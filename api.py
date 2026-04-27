#!/usr/bin/env python3
"""
JSON API for the Japan trip planner.

Usage:
    echo '<json>' | uv run api.py

Every request is a JSON object with at minimum:
    {"resource": "places|days|items|travel", "action": "add|list|show|update|delete|directions", ...fields}

Every response is a JSON object or array written to stdout.
Errors return {"error": "..."} with a non-zero exit code.
"""
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from db import connect

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_PLACES_FIELDS = [
    "name", "category", "city", "neighborhood", "address",
    "website_url", "maps_url", "maps_place_id", "lat", "lon",
    "reservation_status", "booked_time",
    "is_family", "food_tier", "food_type", "food_cuisine",
    "priority", "cuisine_rank", "est_duration_min",
    "mon_open", "mon_close", "tue_open", "tue_close",
    "wed_open", "wed_close", "thu_open", "thu_close",
    "fri_open", "fri_close", "sat_open", "sat_close",
    "sun_open", "sun_close", "notes",
]

_DAYS_FIELDS = ["date", "title", "city", "notes"]

_ITEMS_FIELDS = [
    "day_id", "position", "place_id", "title", "type",
    "start_time", "end_time", "duration_min", "cost_jpy", "notes",
]


def row_to_dict(row) -> dict:
    return dict(row) if row else None


def err(msg: str, code: int = 1) -> dict:
    print(json.dumps({"error": msg}, indent=2))
    sys.exit(code)


# ── places ─────────────────────────────────────────────────────────────────────

def places_add(req: dict) -> dict:
    data = {f: req[f] for f in _PLACES_FIELDS if f in req}
    if "name" not in data:
        err("'name' is required")
    cols = ", ".join(data)
    placeholders = ", ".join("?" * len(data))
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO places ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        return row_to_dict(conn.execute("SELECT * FROM places WHERE id = ?", (cur.lastrowid,)).fetchone())


def places_list(req: dict) -> list:
    clauses: list[str] = []
    params: list = []

    # exact matches
    for col in ("category", "city", "priority", "food_type", "food_cuisine",
                "food_tier", "reservation_status"):
        # --needs-booking shorthand
        if col == "reservation_status" and req.get("needs_booking"):
            clauses.append("reservation_status = ?")
            params.append("reservations_accepted")
            continue
        if col in req and req[col] is not None:
            clauses.append(f"{col} = ?")
            params.append(req[col])

    if "is_family" in req and req["is_family"] is not None:
        clauses.append("is_family = ?")
        params.append(int(req["is_family"]))

    # range / ceiling
    if "max_priority" in req:
        clauses.append("priority <= ?")
        params.append(req["max_priority"])
    if "max_food_tier" in req:
        clauses.append("food_tier <= ?")
        params.append(req["max_food_tier"])

    # full-text search
    if "search" in req:
        pattern = f"%{req['search']}%"
        clauses.append(
            "(name LIKE ? OR neighborhood LIKE ? OR address LIKE ? OR food_cuisine LIKE ? OR notes LIKE ?)"
        )
        params.extend([pattern] * 5)

    # availability
    day = None
    if "open_on_date" in req:
        try:
            day = _WEEKDAYS[datetime.strptime(req["open_on_date"], "%Y-%m-%d").weekday()]
        except ValueError:
            err(f"invalid date '{req['open_on_date']}', expected YYYY-MM-DD")
    elif "open_on_day" in req:
        day = req["open_on_day"].lower()
        if day not in _WEEKDAYS:
            err(f"invalid day '{req['open_on_day']}', expected mon/tue/wed/thu/fri/sat/sun")

    if day:
        clauses.append(f"{day}_open IS NOT NULL")
        if "open_at" in req:
            clauses.append(f"{day}_open <= ?")
            clauses.append(f"{day}_close >= ?")
            params.extend([req["open_at"], req["open_at"]])

    # unscheduled
    if req.get("unscheduled"):
        clauses.append("id NOT IN (SELECT DISTINCT place_id FROM day_items WHERE place_id IS NOT NULL)")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    # proximity filter — resolved after the main query
    near_lat = near_lon = near_label = None
    radius_m = req.get("radius_m", 800)

    if "near_id" in req or "near" in req:
        import googlemaps
        key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not key or key == "your_key_here":
            err("GOOGLE_MAPS_API_KEY is required for proximity search")
        try:
            gmaps = googlemaps.Client(key=key)
            if "near_id" in req:
                with connect() as conn:
                    ref = conn.execute(
                        "SELECT name, city, neighborhood, address, maps_place_id, lat, lon FROM places WHERE id = ?",
                        (req["near_id"],),
                    ).fetchone()
                if not ref:
                    err(f"no place with id {req['near_id']}")
                if ref["lat"] and ref["lon"]:
                    near_lat, near_lon, near_label = ref["lat"], ref["lon"], ref["name"]
                else:
                    near_lat, near_lon, near_label = _resolve_latlng(gmaps, {"id": req["near_id"]})
            else:
                result = gmaps.geocode(req["near"] + ", Japan")
                if not result:
                    err(f"could not geocode '{req['near']}'")
                loc = result[0]["geometry"]["location"]
                near_lat, near_lon, near_label = loc["lat"], loc["lng"], req["near"]
        except Exception as e:
            err(f"proximity lookup failed: {e}")

    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM places {where} ORDER BY priority NULLS LAST, name", params
        ).fetchall()
        results = [row_to_dict(r) for r in rows]

    if near_lat is not None:
        enriched, skipped = [], 0
        for r in results:
            if r["lat"] and r["lon"]:
                r["distance_m"] = _haversine_m(near_lat, near_lon, r["lat"], r["lon"])
                if r["distance_m"] <= radius_m:
                    enriched.append(r)
            else:
                skipped += 1
        enriched.sort(key=lambda x: x["distance_m"])
        if skipped:
            enriched.append({"_note": f"{skipped} place(s) skipped — no coordinates stored (run geocode first)"})
        return enriched

    return results


