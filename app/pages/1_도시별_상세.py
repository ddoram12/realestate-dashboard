"""도시별 부동산 시장 상세 분석 페이지.

4개 탭: 수요 / 공급 / 현 상황 / 결론
"""
from __future__ import annotations

from datetime import date
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
from config.reb_cls_map import REB_CLS_TO_CITY  # noqa: E402
from src.pdf_generator import generate_city_pdf  # noqa: E402

st.set_page_config(
    page_title="도시별 상세 분석",
    page_icon="🔍",
    layout="wide",
)
require_auth()
ensure_db()


# ── 도시 선택 ─────────────────────────────────────────────────
all_sidos = ["전체"] + sorted(list({c.sido for c in CITIES}))
presel_code = st.session_state.pop("nav_city", None) or st.query_params.get("city", "")
presel_city = next((c for c in CITIES if c.code == presel_code), None)

with st.sidebar:
    st.header("🏙️ 도시 선택")
    default_sido_idx = (all_sidos.index(presel_city.sido) if presel_city and presel_city.sido in all_sidos else 0)
    sel_sido_filter = st.selectbox("지역(시도) 필터", all_sidos, index=default_sido_idx)

    if sel_sido_filter == "전체":
        filtered_cities = sorted(CITIES, key=lambda c: (c.sido, c.name))
    else:
        filtered_cities = sorted([c for c in CITIES if c.sido == sel_sido_filter], key=lambda c: c.name)

    city_options = {c.full_label: c.code for c in filtered_cities}
    presel_label = presel_city.full_label if presel_city and presel_city.full_label in city_options else None
    sel_idx = list(city_options.keys()).index(presel_label) if presel_label else 0

    sel_label = st.selectbox(
        "도시",
        list(city_options.keys()),
        index=sel_idx,
    )
    city_code = city_options[sel_label]
    city_obj = next(c for c in CITIES if c.code == city_code)

    st.divider()
    if st.button("← 메인 대시보드", use_container_width=True):
        st.switch_page("Home.py")

    signals_all = load_all_signals()
    last_update_ts = (
        max((s.get("evaluated_at") or "" for s in signals_all), default="")[:19].replace("T", " ")
        if signals_all else "미수집"
    )

    st.divider()
    st.subheader("🔄 데이터 관리")
    st.markdown(f"🕒 **최종 업데이트**: `{last_update_ts}`")
    if st.button("🔄 데이터 업데이트 실행", use_container_width=True, help="외부 API에서 최신 데이터를 수집하고 신호를 재계산합니다."):
        with st.spinner("최신 데이터를 수집 및 분석하는 중입니다... 잠시만 기다려주세요 (약 20~30초 소요)."):
            try:
                import subprocess
                res = subprocess.run(
                    [sys.executable, "scripts/refresh_data.py", "--all"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(ROOT),
                )
                st.cache_data.clear()
                st.success("데이터 업데이트가 성공적으로 완료되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"업데이트 중 오류가 발생했습니다: {e}")




# ── 도시 헤더 ─────────────────────────────────────────────────
signals_all = load_all_signals()
sig = next((s for s in signals_all if s["city_code"] == city_code), None)

pop_data = load_city_population(city_code)
news_data = load_city_news(city_code)
unsold_data = load_city_unsold(city_code)
supply_data = load_city_supply(city_code)
sub_data = load_city_subscription(city_code)
price_data = load_city_price(city_code)

# PDF 보고서 사전 생성 (다운로드 버튼용)
try:
    pdf_bytes = generate_city_pdf(
        city_obj=city_obj,
        sig=sig,
        pop_data=pop_data,
        news_data=news_data,
        unsold_data=unsold_data,
        supply_data=supply_data,
        sub_data=sub_data,
        price_data=price_data,
    )
except Exception as e:
    pdf_bytes = None

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title(f"🔍 {city_obj.sido} {city_obj.name}")
with col_h2:
    st.write("")
    if pdf_bytes:
        st.download_button(
            label="📄 전체 분석 PDF 다운로드",
            data=pdf_bytes,
            file_name=f"{city_obj.sido_short}_{city_obj.name}_부동산종합분석.pdf",
            mime="application/pdf",
            use_container_width=True,
            help="수요, 공급, 현 상황, 종합 결론이 모두 포함된 A4 종합 보고서 PDF를 다운로드합니다.",
        )

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

    with st.expander("🔍 인구·세대수 원천 통계 및 근거 자료 확인"):
        st.markdown(
            f"""
            - **기관 및 통계명**: 통계청 KOSIS 국가통계포털 · 행정안전부 주민등록 인구통계
            - **조회 대상**: **{city_obj.sido} {city_obj.name}** (통계청 행정구역 코드: `{city_code}`)
            - **원천 통계표**:
              - 총인구수: `DT_1B040A3` (주민등록인구현황 - 시군구 월별 총인구수)
              - 세대수: `DT_1B040B3` (주민등록인구현황 - 시군구 월별 세대수)
            - **공식 확인 바로가기**: [KOSIS 국가통계포털 (주민등록인구통계)](https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B040A3)
            """
        )
        if pop_data:
            st.caption("📊 DB에 저장된 최근 월별 원본 수치 (최신순)")
            raw_pop_df = pd.DataFrame(pop_data).sort_values("ym", ascending=False)
            st.dataframe(
                raw_pop_df.rename(columns={
                    "ym": "연월(YYYYMM)",
                    "population": "인구수(명)",
                    "households": "세대수",
                })[["연월(YYYYMM)", "인구수(명)", "세대수"]],
                use_container_width=True,
                hide_index=True,
            )

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

    with st.expander("🔍 미분양 주택 통계 원천 및 근거 자료 확인"):
        # CLS_ID 매핑 역조회
        reb_cls_id = next((k for k, v in REB_CLS_TO_CITY.items() if v == city_code), "—")
        st.markdown(
            f"""
            - **기관 및 통계명**: 국토교통부 · 한국부동산원 부동산통계정보시스템 (R-One)
            - **조회 대상**: **{city_obj.sido} {city_obj.name}** (부동산원 R-One 지역분류코드 `CLS_ID`: `{reb_cls_id}`)
            - **원천 통계표**: `T237973129847263` (미분양주택현황 - 시군구·월별 미분양 및 준공후 미분양)
            - **통계 특성 안내**:
              - 국토부 미분양 통계는 지자체(시·군청 건축과)에 신고된 주택사업장의 잔여세대를 취합한 공식 자료입니다.
              - 30세대 이상 일반 아파트뿐만 아니라 도시형생활주택, 임대 후 분양전환 잔여물량, 지자체 일괄 신고분이 포함될 수 있습니다.
            - **공식 확인 바로가기**: [한국부동산원 R-One 부동산통계정보시스템](https://www.reb.or.kr/r-one/main.do) · [국토교통부 통계누리 (미분양현황)](https://stat.molit.go.kr)
            """
        )
        if unsold_data:
            st.caption("📊 DB에 저장된 최근 월별 미분양 원본 수치 (최신순)")
            raw_u_df = pd.DataFrame(unsold_data).sort_values("ym", ascending=False)
            st.dataframe(
                raw_u_df.rename(columns={
                    "ym": "연월(YYYYMM)",
                    "before_completion": "미분양(호)",
                    "after_completion": "준공후 미분양(호)",
                })[["연월(YYYYMM)", "미분양(호)", "준공후 미분양(호)"]],
                use_container_width=True,
                hide_index=True,
            )

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
        st.info("💡 최근 분석 기간 내 한국부동산원 청약홈에 등록된 분양·입주 예정 아파트 물량이 없습니다. (신규 민간/공공 분양 공급이 없었던 지역입니다)")
        # 빈 연도별 0 공급 현황 테이블 표시
        empty_years = [date.today().year + i for i in range(-2, 3)]
        empty_s_df = pd.DataFrame({
            "연도": empty_years,
            "준공 실적 (세대)": [0] * len(empty_years),
            "입주 예정 (세대)": [0] * len(empty_years),
        })
        st.dataframe(empty_s_df, use_container_width=True, hide_index=True)

    with st.expander("🔍 공급 실적·예정 물량 원천 및 근거 자료 확인"):
        st.markdown(
            f"""
            - **기관 및 통계명**: 한국부동산원 청약홈 (공공데이터포털 `odcloud.kr`)
            - **수집 기준**:
              - 아파트 분양정보 상세 API (`getAPTLttotPblancDetail`)의 입주예정월(`MVN_PREARNGE_YM`) 및 총공급세대수(`TOT_SUPLY_HSHLDCO`)
              - 주소 필터: 공급위치 주소에 **`{city_obj.sido} {city_obj.name}`** 포함 단지 전수 취합
            - **통계 특성 안내**:
              - 주택공급에 관한 규칙에 따라 입주자모집승인을 받는 30세대 이상 아파트 분양공고 전체를 전수 집계합니다.
              - 최근 몇 년간 신규 분양공고가 없었던 소도시나 군 지역의 경우 집계 물량이 0세대로 표기됩니다.
            - **공식 확인 바로가기**: [한국부동산원 청약홈 (분양정보/경쟁률)](https://www.applyhome.co.kr)
            """
        )
        if supply_data:
            st.caption("📊 DB에 집계된 연도별 공급 실적 및 예정 물량")
            st.dataframe(
                pd.DataFrame(supply_data).rename(columns={
                    "year": "연도",
                    "completed_units": "준공 세대수",
                    "planned_units": "입주 예정 세대수",
                })[["연도", "준공 세대수", "입주 예정 세대수"]],
                use_container_width=True,
                hide_index=True,
            )


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
        st.info("💡 최근 6개월 내 해당 도시에서 진행된 아파트 분양 청약 접수 건이 없습니다.")

    with st.expander("🔍 아파트 청약 경쟁률 원천 및 근거 자료 확인"):
        st.markdown(
            f"""
            - **기관 및 통계명**: 한국부동산원 청약홈 (공공데이터포털)
            - **조회 대상**: **{city_obj.sido} {city_obj.name}** (최근 6개월 입주자모집공고 건)
            - **원천 API**:
              - 분양정보 상세: `getAPTLttotPblancDetail` (주택관리번호, 공급위치, 총공급세대수)
              - 1순위 청약경쟁률: `getAPTLttotPblancCmpet` (접수건수, 해당지역 순위경쟁률)
            - **공식 확인 바로가기**: [청약홈 청약당첨·경쟁률 조회](https://www.applyhome.co.kr)
            """
        )
        if sub_data:
            st.caption("📊 DB에 집계된 최근 6개월 청약 단지별 상세 데이터")
            st.dataframe(
                pd.DataFrame(sub_data).rename(columns={
                    "announce_date": "공고일자",
                    "complex_name": "단지명",
                    "house_type": "주택형",
                    "supply_units": "일반공급세대",
                    "applicants": "접수건수",
                    "competition_rate": "경쟁률(:1)",
                })[["공고일자", "단지명", "주택형", "일반공급세대", "접수건수", "경쟁률(:1)"]],
                use_container_width=True,
                hide_index=True,
            )

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

    with st.expander("🔍 매매·전세 가격지수 원천 및 근거 자료 확인"):
        st.markdown(
            f"""
            - **기관 및 통계명**: 한국부동산원 전국주택가격동향조사 (부동산통계정보시스템 R-One)
            - **조회 대상**: **{city_obj.sido} {city_obj.name}** (월별 아파트 매매·전세 가격지수, 기준시점=100)
            - **원천 통계표**:
              - 아파트 매매가격지수: `A_2024_00045` (월간 전국주택가격동향조사)
              - 아파트 전세가격지수: `A_2024_00050` (월간 전국주택가격동향조사)
            - **통계 특성 안내**:
              - 기준시점(100.0)을 기준으로 가격의 상승/하락 비율을 나타내는 국가승인통계입니다.
              - 군 지역 등 일부 소규모 지역의 경우 인접 상위 시·도 지수를 준용하거나 격월/분기별 조사가 적용될 수 있습니다.
            - **공식 확인 바로가기**: [한국부동산원 R-One 아파트 가격동향 통계](https://www.reb.or.kr/r-one/main.do)
            """
        )
        if price_data:
            st.caption("📊 DB에 저장된 최근 월별 가격지수 원본 수치 (최신순)")
            raw_p_df = pd.DataFrame(price_data).sort_values("ym", ascending=False)
            st.dataframe(
                raw_p_df.rename(columns={
                    "ym": "연월(YYYYMM)",
                    "sale_index": "매매가격지수",
                    "jeonse_index": "전세가격지수",
                })[["연월(YYYYMM)", "매매가격지수", "전세가격지수"]],
                use_container_width=True,
                hide_index=True,
            )


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

    with st.expander("🔍 종합 판정 기준 및 4대 지표 산출 근거 확인"):
        st.markdown(
            f"""
            ### 📌 4대 투자 신호 판정 기준 및 데이터 소스
            1. **수요 증가 (demand_up)**:
               - **근거 통계**: 행정안전부 주민등록 인구/세대수 (통계청 KOSIS)
               - **판정 기준**: 최근 12개월간 세대수 증가율 > 0% 또는 인구 증가율 > 0%
            2. **미분양 감소 (unsold_down)**:
               - **근거 통계**: 국토교통부 · 한국부동산원 미분양주택현황 (R-One `T237973129847263`)
               - **판정 기준**: 최근 6개월 미분양 추세 기울기 < 0 (감소 추세) 및 총 세대수 대비 미분양 0.2% 이하
            3. **청약 경쟁 활발 (subscription_hot)**:
               - **근거 통계**: 한국부동산원 청약홈 아파트 1순위 청약경쟁률 API
               - **판정 기준**: 최근 6개월간 일반공급 평균 경쟁률 1.0:1 초과
            4. **가격 상승 (price_up) ⭐필수 조건**:
               - **근거 통계**: 한국부동산원 월간 전국주택가격동향조사 매매·전세가격지수
               - **판정 기준**: 매매 및 전세가격지수 모두 최근 9개월 연속 전월 대비 상승
            
            ---
            - **활황 예상지역(Hotspot) 최종 기준**: 필수 조건(가격 상승)을 포함하여 4개 신호 중 **3개 이상 충족** 시 선정.
            """
        )

    st.divider()
    if pdf_bytes:
        st.download_button(
            label=f"📄 {city_obj.name} 전체 분석 보고서 PDF 다운로드",
            data=pdf_bytes,
            file_name=f"{city_obj.sido_short}_{city_obj.name}_부동산종합분석.pdf",
            mime="application/pdf",
            key="btn_pdf_tab4",
            use_container_width=True,
            help="수요, 공급, 현 상황, 종합 결론이 모두 포함된 A4 종합 보고서 PDF를 다운로드합니다.",
        )
