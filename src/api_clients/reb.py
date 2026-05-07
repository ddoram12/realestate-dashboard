"""한국부동산원 R-One OpenAPI 클라이언트.

수집 대상:
- 미분양주택 현황 (준공 전/후, 시군구·월별)
- 주택가격지수 (매매·전세, 시군구·월별)
- 지역별 신규 분양세대수 (공급 현황)

R-One 응답 형식 (JSON)::

    {
      "SttsApiTblData": [
        {"head": [{"CLS_ID": "...", "ITM_ID": "...", ...}]},
        {"row": [
          {
            "STATBL_ID": "T237973129847263",
            "WRTTIME_IDTFR_ID": "202501",
            "CLS_ID": "50019",
            "CLS_NM": "서울 종로구",
            "ITM_ID": "...",
            "ITM_NM": "준공 전 미분양",
            "DTA_VAL": "152"
          },
          ...
        ]}
      ]
    }

CLS_ID 는 R-One 내부 코드(50xxx)로, ``config.reb_cls_map.lookup()`` 으로
cities.py 의 법정동 5자리 코드로 변환한다.
"""
from __future__ import annotations

import logging

import requests

from config.reb_cls_map import lookup as cls_lookup
from config.settings import REB_API_KEY, REB_STATS, REB_STATS_URL

log = logging.getLogger(__name__)

PAGE_SIZE = 1000


# ─── 미분양 ────────────────────────────────────────────────────
def fetch_unsold(start_ym: str, end_ym: str) -> list[dict]:
    """미분양주택 현황을 시군구·월 단위로 수집.

    반환 행 스키마: ``city_code, ym, before_completion, after_completion``
    """
    if not REB_API_KEY:
        log.warning("REB_API_KEY 없음 — 미분양 수집 건너뜀")
        return []

    rows = _fetch_stats_range(REB_STATS["unsold"], start_ym, end_ym)
    by_key: dict[tuple[str, str], dict] = {}

    for r in rows:
        code = _resolve_city(r)
        if not code:
            continue
        ym = (r.get("WRTTIME_IDTFR_ID") or "").strip()
        if not ym:
            continue

        itm = (r.get("ITM_NM") or "").strip()
        val = _to_int(r.get("DTA_VAL"))

        entry = by_key.setdefault(
            (code, ym),
            {"city_code": code, "ym": ym,
             "before_completion": None, "after_completion": None},
        )
        if "준공후" in itm or "준공 후" in itm:
            entry["after_completion"] = val
        elif "준공전" in itm or "준공 전" in itm:
            entry["before_completion"] = val
        else:
            # 전체 합계만 제공되는 경우 (미분양현황) → before_completion 에 저장
            if entry["before_completion"] is None:
                entry["before_completion"] = val

    return list(by_key.values())


# ─── 가격 지수 ────────────────────────────────────────────────
def fetch_price_index(start_ym: str, end_ym: str) -> list[dict]:
    """매매·전세 가격지수를 시군구 단위로 수집.

    - 매매: 분기별(QY) A_2024_00180, ym = YYYYQQ 형식 (202501=1Q, 202504=4Q)
    - 전세: 월별(MM) A_2024_00050

    반환 행 스키마: ``city_code, ym, sale_index, jeonse_index``
    """
    if not REB_API_KEY:
        log.warning("REB_API_KEY 없음 — 가격지수 수집 건너뜀")
        return []

    by_key: dict[tuple[str, str], dict] = {}

    # ── 매매: 월 단위 ─────────────────────────────────────────
    sale_rows = _fetch_stats_range(
        REB_STATS["sale_price_index"], start_ym, end_ym, cycle="MM"
    )
    for r in sale_rows:
        code = _resolve_city(r)
        if not code:
            continue
        ym = (r.get("WRTTIME_IDTFR_ID") or "").strip()
        if not ym:
            continue
        val = _to_float(r.get("DTA_VAL"))
        entry = by_key.setdefault(
            (code, ym),
            {"city_code": code, "ym": ym, "sale_index": None, "jeonse_index": None},
        )
        entry["sale_index"] = val

    # ── 전세: 월 단위 ─────────────────────────────────────────��──────────────────────
    jeonse_rows = _fetch_stats_range(
        REB_STATS["jeonse_price_index"], start_ym, end_ym, cycle="MM"
    )
    for r in jeonse_rows:
        code = _resolve_city(r)
        if not code:
            continue
        ym = (r.get("WRTTIME_IDTFR_ID") or "").strip()
        if not ym:
            continue
        val = _to_float(r.get("DTA_VAL"))
        entry = by_key.setdefault(
            (code, ym),
            {"city_code": code, "ym": ym, "sale_index": None, "jeonse_index": None},
        )
        entry["jeonse_index"] = val

    return list(by_key.values())


