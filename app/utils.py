"""Streamlit 공통 유틸 — DB 조회 캐시, 차트 팔레트 등.

DB 갱신: 2026-07-06 (최신 데이터 갱신 및 가상환경 재설정)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import streamlit as st

# 프로젝트 루트를 sys.path 에 추가 (app/ 내부에서 실행 시)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage import db, models  # noqa: E402


# ─── 색상 팔레트 ──────────────────────────────────────────────
SIGNAL_COLOR = {True: "#2ECC71", False: "#E74C3C"}   # 초록/빨강
SCORE_COLOR  = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71", "#27AE60"]
HOTSPOT_BG   = "rgba(46,204,113,0.15)"
NORMAL_BG    = "rgba(0,0,0,0)"

SIGNAL_LABELS = {
    "demand_up":         "📈 수요 증가",
    "unsold_down":       "📉 미분양 감소",
    "subscription_hot":  "🔥 청약 경쟁",
    "price_up":          "💰 가격 상승",
}


# ─── DB 로딩 (캐시) ───────────────────────────────────────────
@st.cache_resource
def get_db_connection() -> sqlite3.Connection:
    from src.storage.db import DB_PATH
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@st.cache_data(ttl=300)
def load_all_signals() -> list[dict]:
    con = get_db_connection()
    rows = models.fetch_signals(con)
    out = []
    for r in rows:
        d = dict(r)
        raw = d.pop("detail_json", None)
        d["detail"] = json.loads(raw) if raw else {}
        out.append(d)
    return out


@st.cache_data(ttl=300)
def load_city_population(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_population(con, city_code)]


@st.cache_data(ttl=300)
def load_city_unsold(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_unsold(con, city_code)]


@st.cache_data(ttl=300)
def load_city_supply(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_supply(con, city_code)]


@st.cache_data(ttl=300)
def load_city_subscription(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_subscription(con, city_code)]


@st.cache_data(ttl=300)
def load_city_price(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_price_index(con, city_code)]


@st.cache_data(ttl=300)
def load_city_news(city_code: str) -> list[dict]:
    con = get_db_connection()
    return [dict(r) for r in models.fetch_dev_news(con, city_code)]


# ─── 접근 제한 (비밀번호 로그인) ─────────────────────────────
def require_auth() -> None:
    """APP_PASSWORD 가 secrets 에 설정된 경우 비밀번호 인증을 요구한다.
    로컬 개발 환경처럼 secrets 가 없으면 인증을 건너뛴다.
    """
    try:
        app_pw = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        app_pw = ""

    if not app_pw:          # 비밀번호 미설정 → 로컬 개발용, 건너뜀
        return
    if st.session_state.get("_authenticated"):
        return

    # ── 로그인 화면 ──────────────────────────────────────────
    st.markdown(
        "<h2 style='text-align:center;margin-top:80px'>🏙️ 전국 부동산 시장 분석</h2>"
        "<p style='text-align:center;color:gray'>접근하려면 비밀번호를 입력하세요.</p>",
        unsafe_allow_html=True,
    )
    col = st.columns([1, 2, 1])[1]
    with col:
        pw = st.text_input("비밀번호", type="password", label_visibility="collapsed",
                           placeholder="비밀번호 입력")
        if st.button("로그인", use_container_width=True, type="primary"):
            if pw == app_pw:
                st.session_state["_authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


# ─── DB 초기화 확인 ───────────────────────────────────────────
def ensure_db() -> None:
    db.init_db()


# ─── 신호 배지 렌더 ───────────────────────────────────────────
def signal_badge(label: str, active: bool) -> str:
    bg = "#2ECC71" if active else "#95A5A6"
    return (
        f'<span style="background:{bg};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:0.8rem;margin:2px;display:inline-block">'
        f'{label}</span>'
    )


def hotspot_badge(is_hot: bool, score: int) -> str:
    if is_hot:
        return (
            '<span style="background:#E74C3C;color:white;padding:5px 14px;'
            'border-radius:20px;font-size:1rem;font-weight:bold">🔥 활황 예상지역</span>'
        )
    color = SCORE_COLOR[min(score, 4)]
    return (
        f'<span style="background:{color};color:white;padding:5px 14px;'
        f'border-radius:20px;font-size:0.9rem">{score}개 신호 충족</span>'
    )


# ─── 숫자 포매팅 ─────────────────────────────────────────────
def fmt_rate(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.{digits}f}%"


def fmt_num(v: int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,}"

