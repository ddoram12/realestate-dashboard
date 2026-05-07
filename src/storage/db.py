"""SQLite 연결과 스키마 초기화."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config.settings import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS cities (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sido        TEXT NOT NULL,
    population  INTEGER,
    lat         REAL,
    lng         REAL
);

CREATE TABLE IF NOT EXISTS population_monthly (
    city_code   TEXT NOT NULL,
    ym          TEXT NOT NULL,           -- 'YYYYMM'
    population  INTEGER,
    households  INTEGER,
    PRIMARY KEY (city_code, ym),
    FOREIGN KEY (city_code) REFERENCES cities(code)
);

CREATE TABLE IF NOT EXISTS unsold_monthly (
    city_code           TEXT NOT NULL,
    ym                  TEXT NOT NULL,
    before_completion   INTEGER,         -- 준공 전 미분양
    after_completion    INTEGER,         -- 준공 후 미분양
    PRIMARY KEY (city_code, ym)
);

CREATE TABLE IF NOT EXISTS supply_yearly (
    city_code        TEXT NOT NULL,
    year             INTEGER NOT NULL,
    completed_units  INTEGER,            -- 실제 입주(준공) 세대
    planned_units    INTEGER,            -- 예정 입주 세대
    PRIMARY KEY (city_code, year)
);

CREATE TABLE IF NOT EXISTS subscription (
    announce_no       TEXT NOT NULL,     -- 공고번호 + 주택형 구분키
    city_code         TEXT NOT NULL,
    complex_name      TEXT,
    house_type        TEXT,              -- 주택형 (e.g. 84A)
    supply_units      INTEGER,
    applicants        INTEGER,
    competition_rate  REAL,
    announce_date     TEXT,              -- 'YYYY-MM-DD'
    PRIMARY KEY (announce_no)
);

CREATE TABLE IF NOT EXISTS price_index_monthly (
    city_code     TEXT NOT NULL,
    ym            TEXT NOT NULL,
    sale_index    REAL,                  -- 매매가격지수
    jeonse_index  REAL,                  -- 전세가격지수
    PRIMARY KEY (city_code, ym)
);

CREATE TABLE IF NOT EXISTS dev_news (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    city_code      TEXT NOT NULL,
    published_at   TEXT,                 -- ISO timestamp
    title          TEXT,
    url            TEXT UNIQUE,
    source         TEXT,
    keyword_hits   TEXT                  -- 콤마로 구분된 매칭 키워드
);

CREATE TABLE IF NOT EXISTS city_signals (
    city_code         TEXT PRIMARY KEY,
    evaluated_at      TEXT NOT NULL,     -- ISO timestamp
    demand_up         INTEGER NOT NULL,
    unsold_down       INTEGER NOT NULL,
    subscription_hot  INTEGER NOT NULL,
    price_up          INTEGER NOT NULL,
    total_score       INTEGER NOT NULL,
    is_hotspot        INTEGER NOT NULL,
    detail_json       TEXT                -- 신호별 근거 수치(JSON)
);

CREATE INDEX IF NOT EXISTS idx_subscription_city_date
    ON subscription(city_code, announce_date);
CREATE INDEX IF NOT EXISTS idx_dev_news_city_date
    ON dev_news(city_code, published_at);
"""


def init_db() -> None:
    """스키마가 없으면 생성하고 cities 시드를 채움."""
    from config.cities import CITIES

    with connect() as con:
        con.executescript(SCHEMA)
        con.executemany(
            """
            INSERT INTO cities (code, name, sido, population, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                sido=excluded.sido,
                lat=excluded.lat,
                lng=excluded.lng
            """,
            [(c.code, c.name, c.sido, c.population, c.lat, c.lng) for c in CITIES],
        )
        con.commit()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()
