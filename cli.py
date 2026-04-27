#!/usr/bin/env python3
import json
from datetime import datetime
from typing import Optional

import typer

from db import connect

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

app = typer.Typer(no_args_is_help=True)
places_app = typer.Typer(no_args_is_help=True)
days_app = typer.Typer(no_args_is_help=True)
items_app = typer.Typer(no_args_is_help=True)

app.add_typer(places_app, name="places")
app.add_typer(days_app, name="days")
app.add_typer(items_app, name="items")


def out(data):
    print(json.dumps(data, indent=2, default=str))


def row_to_dict(row) -> dict:
    return dict(row) if row else None


# ── places ─────────────────────────────────────────────────────────────────────

@places_app.command("add")
def places_add(
    name: str = typer.Option(...),
    category: Optional[str] = typer.Option(None, help="food, sightseeing, transportation, lodging"),
    city: Optional[str] = typer.Option(None),
    neighborhood: Optional[str] = typer.Option(None),
    address: Optional[str] = typer.Option(None),
    website_url: Optional[str] = typer.Option(None),
    maps_url: Optional[str] = typer.Option(None),
    reservation_status: Optional[str] = typer.Option(None, help="booked, reservations_accepted, no_reservations"),
    booked_time: Optional[str] = typer.Option(None, help="YYYY-MM-DD HH:MM"),
    is_family: bool = typer.Option(False),
    food_tier: Optional[int] = typer.Option(None, help="1-3"),
    food_type: Optional[str] = typer.Option(None, help="meal, coffee, dessert, cocktails"),
    food_cuisine: Optional[str] = typer.Option(None),
    priority: Optional[int] = typer.Option(None, help="1=must-do, 2=want-to-do, 3=nice-to-have"),
    est_duration_min: Optional[int] = typer.Option(None),
    mon_open: Optional[str] = typer.Option(None), mon_close: Optional[str] = typer.Option(None),
    tue_open: Optional[str] = typer.Option(None), tue_close: Optional[str] = typer.Option(None),
    wed_open: Optional[str] = typer.Option(None), wed_close: Optional[str] = typer.Option(None),
    thu_open: Optional[str] = typer.Option(None), thu_close: Optional[str] = typer.Option(None),
    fri_open: Optional[str] = typer.Option(None), fri_close: Optional[str] = typer.Option(None),
    sat_open: Optional[str] = typer.Option(None), sat_close: Optional[str] = typer.Option(None),
    sun_open: Optional[str] = typer.Option(None), sun_close: Optional[str] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO places (
                name, category, city, neighborhood, address, website_url, maps_url,
                reservation_status, booked_time, is_family, food_tier, food_type, food_cuisine,
                priority, est_duration_min,
                mon_open, mon_close, tue_open, tue_close, wed_open, wed_close,
                thu_open, thu_close, fri_open, fri_close, sat_open, sat_close, sun_open, sun_close,
                notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            name, category, city, neighborhood, address, website_url, maps_url,
            reservation_status, booked_time, int(is_family), food_tier, food_type, food_cuisine,
            priority, est_duration_min,
            mon_open, mon_close, tue_open, tue_close, wed_open, wed_close,
            thu_open, thu_close, fri_open, fri_close, sat_open, sat_close, sun_open, sun_close,
            notes,
        ))
        row = conn.execute("SELECT * FROM places WHERE id = ?", (cur.lastrowid,)).fetchone()
        out(row_to_dict(row))


