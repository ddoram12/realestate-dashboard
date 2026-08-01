"""한국부동산원 청약홈 OpenAPI 클라이언트 (공공데이터포털 odcloud.kr).

두 API:
- ``getAPTLttotPblancDetail`` : 단지별 분양정보 (주소·총공급세대·입주예정월 등)
- ``getAPTLttotPblancCmpttRt`` : 단지·주택형별 1순위 평균 경쟁률 (별도 승인 필요)

청약 경쟁률 수집 (fetch_subscription_since):
  조인 키: ``HOUSE_MANAGE_NO`` + ``HOUSE_TY``.
  도시 매핑은 ``HSSPLY_ADRES`` (공급위치) 에 ``"{sido} {name}"`` 풀네임이 포함되는지로 판단.

연도별 공급 실적/예정 수집 (fetch_supply_data):
  ``getAPTLttotPblancDetail`` 의 ``MVN_PREARNGE_YM`` (입주예정월) 기준으로
  연도별 공급 세대수를 집계한다.
  현재 연도 미만 = completed_units, 이상 = planned_units.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable

import requests

from config import cities as cities_module
from config.settings import (
    APPLYHOME_APT_LIST_URL,
    APPLYHOME_APT_URL,
    DATA_GO_KR_API_KEY,
)

log = logging.getLogger(__name__)

PAGE_SIZE = 500


def fetch_subscription_since(start_date: str) -> list[dict]:
    """공고시작일 ``start_date`` ('YYYY-MM-DD') 이후 청약 단지·주택형별 경쟁률.

    경쟁률 API(getAPTLttotPblancCmpet)는 날짜 필터를 지원하지 않으므로
    PBLANC_NO 앞 4자리(연도)로 범위를 좁힌 뒤, 분양정보 API의 공고일로 최종 필터링.

    Returns 행 스키마::

        announce_no    # HOUSE_MANAGE_NO + HOUSE_TY
        city_code
        complex_name
        house_type
        supply_units
        applicants
        competition_rate
        announce_date
    """
    if not DATA_GO_KR_API_KEY:
        log.warning("DATA_GO_KR_API_KEY 가 비어있어 청약 경쟁률 수집을 건너뜁니다.")
        return []

    # 1) 분양정보: 공고일 기준 날짜 필터 (주소·공고일 확보)
    detail_rows = _fetch_all(APPLYHOME_APT_LIST_URL, since_field="RCEPT_BGNDE", since=start_date)
    detail_by_id = {
        str(d.get("HOUSE_MANAGE_NO")): d
        for d in detail_rows
        if d.get("HOUSE_MANAGE_NO")
    }
    if not detail_by_id:
        log.warning("최근 분양공고가 없습니다.")
        return []
    log.info("최근 분양공고 %d건", len(detail_by_id))

    # 2) 경쟁률: PBLANC_NO 연도 기준으로 범위 한정 (날짜 직접 필터 불가)
    start_year = int(start_date[:4])
    pblanc_since = f"{start_year}000001"
    rate_rows = _fetch_all(APPLYHOME_APT_URL, since_field="PBLANC_NO", since=pblanc_since)
    log.info("경쟁률 %d건 수신 (PBLANC_NO >= %s)", len(rate_rows), pblanc_since)

    out: list[dict] = []
    for r in rate_rows:
        manage_no = str(r.get("HOUSE_MANAGE_NO") or "")
        if manage_no not in detail_by_id:
            continue

        detail = detail_by_id[manage_no]

        # 1순위만
        rank = r.get("SUBSCRPT_RANK_CODE")
        if rank not in (1, "1"):
            continue

        # 해당지역(01) 우선 — 기타지역은 제외
        if r.get("RESIDE_SECD") != "01":
            continue

        addr = (detail.get("HSSPLY_ADRES") or "").strip()
        city_code = _match_address_to_city(addr)
        if not city_code:
            continue

        house_ty = (r.get("HOUSE_TY") or "").strip()
        announce_no = f"{manage_no}-{house_ty}" if house_ty else manage_no

        rate_raw = r.get("CMPET_RATE")
        rate = _to_float(rate_raw) if rate_raw not in (None, "-", "") else None
        supply = _to_int(r.get("SUPLY_HSHLDCO"))
        applicants = _to_int(r.get("REQ_CNT"))
        if rate is None and supply and applicants:
            rate = round(applicants / supply, 2) if supply else None

        announce_date = _normalize_date(detail.get("RCEPT_BGNDE"))

        out.append(
            {
                "announce_no": announce_no,
                "city_code": city_code,
                "complex_name": (detail.get("HOUSE_NM") or "").strip(),
                "house_type": house_ty,
                "supply_units": supply,
                "applicants": applicants,
                "competition_rate": rate,
                "announce_date": announce_date,
            }
        )
    return out


# ─── 공급 실적/예정 ───────────────────────────────────────────
def fetch_supply_data(start_year: int, end_year: int) -> list[dict]:
    """청약홈 분양공고에서 시군구별 연도별 공급 세대수를 집계.

    Args:
        start_year: 집계 시작 연도 (입주예정 기준)
        end_year:   집계 종료 연도 (입주예정 기준)

    Returns 행 스키마::

        city_code, year, completed_units, planned_units
    """
    if not DATA_GO_KR_API_KEY:
        log.warning("DATA_GO_KR_API_KEY 없음 — 공급 실적/예정 수집 건너뜀")
        return []

    current_year = date.today().year

    # 분양→입주까지 보통 2~4년 소요 → start_year-4년 공고부터 수집
    since_date = f"{start_year - 4}0101"
    log.info("청약홈 공고 수집 (공고일 >= %s, 입주연도 %d~%d)", since_date, start_year, end_year)

    all_rows = _fetch_all(APPLYHOME_APT_LIST_URL,
                          since_field="RCRIT_PBLANC_DE", since=since_date)
    log.info("청약홈 공고 총 %d건 수신", len(all_rows))

    by_key: dict[tuple[str, int], dict] = {}
    for r in all_rows:
        addr = (r.get("HSSPLY_ADRES") or "").strip()
        city_code = _match_address_to_city(addr)
        if not city_code:
            continue

        mvn_ym = (r.get("MVN_PREARNGE_YM") or "").strip()
        if len(mvn_ym) < 6:
            continue
        try:
            mvn_year = int(mvn_ym[:4])
        except ValueError:
            continue

        if mvn_year < start_year or mvn_year > end_year:
            continue

        supply = _to_int(r.get("TOT_SUPLY_HSHLDCO"))
        if not supply:
            continue

        key = (city_code, mvn_year)
        entry = by_key.setdefault(
            key,
            {"city_code": city_code, "year": mvn_year,
             "completed_units": None, "planned_units": None},
        )
        if mvn_year < current_year:
            entry["completed_units"] = (entry["completed_units"] or 0) + supply
        else:
            entry["planned_units"] = (entry["planned_units"] or 0) + supply

    result = list(by_key.values())
    log.info("공급 집계: %d 시군구×연도 조합", len(result))
    return result


# ─── 내부 ─────────────────────────────────────────────────────
def _fetch_all(url: str, since_field: str, since: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        params = {
            "serviceKey": DATA_GO_KR_API_KEY,
            "page": page,
            "perPage": PAGE_SIZE,
            f"cond[{since_field}::GTE]": since,
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as e:
            log.error("청약홈 호출 실패 [%s, page=%d]: %s", url, page, e)
            break

        rows = payload.get("data") or []
        if not rows:
            break
        out.extend(rows)

        try:
            total = int(payload.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
        if page * PAGE_SIZE >= total:
            break
        page += 1
        if page > 200:
            log.warning("청약홈 [%s] 페이지 200 초과로 중단", url)
            break
    return out


def _match_address_to_city(address: str) -> str | None:
    if not address:
        return None
    # 1) 풀네임 우선 ("경기도 수원시" → 41110)
    for c in cities_module.CITIES:
        full = f"{c.sido} {c.name}"
        if full in address:
            return c.code
    # 2) 세종특별자치시: 기초자치단체가 없어 sido 만으로 매칭
    if "세종특별자치시" in address:
        for c in cities_module.CITIES:
            if c.code == "36110":
                return c.code
    # 3) 광역시: sido 전체명이 주소에 포함 ("부산광역시 해운대구" → 26000)
    for c in cities_module.CITIES:
        if c.name == c.sido and c.sido in address:
            return c.code
    # 4) 약식 시도명 + 시군구명 ("서울 강남구")
    for c in cities_module.CITIES:
        sido_short = c.sido.replace("특별시", "").replace("광역시", "").replace("특별자치도", "").replace("특별자치시", "").replace("도", "")
        candidate = f"{sido_short} {c.name}".strip()
        if candidate and candidate in address:
            return c.code
    return None


def _normalize_date(value: object) -> str | None:
    if not value:
        return None
    s = str(value)
    # API 가 '20240115' 또는 '2024-01-15' 형식 모두 사용
    s = s.replace(".", "-")
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10:
        try:
            datetime.strptime(s[:10], "%Y-%m-%d")
            return s[:10]
        except ValueError:
            pass
    return None


def _to_int(v: object) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_float(v: object) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
