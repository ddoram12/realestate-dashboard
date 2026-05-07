"""공급 신호 (미분양 추이, 공급 실적·예정)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np

from config.settings import Thresholds, Window


@dataclass
class SupplySignal:
    unsold_slope: float | None          # 최근 6개월 미분양 총량 회귀 기울기
    latest_unsold_total: int | None
    unsold_ratio: float | None          # 최신월 미분양 / 세대수
    is_unsold_down: bool


def evaluate(con: sqlite3.Connection, city_code: str) -> SupplySignal:
    rows = list(
        con.execute(
            """
            SELECT ym,
                   COALESCE(before_completion, 0) + COALESCE(after_completion, 0) AS total
            FROM unsold_monthly
            WHERE city_code = ?
              AND (before_completion IS NOT NULL OR after_completion IS NOT NULL)
            ORDER BY ym
            """,
            (city_code,),
        )
    )
    if len(rows) < 3:
        return SupplySignal(None, None, None, False)

    window = rows[-Thresholds.UNSOLD_TREND_WINDOW_MONTHS:]
    latest = window[-1]["total"]

    if len(window) < 3:
        return SupplySignal(None, latest, None, False)

    xs = np.arange(len(window), dtype=float)
    ys = np.array([r["total"] for r in window], dtype=float)
    slope = float(np.polyfit(xs, ys, 1)[0])

    # 세대수 대비 미분양 비율
    hh_row = con.execute(
        """
        SELECT households FROM population_monthly
        WHERE city_code = ? AND households IS NOT NULL
        ORDER BY ym DESC LIMIT 1
        """,
        (city_code,),
    ).fetchone()
    households = int(hh_row[0]) if hh_row and hh_row[0] else 0
    ratio = (latest / households) if households > 0 else None

    # 감소 추세 + 절대 수준(세대수 대비 0.5% 이하) 모두 충족
    is_down = (
        slope < Thresholds.UNSOLD_SLOPE_MAX
        and (ratio is None or ratio < Thresholds.UNSOLD_RATIO_MAX)
    )
    return SupplySignal(slope, latest, ratio, is_down)


def supply_history_table(con: sqlite3.Connection, city_code: str) -> list[dict]:
    """과거 N년 공급 실적 + 향후 N년 공급 예정."""
    rows = list(
        con.execute(
            "SELECT year, completed_units, planned_units FROM supply_yearly "
            "WHERE city_code=? ORDER BY year",
            (city_code,),
        )
    )
    return [dict(r) for r in rows]