def places_show(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        row = conn.execute("SELECT * FROM places WHERE id = ?", (req["id"],)).fetchone()
        if not row:
            err(f"no place with id {req['id']}")
        return row_to_dict(row)


def places_update(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    # Any field present in req (even null) is written; absent fields are left alone.
    updates = {f: req[f] for f in _PLACES_FIELDS if f in req}
    if not updates:
        err("no fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(
            f"UPDATE places SET {set_clause} WHERE id = ?",
            (*updates.values(), req["id"]),
        )
        return row_to_dict(conn.execute("SELECT * FROM places WHERE id = ?", (req["id"],)).fetchone())


def places_delete(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        conn.execute("DELETE FROM places WHERE id = ?", (req["id"],))
        return {"deleted": req["id"]}


# ── days ───────────────────────────────────────────────────────────────────────

def days_add(req: dict) -> dict:
    if "date" not in req:
        err("'date' is required")
    data = {f: req[f] for f in _DAYS_FIELDS if f in req}
    cols = ", ".join(data)
    placeholders = ", ".join("?" * len(data))
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO days ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        return row_to_dict(conn.execute("SELECT * FROM days WHERE id = ?", (cur.lastrowid,)).fetchone())


def days_list(req: dict) -> list:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM days ORDER BY date").fetchall()
        return [row_to_dict(r) for r in rows]


def days_show(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        day = conn.execute("SELECT * FROM days WHERE id = ?", (req["id"],)).fetchone()
        if not day:
            err(f"no day with id {req['id']}")
        items = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.day_id = ?
            ORDER BY i.position
        """, (req["id"],)).fetchall()
        result = row_to_dict(day)
        result["items"] = [row_to_dict(r) for r in items]
        return result


def days_update(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    updates = {f: req[f] for f in ("title", "city", "notes") if f in req}
    if not updates:
        err("no fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(
            f"UPDATE days SET {set_clause} WHERE id = ?",
            (*updates.values(), req["id"]),
        )
        return row_to_dict(conn.execute("SELECT * FROM days WHERE id = ?", (req["id"],)).fetchone())


def days_delete(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        conn.execute("DELETE FROM days WHERE id = ?", (req["id"],))
        return {"deleted": req["id"]}


# ── items ──────────────────────────────────────────────────────────────────────

def items_add(req: dict) -> dict:
    if "day_id" not in req:
        err("'day_id' is required")
    if "title" not in req:
        err("'title' is required")
    data = {f: req[f] for f in _ITEMS_FIELDS if f in req}
    if "position" not in data:
        with connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM day_items WHERE day_id = ?",
                (data["day_id"],),
            ).fetchone()
            data["position"] = row["next"]
    cols = ", ".join(data)
    placeholders = ", ".join("?" * len(data))
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO day_items ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        return row_to_dict(conn.execute("SELECT * FROM day_items WHERE id = ?", (cur.lastrowid,)).fetchone())


def items_list(req: dict) -> list:
    if "day_id" not in req:
        err("'day_id' is required")
    with connect() as conn:
        rows = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.day_id = ?
            ORDER BY i.position
        """, (req["day_id"],)).fetchall()
        return [row_to_dict(r) for r in rows]


def items_show(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        row = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.id = ?
        """, (req["id"],)).fetchone()
        if not row:
            err(f"no item with id {req['id']}")
        return row_to_dict(row)


def items_update(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    updates = {f: req[f] for f in _ITEMS_FIELDS if f in req and f != "day_id"}
    if not updates:
        err("no fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(
            f"UPDATE day_items SET {set_clause} WHERE id = ?",
            (*updates.values(), req["id"]),
        )
        return row_to_dict(conn.execute("SELECT * FROM day_items WHERE id = ?", (req["id"],)).fetchone())


def items_delete(req: dict) -> dict:
    if "id" not in req:
        err("'id' is required")
    with connect() as conn:
        conn.execute("DELETE FROM day_items WHERE id = ?", (req["id"],))
        return {"deleted": req["id"]}


# ── snapshots ──────────────────────────────────────────────────────────────────

def _snapshot_to_dict(conn, snap_row: dict) -> dict:
    """Return a snapshot with its days and items fully expanded."""
    days = conn.execute(
        "SELECT * FROM snapshot_days WHERE snapshot_id = ? ORDER BY date",
        (snap_row["id"],),
    ).fetchall()
    result = dict(snap_row)
    result["days"] = []
    for d in days:
        day = dict(d)
        items = conn.execute(
            """SELECT si.*, p.name AS place_name
               FROM snapshot_items si
               LEFT JOIN places p ON si.place_id = p.id
               WHERE si.snapshot_day_id = ?
               ORDER BY si.position""",
            (d["id"],),
        ).fetchall()
        day["items"] = [dict(i) for i in items]
        result["days"].append(day)
    return result


def snapshots_create(req: dict) -> dict:
    if "name" not in req:
        err("'name' is required")
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM snapshots WHERE name = ?", (req["name"],)
        ).fetchone()
        if existing:
            err(f"snapshot '{req['name']}' already exists — choose a different name or delete it first")

        cur = conn.execute(
            "INSERT INTO snapshots (name, created_at, notes) VALUES (?, datetime('now'), ?)",
            (req["name"], req.get("notes")),
        )
        snap_id = cur.lastrowid

        days = conn.execute("SELECT * FROM days ORDER BY date").fetchall()
        for day in days:
            dcur = conn.execute(
                """INSERT INTO snapshot_days (snapshot_id, orig_day_id, date, title, city, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (snap_id, day["id"], day["date"], day["title"], day["city"], day["notes"]),
            )
            snap_day_id = dcur.lastrowid
            items = conn.execute(
                "SELECT * FROM day_items WHERE day_id = ? ORDER BY position", (day["id"],)
            ).fetchall()
            for item in items:
                conn.execute(
                    """INSERT INTO snapshot_items
                       (snapshot_id, snapshot_day_id, orig_item_id, position, place_id,
                        title, type, start_time, end_time, duration_min, cost_jpy, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snap_id, snap_day_id, item["id"], item["position"], item["place_id"],
                     item["title"], item["type"], item["start_time"], item["end_time"],
                     item["duration_min"], item["cost_jpy"], item["notes"]),
                )

        snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snap_id,)).fetchone()
        return {
            "snapshot": dict(snap),
            "days_saved": len(days),
        }


def snapshots_list(req: dict) -> list:
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.*, COUNT(DISTINCT sd.id) AS day_count FROM snapshots s "
            "LEFT JOIN snapshot_days sd ON sd.snapshot_id = s.id "
            "GROUP BY s.id ORDER BY s.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def snapshots_show(req: dict) -> dict:
    if "id" not in req and "name" not in req:
        err("'id' or 'name' is required")
    with connect() as conn:
        if "id" in req:
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (req["id"],)).fetchone()
        else:
            snap = conn.execute("SELECT * FROM snapshots WHERE name = ?", (req["name"],)).fetchone()
        if not snap:
            err(f"snapshot not found")
        return _snapshot_to_dict(conn, dict(snap))


def snapshots_restore(req: dict) -> dict:
    """Replace current days and items with a snapshot. Auto-saves current state first."""
    if "id" not in req and "name" not in req:
        err("'id' or 'name' is required")

    with connect() as conn:
        if "id" in req:
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (req["id"],)).fetchone()
        else:
            snap = conn.execute("SELECT * FROM snapshots WHERE name = ?", (req["name"],)).fetchone()
        if not snap:
            err("snapshot not found")

        # Auto-save current state unless caller opts out
        auto_save_name = None
        if not req.get("skip_auto_save"):
            auto_save_name = f"_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            snapshots_create({"name": auto_save_name, "notes": f"auto-saved before restoring '{snap['name']}'"})

        # Delete current days and items
        conn.execute("DELETE FROM day_items")
        conn.execute("DELETE FROM days")

        # Restore from snapshot
        snap_days = conn.execute(
            "SELECT * FROM snapshot_days WHERE snapshot_id = ? ORDER BY date",
            (snap["id"],),
        ).fetchall()

        for sd in snap_days:
            dcur = conn.execute(
                "INSERT INTO days (date, title, city, notes) VALUES (?, ?, ?, ?)",
                (sd["date"], sd["title"], sd["city"], sd["notes"]),
            )
            new_day_id = dcur.lastrowid
            items = conn.execute(
                "SELECT * FROM snapshot_items WHERE snapshot_day_id = ? ORDER BY position",
                (sd["id"],),
            ).fetchall()
            for item in items:
                conn.execute(
                    """INSERT INTO day_items
                       (day_id, position, place_id, title, type,
                        start_time, end_time, duration_min, cost_jpy, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (new_day_id, item["position"], item["place_id"], item["title"],
                     item["type"], item["start_time"], item["end_time"],
                     item["duration_min"], item["cost_jpy"], item["notes"]),
                )

    return {
        "restored": snap["name"],
        "days_restored": len(snap_days),
        "auto_saved_as": auto_save_name,
    }


def snapshots_diff(req: dict) -> dict:
    """Compare two snapshots, or a snapshot against the current live plan.
    Pass 'a' and optionally 'b' (id or name). If 'b' is omitted, compares 'a' vs current."""
    if "a" not in req:
        err("'a' (snapshot id or name) is required")

    def _load_snap(ref) -> dict:
        """Load snapshot days keyed by date."""
        with connect() as conn:
            if isinstance(ref, int):
                snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (ref,)).fetchone()
            else:
                snap = conn.execute("SELECT * FROM snapshots WHERE name = ?", (ref,)).fetchone()
            if not snap:
                err(f"snapshot '{ref}' not found")
            return _snapshot_to_dict(conn, dict(snap))

    def _load_current() -> dict:
        """Load current live plan in the same shape as a snapshot."""
        with connect() as conn:
            days = conn.execute("SELECT * FROM days ORDER BY date").fetchall()
            result = {"name": "current", "days": []}
            for d in days:
                day = dict(d)
                items = conn.execute(
                    """SELECT i.*, p.name AS place_name
                       FROM day_items i LEFT JOIN places p ON i.place_id = p.id
                       WHERE i.day_id = ? ORDER BY i.position""",
                    (d["id"],),
                ).fetchall()
                day["items"] = [dict(i) for i in items]
                result["days"].append(day)
        return result

    snap_a = _load_snap(req["a"])
    snap_b = _load_current() if "b" not in req else _load_snap(req["b"])

    days_a = {d["date"]: d for d in snap_a["days"]}
    days_b = {d["date"]: d for d in snap_b["days"]}
    all_dates = sorted(set(days_a) | set(days_b))

    changes = []
    for date in all_dates:
        if date not in days_a:
            changes.append({"date": date, "change": "added_in_b", "day": days_b[date]})
        elif date not in days_b:
            changes.append({"date": date, "change": "removed_in_b", "day": days_a[date]})
        else:
            da, db = days_a[date], days_b[date]
            day_changed = da["title"] != db["title"] or da["city"] != db["city"] or da["notes"] != db["notes"]
            titles_a = [i["title"] for i in da["items"]]
            titles_b = [i["title"] for i in db["items"]]
            items_added   = [t for t in titles_b if t not in titles_a]
            items_removed = [t for t in titles_a if t not in titles_b]
            reordered = titles_a != titles_b and not items_added and not items_removed

            if day_changed or items_added or items_removed or reordered:
                changes.append({
                    "date": date,
                    "change": "modified",
                    "day_fields_changed": day_changed,
                    "items_added": items_added,
                    "items_removed": items_removed,
                    "reordered": reordered,
                })
            else:
                changes.append({"date": date, "change": "unchanged"})

    return {
        "a": snap_a["name"],
        "b": snap_b["name"],
        "total_dates": len(all_dates),
        "unchanged": sum(1 for c in changes if c["change"] == "unchanged"),
        "modified": sum(1 for c in changes if c["change"] == "modified"),
        "added_in_b": sum(1 for c in changes if c["change"] == "added_in_b"),
        "removed_in_b": sum(1 for c in changes if c["change"] == "removed_in_b"),
        "changes": changes,
    }


def snapshots_delete(req: dict) -> dict:
    if "id" not in req and "name" not in req:
        err("'id' or 'name' is required")
    with connect() as conn:
        if "id" in req:
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (req["id"],)).fetchone()
        else:
            snap = conn.execute("SELECT * FROM snapshots WHERE name = ?", (req["name"],)).fetchone()
        if not snap:
            err("snapshot not found")
        conn.execute("DELETE FROM snapshots WHERE id = ?", (snap["id"],))
        return {"deleted": snap["name"]}


# ── geocode ────────────────────────────────────────────────────────────────────

def places_geocode(req: dict) -> dict:
    """Search Google Places for a DB place and return up to 3 candidates with Place IDs.
    Does not write anything — caller must confirm with places update."""
    import googlemaps

    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key or key == "your_key_here":
        err("GOOGLE_MAPS_API_KEY is not set — add it to .env")
    if "id" not in req:
        err("'id' is required")

    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, city, neighborhood, address, maps_place_id FROM places WHERE id = ?",
            (req["id"],),
        ).fetchone()
        if not row:
            err(f"no place with id {req['id']}")

    # Build the search query — caller may override with a more specific string
    if "query" in req:
        query = req["query"]
    else:
        parts = [p for p in [row["name"], row["neighborhood"] or row["address"], row["city"], "Japan"] if p]
        query = ", ".join(parts)

    try:
        gmaps = googlemaps.Client(key=key)
        results = gmaps.places(query)
    except Exception as e:
        err(f"Google Maps API error: {e}")

    candidates = []
    for r in results.get("results", [])[:3]:
        pid = r["place_id"]
        loc = r.get("geometry", {}).get("location", {})
        candidates.append({
            "name": r.get("name", ""),
            "address": r.get("formatted_address", ""),
            "maps_place_id": pid,
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{pid}",
            "lat": loc.get("lat"),
            "lon": loc.get("lng"),
        })

    return {
        "db_id": row["id"],
        "db_name": row["name"],
        "existing_maps_place_id": row["maps_place_id"],
        "query_used": query,
        "candidates": candidates,
    }


# ── nearby ─────────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _resolve_latlng(gmaps, req: dict) -> tuple[float, float, str]:
    """Return (lat, lng, label) for the origin in the request."""
    if "id" in req:
        with connect() as conn:
            row = conn.execute(
                "SELECT name, city, neighborhood, address, maps_place_id FROM places WHERE id = ?",
                (req["id"],),
            ).fetchone()
        if not row:
            err(f"no place with id {req['id']}")
        if row["maps_place_id"]:
            details = gmaps.place(row["maps_place_id"], fields=["geometry/location"])
            loc = details["result"]["geometry"]["location"]
            return loc["lat"], loc["lng"], row["name"]
        # Fallback: geocode by text if no Place ID stored yet
        parts = [p for p in [row["name"], row["neighborhood"] or row["address"], row["city"], "Japan"] if p]
        result = gmaps.geocode(", ".join(parts))
        if not result:
            err(f"could not resolve coordinates for place {req['id']} — run geocode first")
        loc = result[0]["geometry"]["location"]
        return loc["lat"], loc["lng"], row["name"]
    elif "location" in req:
        result = gmaps.geocode(req["location"])
        if not result:
            err(f"could not geocode '{req['location']}'")
        loc = result[0]["geometry"]["location"]
        return loc["lat"], loc["lng"], req["location"]
    else:
        err("'id' or 'location' is required")


def places_nearby(req: dict) -> dict:
    """Search for places of a given type near a DB place or a free-text location.

    Common useful types for Japan trip planning:
      transit_station, subway_station, restaurant, convenience_store,
      tourist_attraction, lodging, cafe, bar
    Use 'keyword' to narrow further, e.g. keyword='JR' for JR train stations only.
    """
    import googlemaps

    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key or key == "your_key_here":
        err("GOOGLE_MAPS_API_KEY is not set — add it to .env")

    place_type = req.get("type", "transit_station")
    radius = req.get("radius_m", 600)
    keyword = req.get("keyword")

    try:
        gmaps = googlemaps.Client(key=key)
        lat, lng, label = _resolve_latlng(gmaps, req)

        kwargs: dict = {"location": (lat, lng), "radius": radius, "type": place_type}
        if keyword:
            kwargs["keyword"] = keyword

        response = gmaps.places_nearby(**kwargs)
    except Exception as e:
        err(f"Google Maps API error: {e}")

    results = []
    for r in response.get("results", [])[:10]:
        pid = r["place_id"]
        rlat = r["geometry"]["location"]["lat"]
        rlng = r["geometry"]["location"]["lng"]
        results.append({
            "name": r.get("name", ""),
            "address": r.get("vicinity", ""),
            "maps_place_id": pid,
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{pid}",
            "distance_m": _haversine_m(lat, lng, rlat, rlng),
            "rating": r.get("rating"),
            "open_now": r.get("opening_hours", {}).get("open_now"),
        })

    results.sort(key=lambda x: x["distance_m"])

    return {
        "origin": label,
        "type": place_type,
        "radius_m": radius,
        "keyword": keyword,
        "results": results,
    }


# ── travel ─────────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _resolve_location(req: dict, prefix: str) -> str:
    """Return a geocodable string or Place ID ref from either a free-text key or a DB place id."""
    if f"{prefix}_place_id" in req:
        with connect() as conn:
            row = conn.execute(
                "SELECT name, address, neighborhood, city, maps_place_id FROM places WHERE id = ?",
                (req[f"{prefix}_place_id"],),
            ).fetchone()
            if not row:
                err(f"no place with id {req[f'{prefix}_place_id']}")
            # Prefer the stored Google Maps Place ID — unambiguous and skips geocoding
            if row["maps_place_id"]:
                return f"place_id:{row['maps_place_id']}"
            parts = [p for p in [row["name"], row["address"] or row["neighborhood"], row["city"]] if p]
            return ", ".join(parts) + ", Japan"
    elif prefix in req:
        return req[prefix]
    else:
        err(f"'{prefix}' or '{prefix}_place_id' is required")


def _display_location(req: dict, prefix: str) -> str:
    """Return a human-readable address string (never a place_id ref) for use in URLs."""
    if f"{prefix}_place_id" in req:
        with connect() as conn:
            row = conn.execute(
                "SELECT name, address, neighborhood, city FROM places WHERE id = ?",
                (req[f"{prefix}_place_id"],),
            ).fetchone()
            if row:
                parts = [p for p in [row["name"], row["address"] or row["neighborhood"], row["city"]] if p]
                return ", ".join(parts) + ", Japan"
    return req.get(prefix, "")


def travel_directions(req: dict) -> dict:
    import googlemaps

    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key or key == "your_key_here":
        err("GOOGLE_MAPS_API_KEY is not set — add it to .env")

    origin = _resolve_location(req, "origin")
    destination = _resolve_location(req, "destination")
    mode = req.get("mode", "transit")

    kwargs: dict = {"mode": mode}
    departure_dt: datetime | None = None

    if "departure_time" in req:
        departure_dt = datetime.strptime(req["departure_time"], "%Y-%m-%d %H:%M")
        kwargs["departure_time"] = departure_dt
    elif mode == "transit":
        # required by the API for transit; use now as a fallback
        kwargs["departure_time"] = datetime.now()

    try:
        gmaps = googlemaps.Client(key=key)
        results = gmaps.directions(origin, destination, **kwargs)
    except Exception as e:
        err(f"Google Maps API error: {e}")

    if not results:
        display_origin = _display_location(req, "origin")
        display_destination = _display_location(req, "destination")
        maps_link = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={display_origin.replace(' ', '+')}"
            f"&destination={display_destination.replace(' ', '+')}"
            f"&travelmode={mode}"
        )
        return {
            "error": f"no route found from '{origin}' to '{destination}' — Japan transit data is unavailable via the API",
            "manual_directions_url": maps_link,
            "action_required": "Please look up directions manually using the link above and provide the travel time.",
        }

    leg = results[0]["legs"][0]
    duration_min = round(leg["duration"]["value"] / 60)
    distance_km = round(leg["distance"]["value"] / 1000, 1)

    steps = []
    for step in leg.get("steps", []):
        s = {
            "mode": step["travel_mode"].lower(),
            "instruction": _strip_html(step.get("html_instructions", "")),
            "duration_min": round(step["duration"]["value"] / 60),
        }
        if step["travel_mode"] == "TRANSIT":
            td = step.get("transit_details", {})
            line = td.get("line", {})
            s["line"] = line.get("short_name") or line.get("name", "")
            s["departure_stop"] = td.get("departure_stop", {}).get("name", "")
            s["arrival_stop"] = td.get("arrival_stop", {}).get("name", "")
            s["num_stops"] = td.get("num_stops", 0)
        steps.append(s)

    result: dict = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "duration_min": duration_min,
        "distance_km": distance_km,
        "steps": steps,
    }

    if departure_dt:
        result["departure_time"] = req["departure_time"]
        result["arrival_time"] = (departure_dt + timedelta(minutes=duration_min)).strftime("%Y-%m-%d %H:%M")

    return result


