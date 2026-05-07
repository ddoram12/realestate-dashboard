"""테이블별 upsert 헬퍼.

API 클라이언트가 반환한 DataFrame/dict 리스트를 멱등하게 저장.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Iterable, Sequence


# ─── population ────────────────────────────────────────────────
def upsert_population(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO population_monthly (city_code, ym, population, households)
        VALUES (:city_code, :ym, :population, :households)
        ON CONFLICT(city_code, ym) DO UPDATE SET
            population=excluded.population,
            households=excluded.households
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── unsold ────────────────────────────────────────────────────
def upsert_unsold(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO unsold_monthly (city_code, ym, before_completion, after_completion)
        VALUES (:city_code, :ym, :before_completion, :after_completion)
        ON CONFLICT(city_code, ym) DO UPDATE SET
            before_completion=excluded.before_completion,
            after_completion=excluded.after_completion
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── supply ────────────────────────────────────────────────────
def upsert_supply(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO supply_yearly (city_code, year, completed_units, planned_units)
        VALUES (:city_code, :year, :completed_units, :planned_units)
        ON CONFLICT(city_code, year) DO UPDATE SET
            completed_units=COALESCE(excluded.completed_units, supply_yearly.completed_units),
            planned_units=COALESCE(excluded.planned_units, supply_yearly.planned_units)
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── subscription ──────────────────────────────────────────────
def upsert_subscription(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO subscription
            (announce_no, city_code, complex_name, house_type,
             supply_units, applicants, competition_rate, announce_date)
        VALUES
            (:announce_no, :city_code, :complex_name, :house_type,
             :supply_units, :applicants, :competition_rate, :announce_date)
        ON CONFLICT(announce_no) DO UPDATE SET
            complex_name=excluded.complex_name,
            supply_units=excluded.supply_units,
            applicants=excluded.applicants,
            competition_rate=excluded.competition_rate,
            announce_date=excluded.announce_date
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── price index ───────────────────────────────────────────────
def upsert_price_index(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO price_index_monthly (city_code, ym, sale_index, jeonse_index)
        VALUES (:city_code, :ym, :sale_index, :jeonse_index)
        ON CONFLICT(city_code, ym) DO UPDATE SET
            sale_index=COALESCE(excluded.sale_index, price_index_monthly.sale_index),
            jeonse_index=COALESCE(excluded.jeonse_index, price_index_monthly.jeonse_index)
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── dev news ──────────────────────────────────────────────────
def insert_dev_news(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    sql = """
        INSERT OR IGNORE INTO dev_news
            (city_code, published_at, title, url, source, keyword_hits)
        VALUES
            (:city_code, :published_at, :title, :url, :source, :keyword_hits)
    """
    cur = con.executemany(sql, list(rows))
    return cur.rowcount


# ─── signals ───────────────────────────────────────────────────
def upsert_signal(con: sqlite3.Connection, row: dict) -> None:
    if isinstance(row.get("detail"), (dict, list)):
        row = {**row, "detail_json": json.dumps(row.pop("detail"), ensure_ascii=False)}
    sql = """
        INSERT INTO city_signals
            (city_code, evaluated_at, demand_up, unsold_down,
             subscription_hot, price_up, total_score, is_hotspot, detail_json)
        VALUES
            (:city_code, :evaluated_at, :demand_up, :unsold_down,
             :subscription_hot, :price_up, :total_score, :is_hotspot, :detail_json)
        ON CONFLICT(city_code) DO UPDATE SET
            evaluated_at=excluded.evaluated_at,
            demand_up=excluded.demand_up,
            unsold_down=excluded.unsold_down,
            subscription_hot=excluded.subscription_hot,
            price_up=excluded.price_up,
            total_score=excluded.total_score,
            is_hotspot=excluded.is_hotspot,
            detail_json=excluded.detail_json
    """
    con.execute(sql, row)


# ─── select helpers ────────────────────────────────────────────
def fetch_signals(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT s.*, c.name, c.sido, c.population, c.lat, c.lng
            FROM city_signals s
            JOIN cities c ON c.code = s.city_code
            ORDER BY s.is_hotspot DESC, s.total_score DESC, c.population DESC
            """
        )
    )


def fetch_population(con: sqlite3.Connection, city_code: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            "SELECT ym, population, households FROM population_monthly "
            "WHERE city_code=? ORDER BY ym",
            (city_code,),
        )
    )


def fetch_unsold(con: sqlite3.Connection, city_code: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            "SELECT ym, before_completion, after_completion FROM unsold_monthly "
            "WHERE city_code=? ORDER BY ym",
            (city_code,),
        )
    )


def fetch_supply(con: sqlite3.Connection, city_code: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            "SELECT year, completed_units, planned_units FROM supply_yearly "
            "WHERE city_code=? ORDER BY year",
            (city_code,),
        )
    )


def fetch_subscription(
    con: sqlite3.Connection, city_code: str, since: str | None = None
) -> list[sqlite3.Row]:
    if since:
        return list(
            con.execute(
                "SELECT * FROM subscription WHERE city_code=? AND announce_date>=? "
                "ORDER BY announce_date DESC",
                (city_code, since),
            )
        )
    return list(
        con.execute(
            "SELECT * FROM subscription WHERE city_code=? ORDER BY announce_date DESC",
            (city_code,),
        )
    )


def fetch_price_index(con: sqlite3.Connection, city_code: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            "SELECT ym, sale_index, jeonse_index FROM price_index_monthly "
            "WHERE city_code=? ORDER BY ym",
            (city_code,),
        )
    )


def fetch_dev_news(
    con: sqlite3.Connection, city_code: str, limit: int = 50
) -> list[sqlite3.Row]:
    return list(
        con.execute(
            "SELECT * FROM dev_news WHERE city_code=? "
            "ORDER BY published_at DESC LIMIT ?",
            (city_code, limit),
        )
    )
