# Japan Planner

A Claude Code toolkit for planning a Japan trip. Manage your places database, build a day-by-day itinerary, and export it to Google Maps — all through conversational Claude skills.

## Prerequisites

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Google Maps API key (Places, Geocoding, Directions APIs enabled)

## Quick start

```bash
git clone git@github.com:aaronleesmith/japan-planner.git
cd japan-planner
uv sync
```

Then open Claude Code in this directory and run:

```
/japan-trip-init
```

This walks you through setting up your API key, initializing the database, and writing your `PREFERENCES.md`.

## Skills

| Command | What it does |
|---|---|
| `/japan-trip-init` | First-time setup: API key, DB init, preferences |
| `/japan-ingest` | Add places to the database (researches and geocodes automatically) |
| `/japan-planner` | Build your day-by-day itinerary interactively |
| `/japan-trip-export` | Export the itinerary to KML for Google My Maps |

## How it works

**Places** are restaurants, cafés, temples, hotels, transit hubs — anything you want on your trip. They live in `japan.db`.

**Days** are calendar dates for your trip. **Items** are the scheduled activities within each day.

The **planner** runs a two-phase protocol: first sketches the skeleton (anchor sights per day), then fills in meals, coffee, and travel times one day at a time — pausing for your approval at each step.

All data operations go through `api.py`, a simple JSON-in/JSON-out interface. The planner skill delegates to a `japan-db` sub-agent that handles the API calls.

## Customization

Your trip-specific preferences live in `PREFERENCES.md` (gitignored — not checked in). Run `/japan-trip-init` to create it, or copy `PREFERENCES.md.example` and edit manually.

To adjust the planning protocol itself, edit `.claude/commands/japan-planner.md`.

## Project structure

```
api.py                    JSON API for all DB operations
db.py                     SQLite schema + init
cli.py                    Optional CLI for manual DB access
export_kml.py             KML exporter for Google My Maps
PREFERENCES.md.example    Template for your trip preferences
.env.example              Template for environment variables
.claude/commands/
  japan-trip-init.md      Setup wizard skill
  japan-ingest.md         Data ingestion skill
  japan-planner.md        Trip planner skill
  japan-db.md             DB sub-agent (used internally)
  japan-trip-export.md    KML export skill
```