# ── dispatcher ─────────────────────────────────────────────────────────────────

_HANDLERS = {
    ("places", "add"):      places_add,
    ("places", "list"):     places_list,
    ("places", "show"):     places_show,
    ("places", "update"):   places_update,
    ("places", "delete"):   places_delete,
    ("places", "geocode"):       places_geocode,
    ("snapshots", "create"):     snapshots_create,
    ("snapshots", "list"):       snapshots_list,
    ("snapshots", "show"):       snapshots_show,
    ("snapshots", "restore"):    snapshots_restore,
    ("snapshots", "diff"):       snapshots_diff,
    ("snapshots", "delete"):     snapshots_delete,
    ("places", "nearby"):   places_nearby,
    ("days",   "add"):    days_add,
    ("days",   "list"):   days_list,
    ("days",   "show"):   days_show,
    ("days",   "update"): days_update,
    ("days",   "delete"): days_delete,
    ("items",  "add"):    items_add,
    ("items",  "list"):   items_list,
    ("items",  "show"):   items_show,
    ("items",  "update"): items_update,
    ("items",  "delete"): items_delete,
    ("travel", "directions"): travel_directions,
}


def dispatch(req: dict):
    resource = req.get("resource")
    action = req.get("action")
    handler = _HANDLERS.get((resource, action))
    if not handler:
        err(f"unknown resource/action: '{resource}/{action}'. "
            f"Valid resources: places, days, items. Valid actions: add, list, show, update, delete.")
    return handler(req)


if __name__ == "__main__":
    try:
        req = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON: {e}"}))
        sys.exit(1)
    result = dispatch(req)
    print(json.dumps(result, indent=2, default=str))
