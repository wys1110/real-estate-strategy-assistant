"""SQLite 스냅샷 저장소.

수집(배치)과 조회(앱)를 분리하기 위한 로컬 저장 계층입니다.
- 수집 CLI가 매물/실거래/정비사업을 이 DB에 기록합니다.
- Streamlit 앱은 네트워크 없이 이 DB만 읽어 즉시 응답합니다.

stdlib `sqlite3`만 사용합니다 (third-party 런타임 의존성 없음).
각 레코드는 출처(source)와 수집시각(collected_at)을 보존합니다.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "snapshots",
    "realestate.db",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    district      TEXT NOT NULL,
    listing_id    TEXT,
    trade_type    TEXT,
    listing_type  TEXT,
    name          TEXT,
    area_sqm      TEXT,
    floor         TEXT,
    price_manwon  TEXT,
    price_krw     INTEGER,
    agency        TEXT,
    note          TEXT,
    source        TEXT,
    detail_url    TEXT,
    fetched_at    TEXT,
    collected_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    district       TEXT NOT NULL,
    deal_ymd       TEXT NOT NULL,
    property_type  TEXT NOT NULL,
    deal_year      INTEGER,
    deal_month     INTEGER,
    deal_day       INTEGER,
    name           TEXT,
    dong           TEXT,
    lot_number     TEXT,
    area_sqm       REAL,
    floor          INTEGER,
    build_year     INTEGER,
    price_manwon   INTEGER,
    price_krw      INTEGER,
    fetched_at     TEXT,
    collected_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    district      TEXT NOT NULL,
    biz_type      TEXT,
    name          TEXT,
    address       TEXT,
    stage         TEXT,
    progress      INTEGER,
    score         REAL,
    fetched_at    TEXT,
    collected_at  TEXT NOT NULL
);

-- 구·종류별 마지막 수집 현황 (출처 인식 UI용)
CREATE TABLE IF NOT EXISTS collections (
    district      TEXT NOT NULL,
    kind          TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    count         INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'ok',
    collected_at  TEXT NOT NULL,
    PRIMARY KEY (district, kind, detail)
);

CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);
CREATE INDEX IF NOT EXISTS idx_tx_district ON transactions(district, deal_ymd, property_type);
CREATE INDEX IF NOT EXISTS idx_zones_district ON zones(district);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """DB 연결을 열고 스키마를 보장합니다 (디렉터리 자동 생성)."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _record_collection(
    conn: sqlite3.Connection, district: str, kind: str, detail: str, count: int, status: str
) -> None:
    conn.execute(
        "INSERT INTO collections (district, kind, detail, count, status, collected_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(district, kind, detail) DO UPDATE SET "
        "count=excluded.count, status=excluded.status, collected_at=excluded.collected_at",
        (district, kind, detail, count, status, _now()),
    )


# ── 매물 ──────────────────────────────────────────────────────────────────────
def save_listings(conn: sqlite3.Connection, district: str, listings: Sequence) -> int:
    """해당 구의 매물을 통째로 교체합니다 (스냅샷 의미)."""
    collected_at = _now()
    with conn:
        conn.execute("DELETE FROM listings WHERE district = ?", (district,))
        conn.executemany(
            "INSERT INTO listings (district, listing_id, trade_type, listing_type, name, "
            "area_sqm, floor, price_manwon, price_krw, agency, note, source, detail_url, "
            "fetched_at, collected_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (district, li.listing_id, li.trade_type, li.listing_type, li.name,
                 li.area_sqm, li.floor, li.price_manwon, li.price_krw, li.agency,
                 li.note, li.source, li.detail_url, li.fetched_at, collected_at)
                for li in listings
            ],
        )
        _record_collection(conn, district, "매물", "", len(listings), "ok")
    return len(listings)


def load_listings(conn: sqlite3.Connection, district: str) -> List[dict]:
    cur = conn.execute("SELECT * FROM listings WHERE district = ?", (district,))
    return [dict(r) for r in cur.fetchall()]


# ── 실거래 ────────────────────────────────────────────────────────────────────
def save_transactions(
    conn: sqlite3.Connection, district: str, deal_ymd: str, property_type: str, txs: Sequence
) -> int:
    """해당 구·계약년월·유형의 실거래를 교체합니다."""
    collected_at = _now()
    with conn:
        conn.execute(
            "DELETE FROM transactions WHERE district = ? AND deal_ymd = ? AND property_type = ?",
            (district, deal_ymd, property_type),
        )
        conn.executemany(
            "INSERT INTO transactions (district, deal_ymd, property_type, deal_year, deal_month, "
            "deal_day, name, dong, lot_number, area_sqm, floor, build_year, price_manwon, "
            "price_krw, fetched_at, collected_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (district, deal_ymd, property_type, t.deal_year, t.deal_month, t.deal_day,
                 t.name, t.dong, t.lot_number, t.area_sqm, t.floor, t.build_year,
                 t.price_manwon, t.price_krw, t.fetched_at, collected_at)
                for t in txs
            ],
        )
        _record_collection(conn, district, "실거래", f"{deal_ymd}/{property_type}", len(txs), "ok")
    return len(txs)


def load_transactions(
    conn: sqlite3.Connection,
    district: str,
    deal_ymd: Optional[str] = None,
    property_type: Optional[str] = None,
) -> List[dict]:
    sql = "SELECT * FROM transactions WHERE district = ?"
    params: List[object] = [district]
    if deal_ymd:
        sql += " AND deal_ymd = ?"
        params.append(deal_ymd)
    if property_type:
        sql += " AND property_type = ?"
        params.append(property_type)
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ── 정비사업(재개발) ──────────────────────────────────────────────────────────
def save_zones(conn: sqlite3.Connection, district: str, zones: Sequence) -> int:
    collected_at = _now()
    with conn:
        conn.execute("DELETE FROM zones WHERE district = ?", (district,))
        conn.executemany(
            "INSERT INTO zones (district, biz_type, name, address, stage, progress, score, "
            "fetched_at, collected_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (district, z.biz_type, z.name, z.address, z.stage, z.progress, z.score,
                 collected_at, collected_at)
                for z in zones
            ],
        )
        _record_collection(conn, district, "재개발", "", len(zones), "ok")
    return len(zones)


def load_zones(conn: sqlite3.Connection, district: str) -> List[dict]:
    cur = conn.execute("SELECT * FROM zones WHERE district = ? ORDER BY score DESC", (district,))
    return [dict(r) for r in cur.fetchall()]


# ── 수집 현황 ─────────────────────────────────────────────────────────────────
def record_failure(conn: sqlite3.Connection, district: str, kind: str, detail: str, symptom: str) -> None:
    """수집 실패를 증상과 함께 기록합니다 (조용한 폴백 금지 — CLAUDE.md)."""
    with conn:
        _record_collection(conn, district, kind, detail, 0, f"fail: {symptom}"[:200])


def collection_status(conn: sqlite3.Connection, district: Optional[str] = None) -> List[dict]:
    if district:
        cur = conn.execute(
            "SELECT * FROM collections WHERE district = ? ORDER BY kind, detail", (district,)
        )
    else:
        cur = conn.execute("SELECT * FROM collections ORDER BY district, kind, detail")
    return [dict(r) for r in cur.fetchall()]


def collected_districts(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT DISTINCT district FROM collections ORDER BY district")
    return [r["district"] for r in cur.fetchall()]


def summary(conn: sqlite3.Connection) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for table in ("listings", "transactions", "zones"):
        out[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    return out