@places_app.command("list")
def places_list(
    # ── exact-match filters ───────────────────────────────────────────────────
    category: Optional[str] = typer.Option(None, help="food, sightseeing, transportation, lodging"),
    city: Optional[str] = typer.Option(None),
    priority: Optional[int] = typer.Option(None, help="exact priority value"),
    food_type: Optional[str] = typer.Option(None, help="meal, coffee, dessert, cocktails"),
    food_cuisine: Optional[str] = typer.Option(None),
    reservation_status: Optional[str] = typer.Option(None, help="booked, reservations_accepted, no_reservations"),
    is_family: Optional[bool] = typer.Option(None),
    food_tier: Optional[int] = typer.Option(None, help="exact food tier 1-3"),
    # ── range / ceiling filters ───────────────────────────────────────────────
    max_priority: Optional[int] = typer.Option(None, help="priority <= N  (e.g. 2 = must-do + want-to-do)"),
    max_food_tier: Optional[int] = typer.Option(None, help="food_tier <= N"),
    # ── text search ───────────────────────────────────────────────────────────
    search: Optional[str] = typer.Option(None, help="substring search across name, neighborhood, address, food_cuisine, notes"),
    # ── availability filters ──────────────────────────────────────────────────
    open_on_day: Optional[str] = typer.Option(None, help="mon/tue/wed/thu/fri/sat/sun — places not closed that day"),
    open_on_date: Optional[str] = typer.Option(None, help="YYYY-MM-DD — infers day of week, then applies open_on_day logic"),
    open_at: Optional[str] = typer.Option(None, help="HH:MM — combine with --open-on-day or --open-on-date to check open at a specific time"),
    # ── scheduling helpers ────────────────────────────────────────────────────
    unscheduled: bool = typer.Option(False, help="only places not yet linked to any day_items"),
    needs_booking: bool = typer.Option(False, help="shorthand for --reservation-status reservations_accepted"),
):
    clauses: list[str] = []
    params: list = []

    # exact matches
    for col, val in [
        ("category", category), ("city", city), ("priority", priority),
        ("food_type", food_type), ("food_cuisine", food_cuisine),
        ("food_tier", food_tier),
    ]:
        if val is not None:
            clauses.append(f"{col} = ?")
            params.append(val)

    # reservation_status (--needs-booking overrides if both given)
    effective_status = "reservations_accepted" if needs_booking else reservation_status
    if effective_status is not None:
        clauses.append("reservation_status = ?")
        params.append(effective_status)

    if is_family is not None:
        clauses.append("is_family = ?")
        params.append(int(is_family))

    # range / ceiling
    if max_priority is not None:
        clauses.append("priority <= ?")
        params.append(max_priority)
    if max_food_tier is not None:
        clauses.append("food_tier <= ?")
        params.append(max_food_tier)

    # full-text search
    if search:
        pattern = f"%{search}%"
        clauses.append(
            "(name LIKE ? OR neighborhood LIKE ? OR address LIKE ? OR food_cuisine LIKE ? OR notes LIKE ?)"
        )
        params.extend([pattern] * 5)

    # availability — resolve day
    day = None
    if open_on_date:
        try:
            day = _WEEKDAYS[datetime.strptime(open_on_date, "%Y-%m-%d").weekday()]
        except ValueError:
            out({"error": f"invalid date '{open_on_date}', expected YYYY-MM-DD"}); raise typer.Exit(1)
    elif open_on_day:
        day = open_on_day.lower()
        if day not in _WEEKDAYS:
            out({"error": f"invalid day '{open_on_day}', expected mon/tue/wed/thu/fri/sat/sun"}); raise typer.Exit(1)

    if day:
        # NULL open means closed that day
        clauses.append(f"{day}_open IS NOT NULL")
        if open_at:
            clauses.append(f"{day}_open <= ?")
            clauses.append(f"{day}_close >= ?")
            params.extend([open_at, open_at])

    # unscheduled
    if unscheduled:
        clauses.append("id NOT IN (SELECT DISTINCT place_id FROM day_items WHERE place_id IS NOT NULL)")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM places {where} ORDER BY priority NULLS LAST, name", params
        ).fetchall()
        out([row_to_dict(r) for r in rows])