# ─── 공급 (신규 분양세대수) ──────────────────────────────────
def fetch_future_supply(end_year: int) -> list[dict]:
    """신규 분양세대수 시군구별 데이터 수집.

    주의: R-One 분양세대수 통계표(T244633134461863)는 시도 단위로만 제공되어
    시군구 매칭이 불가. 청약홈 API 기반 수집은 별도 구현 예정.
    현재는 빈 리스트 반환.
    """
    return []

    if not REB_API_KEY:  # noqa: unreachable
        return []

    start_ym = f"{end_year - 5}01"
    end_ym = f"{end_year}12"
    rows = _fetch_stats_range(REB_STATS["new_supply"], start_ym, end_ym)

    by_key: dict[tuple[str, int], dict] = {}
    for r in rows:
        code = _resolve_city(r)
        if not code:
            continue
        period = (r.get("WRTTIME_IDTFR_ID") or "").strip()
        if len(period) < 6:
            continue
        try:
            year = int(period[:4])
        except ValueError:
            continue
        val = _to_int(r.get("DTA_VAL"))
        entry = by_key.setdefault(
            (code, year),
            {"city_code": code, "year": year,
             "completed_units": None, "planned_units": 0},
        )
        entry["planned_units"] = (entry.get("planned_units") or 0) + (val or 0)

    return list(by_key.values())


