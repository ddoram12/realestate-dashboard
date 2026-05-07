"""수요 신호 (인구·세대수 추이, 개발사업 뉴스 빈도)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.settings import Thresholds, Window


@dataclass
class DemandSignal:
    household_growth: float | None    # 12개월 세대수 증가율 (소수)
    population_growth: float | None
    dev_news_count: int               # 12개월 개발/기업유치 뉴스 건수
    is_up: bool


def evaluate(con: sqlite3.Connection, city_code: str) -> DemandSignal:
    hh_growth = _yoy_change(con, city_code, "households")
    pop_growth = _yoy_change(con, city_code, "population")

    cutoff = (datetime.now() - timedelta(days=Window.NEWS_MONTHS * 31)).isoformat()
    news_count = con.execute(
        "SELECT COUNT(*) FROM dev_news WHERE city_code=? AND published_at >= ?",
        (city_code, cutoff),
    ).fetchone()[0]

    # 뉴스는 참고 자료이므로 판정에서 제외 — 세대수·인구 증감만으로 판정
    is_up = (
        (hh_growth is not None and hh_growth > Thresholds.HOUSEHOLD_GROWTH_MIN)
        or (pop_growth is not None and pop_growth > Thresholds.HOUSEHOLD_GROWTH_MIN)
    )
    return DemandSignal(hh_growth, pop_growth, news_count, is_up)


def _yoy_change(con: sqlite3.Connection, city_code: str, column: str) -> float | None:
    rows = list(
        con.execute(
            f"SELECT ym, {column} FROM population_monthly "
            f"WHERE city_code=? AND {column} IS NOT NULL ORDER BY ym",
            (city_code,),
        )
    )
    if len(rows) < 2:
        return None
    latest = rows[-1]
    target_ym = _ym_minus_months(latest["ym"], 12)
    base = next((r for r in rows if r["ym"] == target_ym), rows[0])
    if not base[column] or base[column] == 0:
        return None
    return (latest[column] - base[column]) / base[column]


def _ym_minus_months(ym: str, months: int) -> str:
    y = int(ym[:4])
    m = int(ym[4:6])
    total = y * 12 + (m - 1) - months
    return f"{total // 12:04d}{total % 12 + 1:02d}"
