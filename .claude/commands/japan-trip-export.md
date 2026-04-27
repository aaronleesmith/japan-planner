Export the Japan trip itinerary to a KML file and guide the user through importing it into Google Maps.

## Step 1 — Run the export

```bash
uv run export_kml.py
```

This creates a timestamped file like `japan_trip_20260501_143022.kml` in the project directory.

To write to a specific path instead:
```bash
uv run export_kml.py --output ~/Desktop/japan_trip.kml
```

## Step 2 — Check the output

The script prints a note to stderr if any items were skipped due to missing coordinates:

```
Note: 12 item(s) skipped — linked place has no coordinates.
Run 'places geocode' + 'places update' (with lat/lon) to fix.
```

If there are skipped items, offer to geocode them now using the `/japan-planner` skill before re-exporting. Places without coordinates simply won't appear as pins on the map — everything else still exports correctly.

## Step 3 — Import into Google Maps

Tell the user to follow these steps:

1. Go to **[Google My Maps](https://www.google.com/mymaps)** and click **Create a new map**
2. Click **Import** in the left panel (under the first untitled layer)
3. Upload the `.kml` file
4. Google Maps will import all the folders as layers — one per day

**Tips to pass on to the user:**
- Each day is its own folder/layer, named `Day N — YYYY-MM-DD — Title (City)`
- Pins are colour-coded: 🔴 food, 🔵 sightseeing, 🟢 lodging, ⚪ transportation
- Each pin's description includes scheduled time, duration, food type + cuisine + tier (food items only), reservation status, address, website, and notes
- A hidden route line (`Route — Day N`) connects each day's stops in order — toggle it on in the layer list to see the day's path
- To show only one day at a time, use the layer visibility toggles in the left panel
- Google My Maps has a 10-layer limit on free accounts — if the trip is longer than 10 days, suggest splitting into two maps (e.g. Tokyo days / Kyoto+Osaka days)

## KML structure reference

```
Document
├── Styles (food=red, sightseeing=blue, lodging=green, transport=grey)
├── Folder: "Day 1 — 2026-05-01 — Arrival (Tokyo)"
│   ├── Placemark: place name + description + coordinates
│   ├── Placemark: ...
│   └── Placemark: "Route — Day 1"  [LineString, hidden by default]
├── Folder: "Day 2 — 2026-05-02 — ..."
│   └── ...
└── ...
```

## Re-exporting after changes

Re-run the export any time the itinerary changes — each run creates a new timestamped file so old exports are preserved. To replace a previous import in Google My Maps, delete the old layer and re-import the new file.
