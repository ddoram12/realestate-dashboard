"""배치 수집 오케스트레이션.

각 API 클라이언트를 호출해 SQLite 캐시에 적재. 실패한 항목은 로그에 남기고
다른 항목 수집은 계속 진행한다 (한 API 키 누락이 전체 실패를 일으키지 않도록).
"""
from __future__ import annotations

import logging
from datetime import date

from config.settings import Window
from src.analysis import score as score_mod
from src.api_clients import apply_home, kosis, naver_news, reb
from src.storage import db, models

log = logging.getLogger(__name__)


# ─── 기간 헬퍼 ────────────────────────────────────────────────
def _ym_today() -> str:
    today = date.today()
    return f"{today.year:04d}{today.month:02d}"


def _ym_minus_months(months: int) -> str:
    today = date.today()
    total = today.year * 12 + (today.month - 1) - months
    return f"{total // 12:04d}{total % 12 + 1:02d}"


# ─── 단계별 수집 함수 ─────────────────────────────────────────
def run_population() -> int:
    log.info("[population] 수집 시작")
    rows = kosis.fetch_population_monthly(
        start_ym=_ym_minus_months(Window.POPULATION_MONTHS),
        end_ym=_ym_today(),
    )
    if not rows:
        return 0
    with db.connect() as con:
        n = models.upsert_population(con, rows)
        con.commit()
    log.info("[population] %d 행 저장", n)
    return n


def run_unsold() -> int:
    log.info("[unsold] 수집 시작")
    rows = reb.fetch_unsold(
        start_ym=_ym_minus_months(Window.UNSOLD_MONTHS),
        end_ym=_ym_today(),
    )
    if not rows:
        return 0
    with db.connect() as con:
        n = models.upsert_unsold(con, rows)
        con.commit()
    log.info("[unsold] %d 행 저장", n)
    return n


def run_price_index() -> int:
    log.info("[price_index] 수집 시작")
    rows = reb.fetch_price_index(
        start_ym=_ym_minus_months(Window.PRICE_MONTHS),
        end_ym=_ym_today(),
    )
    if not rows:
        return 0
    with db.connect() as con:
        n = models.upsert_price_index(con, rows)
        con.commit()
    log.info("[price_index] %d 행 저장", n)
    return n


def run_supply() -> int:
    log.info("[supply] 수집 시작 (청약홈 공고 기반)")
    today_year = date.today().year
    start_year = today_year - Window.SUPPLY_HISTORY_YEARS
    end_year   = today_year + Window.SUPPLY_FUTURE_YEARS
    rows = apply_home.fetch_supply_data(start_year, end_year)
    if not rows:
        return 0
    with db.connect() as con:
        n = models.upsert_supply(con, rows)
        con.commit()
    log.info("[supply] %d 행 저장", n)
    return n


def run_subscription() -> int:
    log.info("[subscription] 수집 시작")
    cutoff_dt = date.fromordinal(
        date.today().toordinal() - Window.SUBSCRIPTION_MONTHS * 31
    )
    rows = apply_home.fetch_subscription_since(cutoff_dt.strftime("%Y-%m-%d"))
    if not rows:
        return 0
    with db.connect() as con:
        n = models.upsert_subscription(con, rows)
        con.commit()
    log.info("[subscription] %d 행 저장", n)
    return n


def run_news() -> int:
    log.info("[dev_news] 수집 시작")
    rows = naver_news.fetch_dev_news_recent(months=Window.NEWS_MONTHS)
    if not rows:
        return 0
    with db.connect() as con:
        n = models.insert_dev_news(con, rows)
        con.commit()
    log.info("[dev_news] %d 행 저장", n)
    return n


def run_score() -> int:
    log.info("[score] 신호 계산")
    with db.connect() as con:
        results = score_mod.evaluate_all(con)
    hotspots = sum(r["is_hotspot"] for r in results)
    log.info("[score] %d개 도시 평가, 활황 예상지역 %d개", len(results), hotspots)
    return len(results)


# ─── 진입점 ───────────────────────────────────────────────────
ALL_STEPS: dict[str, callable] = {
    "population": run_population,
    "unsold": run_unsold,
    "price": run_price_index,
    "supply": run_supply,
    "subscription": run_subscription,
    "news": run_news,
    "score": run_score,
}


def run(steps: list[str] | None = None) -> dict[str, int]:
    """``steps`` 가 None 이면 전체 실행. 각 단계 실패는 다른 단계에 영향 없음."""
    db.init_db()
    targets = steps or list(ALL_STEPS.keys())
    summary: dict[str, int] = {}
    for name in targets:
        fn = ALL_STEPS.get(name)
        if not fn:
            log.warning("알 수 없는 단계: %s", name)
            continue
        try:
            summary[name] = fn()
        except Exception as e:  # noqa: BLE001 - 한 단계 실패가 전체를 막지 않게
            log.exception("단계 [%s] 실패: %s", name, e)
            summary[name] = -1
    return summary
