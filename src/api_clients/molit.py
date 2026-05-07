"""국토교통부 아파트 매매 실거래가 OpenAPI 클라이언트.

R-One 가격지수가 점수 산출의 1순위 신호. 이 클라이언트는 도시별 상세 페이지
에서 "최근 실거래 표본" 을 보여주기 위한 보조 데이터.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests
import xmltodict

from config.settings import DATA_GO_KR_API_KEY, MOLIT_APT_TRADE_URL

log = logging.getLogger(__name__)

PAGE_SIZE = 1000


def fetch_apt_trades(lawd_cd: str, deal_ym: str) -> list[dict]:
    """단일 시군구·월 아파트 매매 실거래 내역.

    Args:
        lawd_cd: 시군구 5자리 코드 (cities.code 와 동일)
        deal_ym: 'YYYYMM'

    Returns:
        ``[{apt_name, exclu_use_ar, deal_amount, deal_date, build_year, ...}, ...]``
    """
    if not DATA_GO_KR_API_KEY:
        log.warning("DATA_GO_KR_API_KEY 가 비어있어 실거래가 수집을 건너뜁니다.")
        return []

    out: list[dict] = []
    page = 1
    while True:
        params = {
            "serviceKey": DATA_GO_KR_API_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ym,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
        }
        try:
            resp = requests.get(MOLIT_APT_TRADE_URL, params=params, timeout=30)
            resp.raise_for_status()
            parsed = xmltodict.parse(resp.text)
        except (requests.RequestException, ValueError) as e:
            log.error("MOLIT 실거래가 호출 실패 [%s/%s]: %s", lawd_cd, deal_ym, e)
            break

        body = (
            parsed.get("response", {})
            .get("body", {})
        )
        items_raw = (body.get("items") or {}).get("item")
        if items_raw is None:
            break
        items: Iterable[dict] = items_raw if isinstance(items_raw, list) else [items_raw]

        for it in items:
            try:
                amount = int(str(it.get("dealAmount", "0")).replace(",", "").strip() or 0)
            except ValueError:
                amount = 0
            try:
                year = int(it.get("dealYear") or 0)
                month = int(it.get("dealMonth") or 0)
                day = int(it.get("dealDay") or 0)
                deal_date = f"{year:04d}-{month:02d}-{day:02d}" if year else None
            except ValueError:
                deal_date = None

            out.append(
                {
                    "lawd_cd": lawd_cd,
                    "apt_name": (it.get("aptNm") or "").strip(),
                    "exclu_use_ar": _to_float(it.get("excluUseAr")),
                    "deal_amount_manwon": amount,
                    "deal_date": deal_date,
                    "build_year": _to_int(it.get("buildYear")),
                    "floor": _to_int(it.get("floor")),
                    "umd_nm": (it.get("umdNm") or "").strip(),
                }
            )

        try:
            total = int(body.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
        if page * PAGE_SIZE >= total:
            break
        page += 1
    return out


def _to_int(v: object) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: object) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
