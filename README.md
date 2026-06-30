# seo-routines

Weekly local-SEO ranking tracker for **Istanbul Mediterranean** (Las Vegas — Strip
+ Fremont), built to run as a Claude Code **Routine** in the cloud.

The design separates two layers:

- **Deterministic data** — `scripts/track.py` queries DataForSEO's Google Maps
  SERP for each location × keyword and writes a dated snapshot + a delta.
- **Reasoning** — the routine reads the delta and writes a human-readable weekly
  report with commentary and prioritized actions.

Each location is queried with its own geo-coordinate, so Strip and Fremont return
their real local packs instead of one shared result.

## Layout

```
config/istanbul-seo.json   locations, keywords, brand aliases  (edit me)
scripts/track.py           fetch rankings → snapshot + delta
data/snapshots/            one JSON per run (state lives here)
data/latest-delta.json     machine-readable change vs previous run
reports/                   one markdown report per run
routine-prompt.md          the prompt to paste into the Routines UI
```

## Setup

1. **Secrets** — in the routine's cloud environment, add:
   - `DATAFORSEO_LOGIN`
   - `DATAFORSEO_PASSWORD`
2. **Network** — the routine environment must allow outbound HTTPS to
   `api.dataforseo.com`, or the API calls will be blocked.
3. **Create the routine** — at https://claude.ai/code/routines → New routine →
   select this repo → add a **Schedule** trigger (e.g. weekly, Monday 06:00) →
   paste the prompt from `routine-prompt.md`.

## Run it locally first

```bash
export DATAFORSEO_LOGIN=...
export DATAFORSEO_PASSWORD=...
python3 scripts/track.py
```

The first run has no previous snapshot, so it is treated as the baseline (no
deltas). From the second run on you get week-over-week movement.

## Editing keywords

Change `config/istanbul-seo.json` only — the script and prompt read from it, so
you never have to touch code to add/remove keywords or competitors. Replace the
placeholder coordinates with each location's exact latitude,longitude for the most
accurate local pack.

## Notes

- Routines push to `claude/`-prefixed branches by default, so reports land on a
  branch and you review via PR. Flip "Allow unrestricted branch pushes" only if
  you want it to commit straight to main.
- Routines are stateless between runs; state persistence here is the snapshot
  files in `data/snapshots/`.
