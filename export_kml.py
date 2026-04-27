#!/usr/bin/env python3
"""Export the Japan trip itinerary to a KML file for Google Maps import.

Usage:
    uv run export_kml.py
    uv run export_kml.py --output my_trip.kml

Output: japan_trip_YYYYMMDD_HHMMSS.kml (or --output path)
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from db import connect

OUTPUT_DIR = Path(__file__).parent

# (icon_url, AABBGGRR color)  — KML color order is Alpha-Blue-Green-Red
_STYLES: dict[str, tuple[str, str]] = {
    "food":           ("http://maps.google.com/mapfiles/kml/paddle/red-circle.png",  "ff0000dd"),
    "sightseeing":    ("http://maps.google.com/mapfiles/kml/paddle/blu-circle.png",  "ffdd5500"),
    "lodging":        ("http://maps.google.com/mapfiles/kml/paddle/grn-circle.png",  "ff00aa00"),
    "transportation": ("http://maps.google.com/mapfiles/kml/paddle/wht-circle.png",  "ffaaaaaa"),
    "default":        ("http://maps.google.com/mapfiles/kml/paddle/pink-circle.png", "ff8800cc"),
}

_RESERVATION_LABELS = {
    "booked":         "Booked",
    "need_to_book":   "*** NEEDS BOOKING ***",
    "no_reservations": "No reservation needed",
}

_FOOD_TYPE_EMOJI = {
    "meal":     "🍽",
    "coffee":   "☕",
    "dessert":  "🍡",
    "cocktails":"🍸",
}


def _style_id(category: str | None) -> str:
    return f"style_{category}" if category in _STYLES else "style_default"


def _build_description(item: dict, place: dict) -> str:
    lines: list[str] = []

    time_str = item.get("start_time", "")
    if time_str and item.get("end_time"):
        time_str += f" – {item['end_time']}"
    if time_str:
        lines.append(f"Time: {time_str}")
    if item.get("duration_min"):
        lines.append(f"Duration: {item['duration_min']} min")

    if place.get("food_type"):
        emoji = _FOOD_TYPE_EMOJI.get(place["food_type"], "")
        label = f"{emoji} {place['food_type'].title()}".strip()
        if place.get("food_cuisine"):
            label += f" — {place['food_cuisine']}"
        if place.get("food_tier"):
            label += f" (tier {place['food_tier']})"
        lines.append(label)

    if place.get("reservation_status"):
        lines.append(_RESERVATION_LABELS.get(place["reservation_status"], place["reservation_status"]))
    if place.get("booked_time"):
        lines.append(f"Booked for: {place['booked_time']}")

    if place.get("address"):
        lines.append(f"Address: {place['address']}")
    if place.get("website_url"):
        lines.append(f"Website: {place['website_url']}")
    if item.get("cost_jpy"):
        lines.append(f"Est. cost: ¥{item['cost_jpy']:,}")

    note_parts = [s for s in (item.get("notes"), place.get("place_notes")) if s]
    if note_parts:
        lines.append(f"Notes: {' | '.join(note_parts)}")

    return "\n".join(lines)


def build_kml() -> ET.Element:
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "Japan Trip"
    ET.SubElement(doc, "description").text = f"Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    # Pin styles per category
    for cat, (icon_url, color) in _STYLES.items():
        style = ET.SubElement(doc, "Style", id=f"style_{cat}")
        icon_style = ET.SubElement(style, "IconStyle")
        ET.SubElement(icon_style, "color").text = color
        ET.SubElement(icon_style, "scale").text = "1.1"
        icon = ET.SubElement(icon_style, "Icon")
        ET.SubElement(icon, "href").text = icon_url
        label_style = ET.SubElement(style, "LabelStyle")
        ET.SubElement(label_style, "scale").text = "0.8"

    # Route line style (semi-transparent white, hidden by default)
    line_style_el = ET.SubElement(doc, "Style", id="day_route")
    ls = ET.SubElement(line_style_el, "LineStyle")
    ET.SubElement(ls, "color").text = "99ffffff"
    ET.SubElement(ls, "width").text = "3"

    skipped = 0

    with connect() as conn:
        days = conn.execute("SELECT * FROM days ORDER BY date").fetchall()

        for i, day in enumerate(days, 1):
            d = dict(day)
            folder_name = f"Day {i} — {d['date']}"
            if d.get("title"):
                folder_name += f" — {d['title']}"
            if d.get("city"):
                folder_name += f" ({d['city']})"

            folder = ET.SubElement(doc, "Folder")
            ET.SubElement(folder, "name").text = folder_name
            if d.get("notes"):
                ET.SubElement(folder, "description").text = d["notes"]

            items = conn.execute("""
                SELECT i.*,
                       p.name        AS place_name,
                       p.category    AS category,
                       p.lat         AS lat,
                       p.lon         AS lon,
                       p.address     AS address,
                       p.website_url AS website_url,
                       p.food_type   AS food_type,
                       p.food_cuisine AS food_cuisine,
                       p.food_tier   AS food_tier,
                       p.reservation_status AS reservation_status,
                       p.booked_time AS booked_time,
                       p.notes       AS place_notes
                FROM day_items i
                LEFT JOIN places p ON i.place_id = p.id
                WHERE i.day_id = ?
                ORDER BY i.position
            """, (d["id"],)).fetchall()

            route_coords: list[tuple[float, float]] = []

            for item in items:
                it = dict(item)
                if not it.get("lat") or not it.get("lon"):
                    skipped += 1
                    continue

                lat, lon = it["lat"], it["lon"]
                route_coords.append((lon, lat))

                pm = ET.SubElement(folder, "Placemark")
                ET.SubElement(pm, "name").text = it.get("place_name") or it["title"]
                desc = _build_description(it, it)
                if desc:
                    ET.SubElement(pm, "description").text = desc
                ET.SubElement(pm, "styleUrl").text = f"#{_style_id(it.get('category'))}"
                point = ET.SubElement(pm, "Point")
                ET.SubElement(point, "coordinates").text = f"{lon},{lat},0"

            # Route line connecting the day's stops in order
            if len(route_coords) > 1:
                route_pm = ET.SubElement(folder, "Placemark")
                ET.SubElement(route_pm, "name").text = f"Route — Day {i}"
                ET.SubElement(route_pm, "styleUrl").text = "#day_route"
                ET.SubElement(route_pm, "visibility").text = "0"
                ls_el = ET.SubElement(route_pm, "LineString")
                ET.SubElement(ls_el, "tessellate").text = "1"
                ET.SubElement(ls_el, "coordinates").text = " ".join(
                    f"{lon},{lat},0" for lon, lat in route_coords
                )

    if skipped:
        print(
            f"Note: {skipped} item(s) skipped — linked place has no coordinates. "
            "Run 'places geocode' + 'places update' (with lat/lon) to fix.",
            file=sys.stderr,
        )

    return kml


def main():
    parser = argparse.ArgumentParser(description="Export Japan trip to KML")
    parser.add_argument("--output", help="Output file path (default: auto-named in project dir)")
    args = parser.parse_args()

    kml = build_kml()
    ET.indent(kml, space="  ")
    xml_bytes = ET.tostring(kml, encoding="utf-8", xml_declaration=True)

    if args.output:
        out_path = Path(args.output)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUT_DIR / f"japan_trip_{stamp}.kml"

    out_path.write_bytes(xml_bytes)
    print(f"Exported to {out_path}")
    return out_path


if __name__ == "__main__":
    main()