# ─── 내부 공통 ─────────────────────────────────────────────────
def _fetch_stats(tbl_id: str, start_ym: str, cycle: str = "MM") -> list[dict]:
    """R-One SttsApiTblData.do 를 페이지 단위로 수집.

    ``start_ym`` 을 WRTTIME_IDTFR_ID 로 전달해 해당 시점 이후 데이터를 가져오고,
    상위 함수에서 end_ym 으로 파이썬 레벨 필터링.
    """
    out: list[dict] = []
    page = 1
    while True:
        params = {
            "KEY": REB_API_KEY,
            "Type": "json",
            "pIndex": page,
            "pSize": PAGE_SIZE,
            "STATBL_ID": tbl_id,
            "DTACYCLE_CD": cycle,
            "WRTTIME_IDTFR_ID": start_ym,
        }
        try:
            resp = requests.get(REB_STATS_URL, params=params, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as e:
            log.error("R-One 호출 실패 [%s p%d]: %s", tbl_id, page, e)
            break

        # 응답 구조: {"SttsApiTblData": [{"head": [...]}, {"row": [...]}]}
        wrapper = payload.get("SttsApiTblData") or []
        if not isinstance(wrapper, list) or not wrapper:
            log.debug("R-One [%s] 빈 응답: %s", tbl_id, str(payload)[:200])
            break

        row_data: list[dict] = []
        for section in wrapper:
            if isinstance(section, dict) and "row" in section:
                row_data = section["row"]
                break

        if not row_data:
            log.debug("R-One [%s] row 없음 (page=%d)", tbl_id, page)
            break

        out.extend(row_data)
        if len(row_data) < PAGE_SIZE:
            break
        page += 1
        if page > 200:
            log.warning("R-One [%s] 200페이지 초과 중단", tbl_id)
            break

    log.info("R-One [%s] 총 %d 행 수집 (ym=%s)", tbl_id, len(out), start_ym)
    return out


def _fetch_stats_range(tbl_id: str, start_ym: str, end_ym: str,
                       cycle: str = "MM") -> list[dict]:
    """start_ym ~ end_ym 범위를 순차 호출로 수집.

    cycle='MM' → 월 단위 반복, cycle='QY' → 분기 단위 반복.
    """
    out: list[dict] = []
    ym = start_ym
    step = _next_quarter if cycle == "QY" else _next_ym
    while ym <= end_ym:
        out.extend(_fetch_stats(tbl_id, ym, cycle))
        ym = step(ym)
    return out


def _next_ym(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[4:])
    month += 1
    if month > 12:
        month, year = 1, year + 1
    return f"{year:04d}{month:02d}"


def _next_quarter(q: str) -> str:
    """분기 YYYYQQ 에서 다음 분기 반환. 예: 202504 → 202601"""
    year, qnum = int(q[:4]), int(q[4:])
    qnum += 1
    if qnum > 4:
        qnum, year = 1, year + 1
    return f"{year:04d}{qnum:02d}"


def _ym_to_quarter(ym: str) -> str:
    """YYYYMM → YYYYQQ 변환. 예: 202403 → 202401 (Q1), 202406 → 202402 (Q2)"""
    year, month = int(ym[:4]), int(ym[4:])
    q = (month - 1) // 3 + 1
    return f"{year:04d}{q:02d}"


def _resolve_city(row: dict) -> str | None:
    """CLS_ID or CLS_FULLNM → cities.py code(법정동 5자리) 변환.

    1) 50xxx 형식 CLS_ID: reb_cls_map.lookup() 사용 (미분양 테이블)
    2) 510xxx/530xxx 형식: CLS_FULLNM 파싱 (가격지수 테이블)
    """
    cls_id = row.get("CLS_ID")

    # 50xxx → reb_cls_map 직접 매핑
    if isinstance(cls_id, int) and 50000 <= cls_id < 60000:
        return cls_lookup(cls_id)
    if isinstance(cls_id, str):
        try:
            int_id = int(cls_id)
            if 50000 <= int_id < 60000:
                return cls_lookup(int_id)
        except ValueError:
            pass

    # 510xxx/530xxx → CLS_FULLNM 기반 매칭 (가격지수 테이블용)
    fullnm = (row.get("CLS_FULLNM") or "").strip()
    if fullnm:
        return _match_by_fullnm(fullnm)

    return None


# ─── CLS_FULLNM 파싱 (가격지수 테이블) ────────────────────────
# 예: "부산"            → 광역시 시 단위 직접 매핑 (1레벨)
# 예: "서울>종로구"     → ("서울", "종로구") → 없음 (서울 제외)
# 예: "경기>안양시"     → ("경기", "안양시") → 41170
# 예: "경기>안양시>만안구" → 3단계 = 우리 도시 목록에 없음

# 광역시 약칭 → 시 단위 city_code (1레벨 CLS_FULLNM 매칭용)
_METRO_CODE: dict[str, str] = {
    "부산": "26000",
    "대구": "27000",
    "인천": "28000",
    "광주": "29000",
    "대전": "30000",
    "울산": "31000",
}

_SIDO_ABBR: dict[str, str] = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}

_FULLNM_INDEX: dict[tuple[str, str], str] | None = None


def _fullnm_index() -> dict[tuple[str, str], str]:
    """(sido_abbr, city_name) → city_code 인덱스를 한 번만 빌드."""
    global _FULLNM_INDEX
    if _FULLNM_INDEX is not None:
        return _FULLNM_INDEX
    from config import cities as cities_module
    reverse_abbr = {v: k for k, v in _SIDO_ABBR.items()}
    idx: dict[tuple[str, str], str] = {}
    for city in cities_module.CITIES:
        abbr = reverse_abbr.get(city.sido, city.sido)
        idx[(abbr, city.name)] = city.code
    _FULLNM_INDEX = idx
    return idx


def _match_by_fullnm(fullnm: str) -> str | None:
    """CLS_FULLNM → city_code.

    1레벨("부산"): 광역시 시 단위 직접 매핑.
    2레벨 이상("경기>안양시"): 시도 약칭 + 마지막 항목으로 매칭.
    예: "경기>경부1권>안양시"         → ("경기", "안양시") → 41170
    """
    parts = [p.strip() for p in fullnm.split(">")]
    if len(parts) == 1:
        # 광역시 전체 레벨 — 예: "부산" → "26000"
        return _METRO_CODE.get(parts[0])
    sido_abbr = parts[0]
    city_name = parts[-1]
    return _fullnm_index().get((sido_abbr, city_name))


def _to_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
