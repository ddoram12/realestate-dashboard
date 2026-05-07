"""활황 예상지역 판정 (4신호 중 ≥ 3개 충족)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable

from config import cities as cities_module
from config.settings import Thresholds
from src.analysis import current as current_mod
from src.analysis import demand as demand_mod
from src.analysis import supply as supply_mod
from src.storage.models import upsert_signal


def evaluate_all(con: sqlite3.Connection) -> list[dict]:
    """모든 도시에 대해 신호를 계산하고 ``city_signals`` 에 저장."""
    now = datetime.now().isoformat(timespec="seconds")
    results: list[dict] = []

    for city in cities_module.CITIES:
        d = demand_mod.evaluate(con, city.code)
        s = supply_mod.evaluate(con, city.code)
        c = current_mod.evaluate(con, city.code)

        signals = {
            "demand_up": int(d.is_up),
            "unsold_down": int(s.is_unsold_down),
            "subscription_hot": int(c.is_subscription_hot),
            "price_up": int(c.is_price_up),
        }
        total = sum(signals.values())
        # price_up 은 필수 조건 — 미충족 시 다른 조건 관계없이 탈락
        is_hot = int(total >= Thresholds.HOTSPOT_SIGNAL_MIN and signals["price_up"] == 1)

        detail = {
            "household_growth": d.household_growth,
            "population_growth": d.population_growth,
            "dev_news_count": d.dev_news_count,
            "unsold_slope": s.unsold_slope,
            "latest_unsold_total": s.latest_unsold_total,
            "subscription_count": c.subscription_count,
            "avg_competition_rate": c.avg_competition_rate,
            "sale_yoy": c.sale_yoy,
            "jeonse_yoy": c.jeonse_yoy,
        }

        row = {
            "city_code": city.code,
            "evaluated_at": now,
            "demand_up": signals["demand_up"],
            "unsold_down": signals["unsold_down"],
            "subscription_hot": signals["subscription_hot"],
            "price_up": signals["price_up"],
            "total_score": total,
            "is_hotspot": is_hot,
            "detail": detail,
        }
        upsert_signal(con, row)
        results.append(row)

    con.commit()
    return results
