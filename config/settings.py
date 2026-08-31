"""환경변수 로딩 및 분석 임계값."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# .env 파일이 있으면 로드
load_dotenv(ROOT / ".env", override=False)


def _get_setting(key: str, default: str = "") -> str:
    """os.getenv 우선, 없으면 streamlit.secrets 확인."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


# ─── API 인증키 ────────────────────────────────────────────────
KOSIS_API_KEY: str = _get_setting("KOSIS_API_KEY")
REB_API_KEY: str = _get_setting("REB_API_KEY")
DATA_GO_KR_API_KEY: str = _get_setting("DATA_GO_KR_API_KEY")
NAVER_CLIENT_ID: str = _get_setting("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET: str = _get_setting("NAVER_CLIENT_SECRET")


# ─── 데이터베이스 ──────────────────────────────────────────────
DB_PATH: Path = Path(os.getenv("DB_PATH", str(ROOT / "data" / "realestate.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─── API 엔드포인트 ────────────────────────────────────────────
KOSIS_PARAM_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

REB_STATS_URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
REB_LIST_URL  = "https://www.reb.or.kr/r-one/openapi/SttsApiTblm.do"

# 공공데이터포털 - 국토교통부 아파트 매매 실거래가 (RTMSDataSvcAptTradeDev)
MOLIT_APT_TRADE_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
)

# 공공데이터포털 - 한국부동산원 청약접수 경쟁률 및 특별공급 신청현황
APPLYHOME_APT_URL = (
    "https://api.odcloud.kr/api/ApplyhomeInfoCmpetRtSvc/v1/getAPTLttotPblancCmpet"
)
APPLYHOME_APT_LIST_URL = (
    "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
)

# 공공데이터포털 - 한국부동산원 입주예정물량
REB_INFLOW_URL = (
    "https://apis.data.go.kr/B552555/HouseInflowSvc/getHouseInflowList"
)

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


# ─── R-One 통계표 ID (부동산통계정보시스템) ────────────────────
# SttsApiTbl.do 로 조회한 실제 통계표 ID (2025년 기준).
# CLS_ID 는 config/reb_cls_map.py 의 50xxx 코드와 대응.
REB_STATS = {
    # 미분양주택 현황 (시군구·월별) — 준공 전/후 ITM_NM 으로 구분
    "unsold":            "T237973129847263",
    # 시군구별 매매가격지수 아파트 (월별, DTACYCLE_CD=MM)
    "sale_price_index":  "A_2024_00045",
    # 전세가격지수 아파트 (월별, DTACYCLE_CD=MM)
    "jeonse_price_index": "A_2024_00050",
    # 지역별 신규 분양세대수 (월별) — 공급 현황
    "new_supply":        "T244633134461863",
}


# ─── 활황 판정 임계값 ──────────────────────────────────────────
class Thresholds:
    """``src/analysis/score.py`` 가 참조하는 판정 기준값."""

    # demand_up
    HOUSEHOLD_GROWTH_MIN = 0.0           # 12개월 세대수 증가율 > 0
    DEV_NEWS_MIN_COUNT = 3               # 12개월 누적 개발/기업유치 뉴스 ≥ 3건

    # unsold_down
    UNSOLD_TREND_WINDOW_MONTHS = 6       # 회귀 윈도우
    UNSOLD_SLOPE_MAX = 0.0               # 기울기 < 0
    UNSOLD_RATIO_MAX = 0.002             # 세대수 대비 미분양 비율 < 0.2%

    # subscription_hot
    SUBSCRIPTION_WINDOW_MONTHS = 6
    SUBSCRIPTION_AVG_MIN = 1.0           # 평균 경쟁률 > 1.0

    # price_up (필수 조건 — 미충족 시 is_hotspot 탈락)
    PRICE_SUSTAIN_MONTHS = 9             # 연속 상승 최소 개월 수 (전월 대비 MoM)

    # 활황 판정
    HOTSPOT_SIGNAL_MIN = 3               # 4개 신호 중 ≥ 3개


# ─── 수집 기간 기본값 ─────────────────────────────────────────
class Window:
    POPULATION_MONTHS = 24   # 인구·세대수: 최근 2년 (KOSIS 40,000 행 한도)
    UNSOLD_MONTHS = 12       # 미분양: 최근 1년
    SUPPLY_HISTORY_YEARS = 3 # 공급 실적: 과거 3년
    SUPPLY_FUTURE_YEARS = 3  # 공급 예정: 향후 3년
    PRICE_MONTHS = 24        # 가격: 최근 2년
    SUBSCRIPTION_MONTHS = 6  # 청약: 최근 6개월
    NEWS_MONTHS = 12         # 뉴스: 최근 1년
