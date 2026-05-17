"""도시별 부동산 시장 상세 분석 페이지.

4개 탭: 수요 / 공급 / 현 상황 / 결론
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils import (  # noqa: E402
    SIGNAL_LABELS,
    ensure_db,
    fmt_num,
    fmt_rate,
    hotspot_badge,
    load_all_signals,
    load_city_news,
    load_city_population,
    load_city_price,
    load_city_subscription,
    load_city_supply,
    load_city_unsold,
    require_auth,
    signal_badge,
)
from config.cities import CITIES  # noqa: E402

st.set_page_config(
    page_title="도시별 상세 분석",
    page_icon="🔍",
    layout="wide",
)
require_auth()
ensure_db()


# ── 도시 선택 ─────────────────────────────────────────────────
city_options = {f"{c.sido[:2]} {c.name}": c.code for c in CITIES}
# session_state 우선(카드 클릭), 없으면 query_params(URL 직접 접근)
presel_code = st.session_state.pop("nav_city", None) or st.query_params.get("city", "")
presel_label = next(
    (k for k, v in city_options.items() if v == presel_code), None
)

with st.sidebar:
    st.header("🏙️ 도시 선택")
    sel_label = st.selectbox(
        "도시",
        list(city_options.keys()),
        index=list(city_options.keys()).index(presel_label) if presel_label else 0,
    )
    city_code = city_options[sel_label]
    city_obj = next(c for c in CITIES if c.code == city_code)

    st.divider()
    if st.button("← 메인 대시보드"):
        st.switch_page("Home.py")


# ── 도시 헤더 ─────────────────────────────────────────────────
signals_all = load_all_signals()
sig = next((s for s in signals_all if s["city_code"] == city_code), None)

st.title(f"🔍 {city_obj.sido} {city_obj.name}")

if sig:
    st.markdown(
        hotspot_badge(bool(sig["is_hotspot"]), int(sig["total_score"])),
        unsafe_allow_html=True,
    )
    badges = "  ".join(
        signal_badge(label, bool(sig[key]))
        for key, label in SIGNAL_LABELS.items()
    )
    st.markdown(badges, unsafe_allow_html=True)
else:
    st.info("아직 점수가 계산되지 않았습니다. `--score` 를 실행하세요.")

st.divider()

# ── 탭 ────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 수요", "🏗️ 공급", "🏠 현 상황", "📊 결론"]
)


# ══════════════════════════════════════════════════════════════
# 탭 1 : 수요
# ══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("인구·세대수 추이")
    pop_data = load_city_population(city_code)

    if pop_data:
        pop_df = pd.DataFrame(pop_data)
        pop_df["ym_dt"] = pd.to_datetime(pop_df["ym"], format="%Y%m")

        col_pop, col_hh = st.columns(2)
        with col_pop:
            if "population" in pop_df.columns and pop_df["population"].notna().any():
                fig = px.line(
                    pop_df, x="ym_dt", y="population",
                    title="인구 추이",
                    labels={"ym_dt": "연월", "population": "인구 (명)"},
                )
                fig.update_traces(line_color="#3498DB")
                fig.update_layout(height=320, margin=dict(t=40, b=20),
                                  xaxis_tickformat="%Y.%m")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("인구 데이터가 없습니다.")

        with col_hh:
            if "households" in pop_df.columns and pop_df["households"].notna().any():
                fig = px.line(
                    pop_df, x="ym_dt", y="households",
                    title="세대수 추이",
                    labels={"ym_dt": "연월", "households": "세대수"},
                    color_discrete_sequence=["#2ECC71"],
                )
                fig.update_layout(height=320, margin=dict(t=40, b=20),
                                  xaxis_tickformat="%Y.%m")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("세대수 데이터가 없습니다.")

        # 증감률 요약
        if len(pop_df) >= 13 and pop_df["households"].notna().sum() >= 2:
            hh_latest = pop_df["households"].dropna().iloc[-1]
            hh_base = pop_df["households"].dropna().iloc[-min(13, len(pop_df["households"].dropna()))]
            yoy_hh = (hh_latest - hh_base) / hh_base if hh_base else None
            st.metric("세대수 전년 동기 대비", fmt_rate(yoy_hh),
                      delta=fmt_rate(yoy_hh) if yoy_hh else None)
    else:
        st.info("인구·세대수 데이터가 없습니다. `--population` 을 실행하세요.")

    st.divider()

    # 부동산 수요 신호 뉴스 (4개 카테고리, 각 최대 2건)
    st.subheader("📰 부동산 수요 신호 뉴스 (최근 12개월)")

    # keyword_hits 첫 번째 토큰이 카테고리명
    _CAT_ORDER  = ["기업유치", "인구증가", "교통개발", "개발사업"]
    _CAT_LABEL  = {
        "기업유치": "🏢 기업유치",
        "인구증가": "👥 인구·세대 증가",
        "교통개발": "🚆 교통 개발",
        "개발사업": "🏗️ 개발사업",
    }
    _CAT_COLOR  = {
        "기업유치": "#8E44AD",
        "인구증가": "#27AE60",
        "교통개발": "#2980B9",
        "개발사업": "#E67E22",
    }

    def _get_cat(kw_str: str) -> str:
        """keyword_hits 첫 토큰을 카테고리로 반환."""
        first = (kw_str or "").split(",")[0].strip()
        return first if first in _CAT_ORDER else "개발사업"

    news_data = load_city_news(city_code)
    if news_data:
        buckets: dict[str, list] = {c: [] for c in _CAT_ORDER}
        for n in sorted(news_data,
                        key=lambda x: x.get("published_at", ""), reverse=True):
            cat = _get_cat(n.get("keyword_hits") or "")
            if len(buckets[cat]) < 2:
                buckets[cat].append(n)

        selected = []
        for cat in _CAT_ORDER:
            selected.extend(buckets[cat])

        if selected:
            for n in selected:
                cat  = _get_cat(n.get("keyword_hits") or "")
                pub  = (n.get("published_at") or "")[:10]
                color = _CAT_COLOR.get(cat, "#7F8C8D")
                label = _CAT_LABEL.get(cat, cat)
                cat_badge = (
                    f'<span style="background:{color};color:white;padding:2px 10px;'
                    f'border-radius:8px;font-size:0.75rem;margin-right:6px">{label}</span>'
                )
                st.markdown(
                    f'{cat_badge}**[{n["title"]}]({n["url"]})**  '
                    f'<span style="color:gray;font-size:0.8rem">{pub}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("해당 도시의 기업유치·인구증가·교통·개발 관련 뉴스가 없습니다.")
    else:
        st.info("뉴스 데이터가 없습니다. (NAVER_CLIENT_ID 설정 또는 `--news` 실행 필요)")


# ══════════════════════════════════════════════════════════════
# 탭 2 : 공급
# ══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("미분양 주택 추이")
    unsold_data = load_city_unsold(city_code)
    if unsold_data:
        u_df = pd.DataFrame(unsold_data)
        u_df["ym_dt"] = pd.to_datetime(u_df["ym"], format="%Y%m")
        u_df["total_unsold"] = u_df["before_completion"].fillna(0)

        fig_u = go.Figure()
        fig_u.add_trace(go.Bar(
            x=u_df["ym_dt"], y=u_df["total_unsold"],
            name="총 미분양", marker_color="#E67E22",
        ))
        fig_u.update_layout(
            height=380,
            title="월별 미분양 현황",
            xaxis_title="연월", yaxis_title="호수",
            xaxis_tickformat="%Y.%m",
            margin=dict(t=50, b=20),
        )
        st.plotly_chart(fig_u, use_container_width=True)

        latest = u_df.iloc[-1]
        total_unsold = int(latest["total_unsold"])
        c1, c2 = st.columns(2)
        c1.metric("최근월 총 미분양", fmt_num(total_unsold))
        # 6개월 추세
        if len(u_df) >= 2:
            prev = int(u_df.iloc[-min(7, len(u_df))]["total_unsold"])
            delta = total_unsold - prev
            c2.metric("6개월 전 대비", fmt_num(delta),
                      delta=str(delta) if delta else None,
                      delta_color="inverse")
    else:
        st.info("미분양 데이터가 없습니다. `--unsold` 를 실행하세요.")

    st.divider()
    st.subheader("연도별 공급 실적 및 예정 물량")
    supply_data = load_city_supply(city_code)
    if supply_data:
        s_df = pd.DataFrame(supply_data)
        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(
            x=s_df["year"],
            y=s_df["completed_units"],
            name="공급 실적 (준공)", marker_color="#3498DB",
        ))
        fig_s.add_trace(go.Bar(
            x=s_df["year"],
            y=s_df["planned_units"],
            name="공급 예정", marker_color="#BDC3C7",
        ))
        fig_s.update_layout(
            barmode="group", height=360,
            title="연도별 공급 실적·예정",
            xaxis_title="연도", yaxis_title="세대수",
            margin=dict(t=50, b=20),
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_s, use_container_width=True)

        st.dataframe(
            s_df.rename(columns={
                "year": "연도", "completed_units": "준공 세대",
                "planned_units": "입주 예정 세대"
            }),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("공급 실적·예정 데이터가 없습니다. `--supply` 를 실행하세요.")


# ══════════════════════════════════════════════════════════════
# 탭 3 : 현 상황
# ══════════════════════════════════════════════════════════════
with tab3:
    st.subheader("아파트 청약 현황 (최근 6개월)")
    sub_data = load_city_subscription(city_code)
    if sub_data:
        sub_df = pd.DataFrame(sub_data)
        sub_df = sub_df.sort_values("announce_date", ascending=False)

        disp_cols = {
            "announce_date": "공고일",
            "complex_name": "단지명",
            "house_type": "주택형",
            "supply_units": "공급 세대",
            "applicants": "청약자 수",
            "competition_rate": "경쟁률",
        }
        disp = sub_df[[c for c in disp_cols if c in sub_df.columns]].rename(
            columns=disp_cols
        )
        if "경쟁률" in disp.columns:
            disp["경쟁률"] = disp["경쟁률"].apply(
                lambda x: f"{x:.2f} : 1" if x is not None else "—"
            )

        st.dataframe(disp, use_container_width=True, hide_index=True)

        # 경쟁률 막대차트
        rate_df = sub_df[sub_df["competition_rate"].notna()].copy()
        if not rate_df.empty:
            rate_df["label"] = (
                rate_df["complex_name"].fillna("") + " " + rate_df["house_type"].fillna("")
            ).str.strip()
            fig_rate = px.bar(
                rate_df,
                x="label", y="competition_rate",
                color="competition_rate",
                color_continuous_scale=["#E74C3C", "#F39C12", "#2ECC71"],
                labels={"label": "단지·주택형", "competition_rate": "청약 경쟁률"},
                title="단지별 청약 경쟁률",
            )
            fig_rate.add_hline(y=1, line_dash="dash",
                               annotation_text="경쟁률 1:1 기준",
                               annotation_position="top right")
            fig_rate.update_layout(height=360, xaxis_tickangle=-30,
                                   margin=dict(t=50, b=80),
                                   coloraxis_showscale=False)
            st.plotly_chart(fig_rate, use_container_width=True)
    else:
        st.info("청약 데이터가 없습니다. `--subscription` 을 실행하세요.")

    st.divider()
    st.subheader("아파트 매매·전세 가격지수 추이 (최근 2년)")
    price_data = load_city_price(city_code)
    if price_data:
        p_df = pd.DataFrame(price_data)
        p_df["ym_dt"] = pd.to_datetime(p_df["ym"], format="%Y%m")

        fig_p = go.Figure()
        if p_df["sale_index"].notna().any():
            fig_p.add_trace(go.Scatter(
                x=p_df["ym_dt"], y=p_df["sale_index"],
                mode="lines+markers", name="매매가격지수",
                line=dict(color="#E74C3C", width=2),
            ))
        if p_df["jeonse_index"].notna().any():
            fig_p.add_trace(go.Scatter(
                x=p_df["ym_dt"], y=p_df["jeonse_index"],
                mode="lines+markers", name="전세가격지수",
                line=dict(color="#3498DB", width=2),
            ))
        fig_p.update_layout(
            title="매매·전세 가격지수 (한국부동산원)",
            xaxis_title="연월", yaxis_title="지수",
            xaxis_tickformat="%Y.%m",
            height=380,
            legend=dict(orientation="h", y=1.08),
            margin=dict(t=50, b=20),
        )
        st.plotly_chart(fig_p, use_container_width=True)

        # 12개월 변화율
        if len(p_df) >= 13:
            for col, label, color in [
                ("sale_index", "매매가격지수", "#E74C3C"),
                ("jeonse_index", "전세가격지수", "#3498DB"),
            ]:
                series = p_df[col].dropna()
                if len(series) >= 2:
                    latest_v = series.iloc[-1]
                    base_v = series.iloc[-min(13, len(series))]
                    yoy = (latest_v - base_v) / base_v if base_v else None
                    st.metric(
                        f"{label} 전년 동기 대비",
                        fmt_rate(yoy),
                        delta=fmt_rate(yoy) if yoy else None,
                        delta_color="normal",
                    )
    else:
        st.info("가격 데이터가 없습니다. `--price` 를 실행하세요.")


# ══════════════════════════════════════════════════════════════
# 탭 4 : 결론
# ══════════════════════════════════════════════════════════════
with tab4:
    st.subheader(f"📊 {city_obj.name} 시장 종합 판정")

    if not sig:
        st.info("점수가 아직 계산되지 않았습니다.")
        st.stop()

    # 활황 배지 (크게)
    st.markdown(
        f"<div style='text-align:center;padding:20px 0'>"
        f"{hotspot_badge(bool(sig['is_hotspot']), int(sig['total_score']))}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 4신호 카드
    st.markdown("### 신호별 판정 결과")
    detail = sig.get("detail") or {}

    signal_detail = {
        "demand_up": {
            "icon": "📈",
            "title": "수요 증가",
            "criteria": "세대수 증가율 > 0  또는  인구 증가율 > 0",
            "values": [
                ("세대수 증가율 (12개월)", fmt_rate(detail.get("household_growth"))),
                ("인구 증가율 (12개월)", fmt_rate(detail.get("population_growth"))),
            ],
        },
        "unsold_down": {
            "icon": "📉",
            "title": "미분양 감소",
            "criteria": "최근 6개월 감소 추세 + 세대수 대비 0.2% 이하",
            "values": [
                ("최근 미분양 합계 (최신월)", fmt_num(detail.get("latest_unsold_total"))),
                ("월평균 변화량", f"{detail.get('unsold_slope', 0) or 0:+.1f}세대"
                 if detail.get("unsold_slope") is not None else "—"),
            ],
        },
        "subscription_hot": {
            "icon": "🔥",
            "title": "청약 경쟁 활발",
            "criteria": "최근 6개월 평균 청약 경쟁률 > 1.0",
            "values": [
                ("청약 단지·주택형 수", fmt_num(detail.get("subscription_count"))),
                ("평균 경쟁률", f"{detail.get('avg_competition_rate', 0) or 0:.2f} : 1"
                 if detail.get("avg_competition_rate") else "—"),
            ],
        },
        "price_up": {
            "icon": "💰",
            "title": "가격 상승 ⭐필수",
            "criteria": "매매 AND 전세가격지수 모두 최근 9개월 연속 전월 대비 상승 (필수 조건)",
            "values": [
                ("매매가격지수 변화율 (12개월)", fmt_rate(detail.get("sale_yoy"))),
                ("전세가격지수 변화율 (12개월)", fmt_rate(detail.get("jeonse_yoy"))),
            ],
        },
    }

    g_cols = st.columns(2)
    for i, (key, info) in enumerate(signal_detail.items()):
        active = bool(sig[key])
        border_color = "#2ECC71" if active else "#E74C3C"
        result_text = "✅ 충족" if active else "❌ 미충족"
        with g_cols[i % 2]:
            with st.container(border=True):
                st.markdown(
                    f"<div style='border-left:4px solid {border_color};padding-left:10px'>"
                    f"<b>{info['icon']} {info['title']}</b> — <span style='color:{border_color}'>{result_text}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"판정 기준: {info['criteria']}")
                for label, val in info["values"]:
                    st.markdown(f"- **{label}**: {val}")

    st.divider()

    # 종합 요약 텍스트
    score = int(sig["total_score"])
    is_hot = bool(sig["is_hotspot"])
    hot_signals = [
        SIGNAL_LABELS[k]
        for k in ["demand_up", "unsold_down", "subscription_hot", "price_up"]
        if sig[k]
    ]
    cold_signals = [
        SIGNAL_LABELS[k]
        for k in ["demand_up", "unsold_down", "subscription_hot", "price_up"]
        if not sig[k]
    ]

    if is_hot:
        summary = (
            f"**{city_obj.name}**은(는) 4가지 지표 중 **{score}개가 양호**하여 "
            f"**부동산 활황 예상지역**으로 분류됩니다.  \n"
            f"충족 신호: {', '.join(hot_signals)}"
        )
        st.success(summary)
    elif score >= 2:
        summary = (
            f"**{city_obj.name}**은(는) {score}개 신호가 충족되어 활황 기준(3개)에 "
            f"근접합니다. 향후 추이를 지속 모니터링하세요.  \n"
            f"충족 신호: {', '.join(hot_signals) if hot_signals else '없음'}  \n"
            f"미충족 신호: {', '.join(cold_signals)}"
        )
        st.warning(summary)
    else:
        summary = (
            f"**{city_obj.name}**은(는) 현재 {score}개 신호만 충족하고 있어 "
            f"시장 활성화 가능성이 낮은 상태입니다.  \n"
            f"미충족 신호: {', '.join(cold_signals)}"
        )
        st.error(summary)

    st.caption(f"마지막 평가: {sig.get('evaluated_at', '—')[:19]}")
