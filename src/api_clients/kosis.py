"""KOSIS OpenAPI 클라이언트 (인구·세대수).

- 인구: 행정안전부 주민등록통계 (DT_1B040A3) — 총인구수 (시군구 월별)
- 세대수: 행정안전부 주민등록통계 (DT_1B040B3) — 세대수 (시군구 월별)
- 두 테이블을 (city_code, ym)으로 병합하여 반환.
- KOSIS C1 코드:
    · 시군구 5자리 (41110 = 수원시) — CITY_BY_CODE 직접 매칭
    · 광역시 2자리 (26=부산, 27=대구, 28=인천, 29=광주, 30=대전, 31=울산)
      → _KOSIS_METRO_CODE 테이블로 우리 5자리 코드로 변환
    · 세종 2자리 (36=세종) → 36110
- C1 직접 매칭 불가 시 C1_NM (행정구역명)으로 fallback.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

from config import cities as cities_module
from config.settings import KOSIS_API_KEY, KOSIS_PARAM_URL

log = logging.getLogger(__name__)

DEFAULT_ORG_ID = "101"
POP_TBL_ID  = "DT_1B040A3"   # 총인구수 (시군구 월별)
HH_TBL_ID   = "DT_1B040B3"   # 세대수 (시군구 월별)

# KOSIS 2자리 시도코드 → 우리 city_code
_KOSIS_METRO_CODE: dict[str, str] = {
    "26": "26000",  # 부산광역시
    "27": "27000",  # 대구광역시
    "28": "28000",  # 인천광역시
    "29": "29000",  # 광주광역시
    "30": "30000",  # 대전광역시
    "31": "31000",  # 울산광역시
    "36": "36110",  # 세종특별자치시
}


def fetch_population_monthly(
    start_ym: str,
    end_ym: str,
    org_id: str = DEFAULT_ORG_ID,
    pop_tbl_id: str = POP_TBL_ID,
    hh_tbl_id: str = HH_TBL_ID,
) -> list[dict]:
    """KOSIS 에서 시군구 월별 인구·세대수를 받아 cities 시드와 매칭.

    Args:
        start_ym: 'YYYYMM'
        end_ym:   'YYYYMM'

    Returns:
        ``[{"city_code": str, "ym": str, "population": int|None, "households": int|None}, ...]``
    """
    if not KOSIS_API_KEY:
        log.warning("KOSIS_API_KEY 가 설정되지 않아 인구·세대수 수집을 건너뜁니다.")
        return []

    # 인구 수집
    pop_raw = _call_kosis(org_id=org_id, tbl_id=pop_tbl_id,
                          start_prd=start_ym, end_prd=end_ym)
    # 세대수 수집
    hh_raw = _call_kosis(org_id=org_id, tbl_id=hh_tbl_id,
                         start_prd=start_ym, end_prd=end_ym)

    bucket: dict[tuple[str, str], dict] = {}

    # 인구 처리
    for row in _match_to_cities(pop_raw):
        key = (row["city_code"], row["ym"])
        entry = bucket.setdefault(
            key,
            {"city_code": row["city_code"], "ym": row["ym"],
             "population": None, "households": None},
        )
        if row["population"] is not None:
            entry["population"] = row["population"]

    # 세대수 처리
    for row in _match_to_cities(hh_raw):
        key = (row["city_code"], row["ym"])
        entry = bucket.setdefault(
            key,
            {"city_code": row["city_code"], "ym": row["ym"],
             "population": None, "households": None},
        )
        if row["households"] is not None:
            entry["households"] = row["households"]

    return list(bucket.values())


# ─── 내부 호출 ─────────────────────────────────────────────────
def _call_kosis(
    *, org_id: str, tbl_id: str, start_prd: str, end_prd: str
) -> list[dict]:
    params = {
        "method": "getList",
        "apiKey": KOSIS_API_KEY,
        "format": "json",
        "jsonVD": "Y",
        "orgId": org_id,
        "tblId": tbl_id,
        "prdSe": "M",
        "startPrdDe": start_prd,
        "endPrdDe": end_prd,
        "objL1": "ALL",
        "itmId": "ALL",
    }
    try:
        resp = requests.get(KOSIS_PARAM_URL, params=params, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        import json
        data = json.loads(resp.text)
    except (requests.RequestException, ValueError) as e:
        log.error("KOSIS 호출 실패 (%s/%s): %s", org_id, tbl_id, e)
        return []

    if isinstance(data, dict):
        log.error("KOSIS 오류 응답 (%s): %s", tbl_id, data)
        return []
    log.info("KOSIS [%s] %d행 수집 (%s~%s)", tbl_id, len(data), start_prd, end_prd)
    return data


# ─── 매칭 로직 ─────────────────────────────────────────────────
def _match_to_cities(raw: Iterable[dict]) -> Iterable[dict]:
    name_index = _name_to_code()
    bucket: dict[tuple[str, str], dict] = {}

    for row in raw:
        c1 = (row.get("C1") or "").strip()
        c1_nm = (row.get("C1_NM") or "").strip()
        prd = (row.get("PRD_DE") or "").strip()
        itm_nm = (row.get("ITM_NM") or "").strip()
        val = row.get("DT")
        if not prd or val in (None, ""):
            continue

        # 1) 5자리 시군구 코드 직접 매칭
        if c1 in cities_module.CITY_BY_CODE:
            code = c1
        # 2) 광역시·세종 2자리 시도코드 매칭
        elif c1 in _KOSIS_METRO_CODE:
            code = _KOSIS_METRO_CODE[c1]
        # 3) 행정구역명으로 fallback
        elif c1_nm in name_index:
            code = name_index[c1_nm]
        else:
            continue

        try:
            value = int(float(val))
        except (TypeError, ValueError):
            continue

        key = (code, prd)
        entry = bucket.setdefault(
            key, {"city_code": code, "ym": prd, "population": None, "households": None}
        )
        if "세대" in itm_nm:
            entry["households"] = value
        elif "인구" in itm_nm and "세대" not in itm_nm:
            # 총인구수만 저장 (남자/여자 중복 방지)
            if "총" in itm_nm or entry["population"] is None:
                entry["population"] = value

    yield from bucket.values()


def _name_to_code() -> dict[str, str]:
    """KOSIS C1_NM → cities code 매핑.

    - "광역시도명 시군구명" (풀네임) 우선
    - "시군구명" (단순명) 충돌 시 마지막 값
    - 광역시·세종 시도명도 직접 매핑 (C1_NM이 시도명인 경우 대비)
    """
    idx: dict[str, str] = {}
    for c in cities_module.CITIES:
        idx[f"{c.sido} {c.name}"] = c.code
        idx.setdefault(c.name, c.code)
        # 광역시·세종: 시도명 자체도 매핑 (KOSIS C1_NM이 시도명으로 오는 경우)
        idx.setdefault(c.sido, c.code)
    return idx
