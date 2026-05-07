"""전국 부동산 시장 분석 대시보드 — 메인 페이지 (활황 예상지역).

실행::
    streamlit run app/Home.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 프로젝트 루트 sys.path ─────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils import (  # noqa: E402
    SIGNAL_LABELS,
    ensure_db,
    fmt_num,
    fmt_rate,
    hotspot_badge,
    load_all_signals,
    require_auth,
    signal_badge,
)

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(
    page_title="전국 부동산 시장 분석",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_auth()
ensure_db()


# ── 헤더 ──────────────────────────────────────────────────────
st.title("🏙️ 전국 부동산 시장 분석 대시보드")
st.caption("인구 10만 이상 도시 · 4개 신호 종합 평가 (수요·공급·청약·가격)")


# ── 데이터 로드 ───────────────────────────────────────────────
all_signals = load_all_signals()

if not all_signals:
    st.warning(
        "⚠️ 아직 수집된 데이터가 없습니다.  \n"
        "`python scripts/refresh_data.py --all` 을 실행해 데이터를 먼저 수집하세요."
    )
    st.stop()

df = pd.DataFrame(all_signals)


# ── 사이드바 필터 ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 필터")

    sidos = ["전체"] + sorted(df["sido"].unique().tolist())
    sel_sido = st.selectbox("광역시도", sidos)

    score_range = st.slider("최소 신호 충족 개수", min_value=0, max_value=4, value=3)
    hotspot_only = st.checkbox("활황 예상지역만 보기", value=False)
    st.divider()
    st.caption("데이터 기준일: " + (df["evaluated_at"].max()[:10] if "evaluated_at" in df.columns else "—"))

mask = pd.Series([True] * len(df))
if sel_sido != "전체":
    mask &= df["sido"] == sel_sido
if hotspot_only:
    mask &= df["is_hotspot"] == 1
mask &= df["total_score"] >= score_range
df_filtered = df[mask].copy()


# ── 상단 지표 ─────────────────────────────────────────────────
hotspot_cnt = int(df["is_hotspot"].sum())
total_cnt = len(df)
avg_score = df["total_score"].mean()
top_sido = (
    df[df["is_hotspot"] == 1].groupby("sido").size().idxmax()
    if hotspot_cnt else "—"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 분석 도시", f"{total_cnt}개")
c2.metric("🔥 활황 예상지역", f"{hotspot_cnt}개", help="4개 신호 중 3개 이상 충족")
c3.metric("평균 신호 점수", f"{avg_score:.1f} / 4")
c4.metric("활황 집중 지역", top_sido)

st.divider()


# ── 지도 (버블 맵) ────────────────────────────────────────────
col_map, col_legend = st.columns([3, 1])

with col_map:
    st.subheader("📍 전국 부동산 시장 현황 지도")

    df_map = df_filtered[
        df_filtered["lat"].notna() & df_filtered["lng"].notna()
    ].copy()
    df_map["is_hotspot_label"] = df_map["is_hotspot"].map(
        {1: "🔥 활황 예상", 0: "관찰 중"}
    )
    df_map["city_label"] = df_map["sido"].str[:2] + " " + df_map["name"]
    df_map["hover"] = (
        df_map["city_label"]
        + "<br>신호: " + df_map["total_score"].astype(str) + "/4"
        + "<br>인구: " + df_map["population"].apply(lambda x: f"{x:,}" if x else "—")
    )

    color_map = {"🔥 활황 예상": "#E74C3C", "관찰 중": "#3498DB"}
    size_map = df_map["total_score"].clip(lower=1) * 4 + 2

    fig_map = px.scatter_mapbox(
        df_map,
        lat="lat",
        lon="lng",
        size=size_map,
        color="is_hotspot_label",
        color_discrete_map=color_map,
        hover_name="city_label",
        hover_data={"lat": False, "lng": False, "is_hotspot_label": False},
        custom_data=["hover"],
        zoom=6.2,
        center={"lat": 36.5, "lon": 127.8},
        height=540,
    )
    fig_map.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>"
    )
    fig_map.update_layout(
        mapbox_style="carto-positron",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend_title_text="시장 상태",
    )
    st.plotly_chart(fig_map, use_container_width=True)

with col_legend:
    st.subheader("신호 범례")
    for key, label in SIGNAL_LABELS.items():
        st.markdown(
            f"{signal_badge(label, True)}", unsafe_allow_html=True
        )
    st.divider()
    st.markdown(
        f"""
        **활황 예상지역 판정 기준**
        4개 신호 중 **3개 이상** 충족

        | 신호 | 기준 |
        |------|------|
        | 수요 증가 | 세대수 또는 인구 증가율 > 0 |
        | 미분양 감소 | 6개월 추세↓ + 세대수 대비 0.2% 이하 |
        | 청약 경쟁 | 평균경쟁률 > 1 |
        | 가격 상승⭐ | 매매·전세 모두 9개월 연속↑ **(필수)** |
        """
    )


# ── 도시 카드 ────────────────────────────────────────────────
st.divider()
hotspots = df_filtered.sort_values(
    ["is_hotspot", "total_score", "population"], ascending=[False, False, False]
)

if not hotspots.empty:
    if hotspot_only:
        section_title = f"🔥 활황 예상지역 ({len(hotspots)}개)"
    else:
        section_title = f"📊 신호 {score_range}개 이상 충족 도시 ({len(hotspots)}개)"
    st.subheader(section_title)
    cols_per_row = 3
    rows = [
        hotspots.iloc[i : i + cols_per_row]
        for i in range(0, len(hotspots), cols_per_row)
    ]
    for row_df in rows:
        cols = st.columns(cols_per_row)
        for col, (_, city) in zip(cols, row_df.iterrows()):
            detail = city.get("detail") or {}
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"### {city['sido'][:2]} **{city['name']}**",
                    )
                    st.markdown(
                        hotspot_badge(bool(city["is_hotspot"]), int(city["total_score"])),
                        unsafe_allow_html=True,
                    )
                    st.markdown("")

                    # 신호 배지
                    badges = "".join(
                        signal_badge(label, bool(city[key]))
                        for key, label in SIGNAL_LABELS.items()
                    )
                    st.markdown(badges, unsafe_allow_html=True)
                    st.divider()

                    # 핵심 지표 요약
                    cols_m = st.columns(2)
                    cols_m[0].metric(
                        "세대수 증감",
                        fmt_rate(detail.get("household_growth")),
                    )
                    cols_m[1].metric(
                        "미분양",
                        fmt_num(detail.get("latest_unsold_total")),
                    )
                    cols_m2 = st.columns(2)
                    cols_m2[0].metric(
                        "청약 경쟁률",
                        f"{detail.get('avg_competition_rate', 0) or 0:.1f}:1"
                        if detail.get("avg_competition_rate") else "—",
                    )
                    cols_m2[1].metric(
                        "매매가격",
                        fmt_rate(detail.get("sale_yoy")),
                    )

                    if st.button("상세보기 →", key=f"btn_{city['city_code']}"):
                        st.session_state["nav_city"] = city["city_code"]
                        st.switch_page("pages/1_도시별_상세.py")
else:
    st.info("필터 조건을 만족하는 도시가 없습니다.")


# ── 전체 도시 테이블 ──────────────────────────────────────────
st.divider()
with st.expander("📋 전체 도시 분석표", expanded=False):
    display_cols = {
        "sido": "광역시도",
        "name": "도시명",
        "population": "인구",
        "demand_up": "수요↑",
        "unsold_down": "미분양↓",
        "subscription_hot": "청약경쟁",
        "price_up": "가격↑",
        "total_score": "종합점수",
        "is_hotspot": "활황예상",
    }
    tbl = df_filtered[list(display_cols.keys())].rename(columns=display_cols).copy()
    tbl["활황예상"] = tbl["활황예상"].map({1: "🔥", 0: ""})
    tbl["수요↑"] = tbl["수요↑"].map({1: "✅", 0: "—"})
    tbl["미분양↓"] = tbl["미분양↓"].map({1: "✅", 0: "—"})
    tbl["청약경쟁"] = tbl["청약경쟁"].map({1: "✅", 0: "—"})
    tbl["가격↑"] = tbl["가격↑"].map({1: "✅", 0: "—"})
    tbl["인구"] = tbl["인구"].apply(lambda x: f"{x:,}" if x else "—")
    tbl["종합점수"] = tbl["종합점수"].apply(lambda x: "★" * x)

    st.dataframe(
        tbl,
        use_container_width=True,
        hide_index=True,
        column_config={
            "종합점수": st.column_config.TextColumn("종합점수", width="small"),
        },
    )
