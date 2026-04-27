You are the first-time setup wizard for the trip planner toolkit. Walk the user through everything they need to start planning: dependencies, Google Maps API key, database initialization, and trip preferences.

## Step 1 — Check dependencies

```bash
uv run python -c "import googlemaps, dotenv, typer; print('dependencies OK')"
```

If this fails, install them first:
```bash
uv sync
```

Then re-check. If it still fails, tell the user which package failed and stop.

---

## Step 2 — Google Maps API key

Check if `.env` exists and has a real key:
```bash
cat .env 2>/dev/null || echo "not found"
```

If `.env` is missing or the key is `your_google_maps_api_key_here`, tell the user:

> "You need a Google Maps API key for geocoding, directions, and nearby search. Here's how to get one:
>
> 1. Go to [Google Cloud Console](https://console.cloud.google.com/)
> 2. Create or select a project
> 3. Enable these APIs: **Places API**, **Geocoding API**, **Directions API**
> 4. Go to **APIs & Services → Credentials** and create an API key
> 5. Paste it here"

Once they provide a key, write it:
```bash
echo "GOOGLE_MAPS_API_KEY=THEIR_KEY_HERE" > .env
```

---

## Step 3 — Initialize the database

```bash
uv run db.py
```

This creates `japan.db` with all required tables. Safe to re-run on an existing DB — uses `CREATE TABLE IF NOT EXISTS`. Confirm the output says "DB initialized at ...".

---

## Step 4 — Trip preferences

Ask the user the following questions in groups. Wait for their answers before moving to the next group. At the end, summarise everything and ask for confirmation before writing the file.

### Group 1 — Trip basics
> "Let's set up your preferences. First, a few basics:
> 1. What city or cities is your trip to?
> 2. What are your travel dates?
> 3. How many people are travelling?
> 4. Where are you staying? (hotel name and/or neighborhood)"

### Group 2 — Daily rhythm
> "5. What time do you like to start the day? (e.g., 08:00 or 09:00)
> 6. How do you prefer to pace your days — packed, moderate, or leisurely?"

### Group 3 — Food & drink
> "7. What types of food or drink are most important, and roughly how often do you want each? (e.g., 'ramen 4–5 times, coffee every day, sushi once or twice')
> 8. Are there any dishes that absolutely must appear in the itinerary?
> 9. Any dietary restrictions or foods to avoid?
> 10. What types of shopping are you interested in, if any? (Leave blank to skip shopping stops entirely)"

### Group 4 — Sightseeing & activities
> "11. What types of experiences matter most? For each, tell me if it's must-do, nice-to-have, or skip: temples/shrines, museums, markets, gardens/parks, neighborhoods, nightlife, other.
> 12. Would you like the planner to suggest midday breaks back at your home base when the geography allows it?"

### Group 5 — Fixed events & special rules
> "13. Do you have anything already booked? If so, what date, time, and what is it?
> 14. Any specific planning rules for the planner? (e.g., 'one big group dinner, plan for bar-hopping not a single venue', 'no early mornings after late nights')"

### Write PREFERENCES.md

Present a summary of all answers and ask:
> "Here's a summary — does this look right before I write the file?"

Once confirmed, write `PREFERENCES.md` using the template from `PREFERENCES.md.example`, filled in with their answers. Show the written file, then say:
> "You can edit PREFERENCES.md directly at any time to update your preferences."

---

## Step 5 — Customize the planner (optional)

Ask:
> "Would you like to review or adjust the planning rules? The planner skill (`.claude/commands/japan-planner.md`) controls the two-phase protocol, pause points, and daily checklist. Want to go through it now?"

If yes: Read and display the relevant sections of `japan-planner.md`. Let the user suggest changes and apply any edits they request.

If no: Skip to Step 6.

---

## Step 6 — Next steps

Tell the user:

> **Setup complete. Here's what to do next:**
>
> - `/japan-ingest` — Add restaurants, sights, and activities to the database. Paste a list of places and the agent will research, geocode, and add them.
>
> - `/japan-planner` — Once you have places in the DB, build your day-by-day itinerary.
>
> - `/japan-trip-export` — After planning, generate a KML file to import into Google My Maps.
