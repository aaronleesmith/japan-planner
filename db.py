import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "japan.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS places (
                id                  INTEGER PRIMARY KEY,
                name                TEXT NOT NULL,
                category            TEXT,   -- food, sightseeing, transportation, lodging
                city                TEXT,
                neighborhood        TEXT,
                address             TEXT,
                website_url         TEXT,
                maps_url            TEXT,
                maps_place_id       TEXT,   -- Google Maps Place ID e.g. ChIJN1t_tDeuEmsRUsoyG83frY4
                lat                 REAL,
                lon                 REAL,
                reservation_status  TEXT,   -- booked, reservations_accepted, no_reservations
                booked_time         TEXT,   -- ISO 8601: YYYY-MM-DD HH:MM
                is_family           INTEGER DEFAULT 0,  -- 1 = whole family activity
                food_tier           INTEGER,  -- 1-3, food only
                food_type           TEXT,     -- meal, coffee, dessert, cocktails; food only
                food_cuisine        TEXT,     -- Sushi, Ramen, Udon, etc.; food only
                priority            INTEGER,  -- 1=must-do, 2=want-to-do, 3=nice-to-have
                cuisine_rank        INTEGER,  -- preference order within a food category (1=most preferred)
                est_duration_min    INTEGER,
                mon_open            TEXT,     -- HH:MM, NULL = closed
                mon_close           TEXT,
                tue_open            TEXT,
                tue_close           TEXT,
                wed_open            TEXT,
                wed_close           TEXT,
                thu_open            TEXT,
                thu_close           TEXT,
                fri_open            TEXT,
                fri_close           TEXT,
                sat_open            TEXT,
                sat_close           TEXT,
                sun_open            TEXT,
                sun_close           TEXT,
                notes               TEXT
            );

            CREATE TABLE IF NOT EXISTS days (
                id      INTEGER PRIMARY KEY,
                date    TEXT NOT NULL UNIQUE,
                title   TEXT,
                city    TEXT,
                notes   TEXT
            );

            CREATE TABLE IF NOT EXISTS day_items (
                id          INTEGER PRIMARY KEY,
                day_id      INTEGER NOT NULL REFERENCES days(id),
                position    INTEGER NOT NULL DEFAULT 0,
                place_id    INTEGER REFERENCES places(id),
                title       TEXT NOT NULL,
                type        TEXT,
                start_time  TEXT,
                end_time    TEXT,
                duration_min INTEGER,
                cost_jpy    INTEGER,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                created_at  TEXT NOT NULL,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshot_days (
                id          INTEGER PRIMARY KEY,
                snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                orig_day_id INTEGER,
                date        TEXT NOT NULL,
                title       TEXT,
                city        TEXT,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshot_items (
                id              INTEGER PRIMARY KEY,
                snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                snapshot_day_id INTEGER NOT NULL REFERENCES snapshot_days(id) ON DELETE CASCADE,
                orig_item_id    INTEGER,
                position        INTEGER NOT NULL DEFAULT 0,
                place_id        INTEGER,
                title           TEXT NOT NULL,
                type            TEXT,
                start_time      TEXT,
                end_time        TEXT,
                duration_min    INTEGER,
                cost_jpy        INTEGER,
                notes           TEXT
            );
        """)
    print(f"DB initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
