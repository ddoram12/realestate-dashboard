"""현 상황 신호 (청약 경쟁률, 매매·전세 가격 추이)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.settings import Thresholds, Window


@dataclass
class CurrentSignal:
    avg_competition_rate: float | None   # 최근 6개월 평균 경쟁률
    subscription_count: int
    sale_yoy: float | None               # 12개월 매매가격지수 변화율
    jeonse_yoy: float | None             # 12개월 전세가격지수 변화율
    is_subscription_hot: bool
    is_price_up: bool


def evaluate(con: sqlite3.Connection, city_code: str) -> CurrentSignal:
    cutoff = (
        datetime.now() - timedelta(days=Window.SUBSCRIPTION_MONTHS * 31)
    ).strftime("%Y-%m-%d")
    sub = con.execute(
        """
        SELECT COUNT(*), AVG(competition_rate)
        FROM subscription
        WHERE city_code = ?
          AND announce_date >= ?
          AND competition_rate IS NOT NULL
        """,
        (city_code, cutoff),
    ).fetchone()
    sub_count = int(sub[0] or 0)
    avg_rate = float(sub[1]) if sub[1] is not None else None

    is_hot = (
        sub_count > 0
        and avg_rate is not None
        and avg_rate > Thresholds.SUBSCRIPTION_AVG_MIN
    )

    sale_yoy = _index_yoy(con, city_code, "sale_index")
    jeonse_yoy = _index_yoy(con, city_code, "jeonse_index")

    # 매매 AND 전세 모두 최근 N개월 연속 전월 대비 상승해야 충족
    sale_sustained = _index_sustained_rise(con, city_code, "sale_index")
    jeonse_sustained = _index_sustained_rise(con, city_code, "jeonse_index")
    is_price_up = sale_sustained and jeonse_sustained
    return CurrentSignal(avg_rate, sub_count, sale_yoy, jeonse_yoy, is_hot, is_price_up)


def _index_yoy(con: sqlite3.Connection, city_code: str, column: str) -> float | None:
    rows = list(
        con.execute(
            f"SELECT ym, {column} FROM price_index_monthly "
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


def _index_sustained_rise(con: sqlite3.Connection, city_code: str, column: str) -> bool:
    """최근 N개월 연속으로 전월 대비 상승했는지 확인."""
    n = Thresholds.PRICE_SUSTAIN_MONTHS + 1  # 비교를 위해 1개 더 조회
    rows = list(
        con.execute(
            f"SELECT {column} FROM price_index_monthly "
            f"WHERE city_code=? AND {column} IS NOT NULL ORDER BY ym DESC LIMIT ?",
            (city_code, n),
        )
    )
    if len(rows) < Thresholds.PRICE_SUSTAIN_MONTHS + 1:
        return False
    # 최신순으로 정렬되어 있으므로 역순으로 비교
    values = [r[0] for r in reversed(rows)]
    return all(values[i] > values[i - 1] for i in range(1, len(values)))


def _ym_minus_months(ym: str, months: int) -> str:
    y = int(ym[:4])
    m = int(ym[4:6])
    total = y * 12 + (m - 1) - months
    return f"{total // 12:04d}{total % 12 + 1:02d}"