@places_app.command("show")
def places_show(id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM places WHERE id = ?", (id,)).fetchone()
        if not row:
            out({"error": f"no place with id {id}"}); raise typer.Exit(1)
        out(row_to_dict(row))


@places_app.command("update")
def places_update(
    id: int,
    name: Optional[str] = typer.Option(None),
    category: Optional[str] = typer.Option(None),
    city: Optional[str] = typer.Option(None),
    neighborhood: Optional[str] = typer.Option(None),
    address: Optional[str] = typer.Option(None),
    website_url: Optional[str] = typer.Option(None),
    maps_url: Optional[str] = typer.Option(None),
    reservation_status: Optional[str] = typer.Option(None),
    booked_time: Optional[str] = typer.Option(None),
    is_family: Optional[bool] = typer.Option(None),
    food_tier: Optional[int] = typer.Option(None),
    food_type: Optional[str] = typer.Option(None),
    food_cuisine: Optional[str] = typer.Option(None),
    priority: Optional[int] = typer.Option(None),
    est_duration_min: Optional[int] = typer.Option(None),
    mon_open: Optional[str] = typer.Option(None), mon_close: Optional[str] = typer.Option(None),
    tue_open: Optional[str] = typer.Option(None), tue_close: Optional[str] = typer.Option(None),
    wed_open: Optional[str] = typer.Option(None), wed_close: Optional[str] = typer.Option(None),
    thu_open: Optional[str] = typer.Option(None), thu_close: Optional[str] = typer.Option(None),
    fri_open: Optional[str] = typer.Option(None), fri_close: Optional[str] = typer.Option(None),
    sat_open: Optional[str] = typer.Option(None), sat_close: Optional[str] = typer.Option(None),
    sun_open: Optional[str] = typer.Option(None), sun_close: Optional[str] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    raw = {
        "name": name, "category": category, "city": city, "neighborhood": neighborhood,
        "address": address, "website_url": website_url, "maps_url": maps_url,
        "reservation_status": reservation_status, "booked_time": booked_time,
        "food_tier": food_tier, "food_type": food_type, "food_cuisine": food_cuisine,
        "priority": priority, "est_duration_min": est_duration_min,
        "mon_open": mon_open, "mon_close": mon_close,
        "tue_open": tue_open, "tue_close": tue_close,
        "wed_open": wed_open, "wed_close": wed_close,
        "thu_open": thu_open, "thu_close": thu_close,
        "fri_open": fri_open, "fri_close": fri_close,
        "sat_open": sat_open, "sat_close": sat_close,
        "sun_open": sun_open, "sun_close": sun_close,
        "notes": notes,
    }
    if is_family is not None:
        raw["is_family"] = int(is_family)
    updates = {k: v for k, v in raw.items() if v is not None}
    if not updates:
        out({"error": "no fields provided"}); raise typer.Exit(1)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(f"UPDATE places SET {set_clause} WHERE id = ?", (*updates.values(), id))
        row = conn.execute("SELECT * FROM places WHERE id = ?", (id,)).fetchone()
        out(row_to_dict(row))


@places_app.command("delete")
def places_delete(id: int):
    with connect() as conn:
        conn.execute("DELETE FROM places WHERE id = ?", (id,))
        out({"deleted": id})


# ── days ───────────────────────────────────────────────────────────────────────

@days_app.command("add")
def days_add(
    date: str = typer.Option(..., help="YYYY-MM-DD"),
    title: Optional[str] = typer.Option(None),
    city: Optional[str] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO days (date, title, city, notes) VALUES (?, ?, ?, ?)",
            (date, title, city, notes),
        )
        row = conn.execute("SELECT * FROM days WHERE id = ?", (cur.lastrowid,)).fetchone()
        out(row_to_dict(row))


@days_app.command("list")
def days_list():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM days ORDER BY date").fetchall()
        out([row_to_dict(r) for r in rows])


@days_app.command("show")
def days_show(id: int):
    with connect() as conn:
        day = conn.execute("SELECT * FROM days WHERE id = ?", (id,)).fetchone()
        if not day:
            out({"error": f"no day with id {id}"}); raise typer.Exit(1)
        items = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.day_id = ?
            ORDER BY i.position
        """, (id,)).fetchall()
        result = row_to_dict(day)
        result["items"] = [row_to_dict(r) for r in items]
        out(result)


@days_app.command("update")
def days_update(
    id: int,
    title: Optional[str] = typer.Option(None),
    city: Optional[str] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    updates = {k: v for k, v in {"title": title, "city": city, "notes": notes}.items() if v is not None}
    if not updates:
        out({"error": "no fields provided"}); raise typer.Exit(1)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(f"UPDATE days SET {set_clause} WHERE id = ?", (*updates.values(), id))
        row = conn.execute("SELECT * FROM days WHERE id = ?", (id,)).fetchone()
        out(row_to_dict(row))


@days_app.command("delete")
def days_delete(id: int):
    with connect() as conn:
        conn.execute("DELETE FROM days WHERE id = ?", (id,))
        out({"deleted": id})


# ── items ──────────────────────────────────────────────────────────────────────

@items_app.command("add")
def items_add(
    day_id: int = typer.Option(...),
    title: str = typer.Option(...),
    place_id: Optional[int] = typer.Option(None),
    position: Optional[int] = typer.Option(None, help="auto-appends if omitted"),
    item_type: Optional[str] = typer.Option(None, "--type"),
    start_time: Optional[str] = typer.Option(None, help="HH:MM"),
    end_time: Optional[str] = typer.Option(None, help="HH:MM"),
    duration_min: Optional[int] = typer.Option(None),
    cost_jpy: Optional[int] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    with connect() as conn:
        if position is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM day_items WHERE day_id = ?",
                (day_id,),
            ).fetchone()
            position = row["next"]
        cur = conn.execute("""
            INSERT INTO day_items (day_id, position, place_id, title, type, start_time, end_time, duration_min, cost_jpy, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (day_id, position, place_id, title, item_type, start_time, end_time, duration_min, cost_jpy, notes))
        row = conn.execute("SELECT * FROM day_items WHERE id = ?", (cur.lastrowid,)).fetchone()
        out(row_to_dict(row))


@items_app.command("list")
def items_list(day_id: int):
    with connect() as conn:
        rows = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.day_id = ?
            ORDER BY i.position
        """, (day_id,)).fetchall()
        out([row_to_dict(r) for r in rows])


@items_app.command("show")
def items_show(id: int):
    with connect() as conn:
        row = conn.execute("""
            SELECT i.*, p.name AS place_name, p.category AS place_category
            FROM day_items i
            LEFT JOIN places p ON i.place_id = p.id
            WHERE i.id = ?
        """, (id,)).fetchone()
        if not row:
            out({"error": f"no item with id {id}"}); raise typer.Exit(1)
        out(row_to_dict(row))


@items_app.command("update")
def items_update(
    id: int,
    title: Optional[str] = typer.Option(None),
    place_id: Optional[int] = typer.Option(None),
    position: Optional[int] = typer.Option(None),
    item_type: Optional[str] = typer.Option(None, "--type"),
    start_time: Optional[str] = typer.Option(None),
    end_time: Optional[str] = typer.Option(None),
    duration_min: Optional[int] = typer.Option(None),
    cost_jpy: Optional[int] = typer.Option(None),
    notes: Optional[str] = typer.Option(None),
):
    raw = {
        "title": title, "place_id": place_id, "position": position, "type": item_type,
        "start_time": start_time, "end_time": end_time,
        "duration_min": duration_min, "cost_jpy": cost_jpy, "notes": notes,
    }
    updates = {k: v for k, v in raw.items() if v is not None}
    if not updates:
        out({"error": "no fields provided"}); raise typer.Exit(1)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with connect() as conn:
        conn.execute(f"UPDATE day_items SET {set_clause} WHERE id = ?", (*updates.values(), id))
        row = conn.execute("SELECT * FROM day_items WHERE id = ?", (id,)).fetchone()
        out(row_to_dict(row))


@items_app.command("delete")
def items_delete(id: int):
    with connect() as conn:
        conn.execute("DELETE FROM day_items WHERE id = ?", (id,))
        out({"deleted": id})


if __name__ == "__main__":
    app()
