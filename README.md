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
4. **Enable "Allow unrestricted branch pushes."** This is required, not
   optional, for this routine. See "Why continuity requires pushing to main"
   below — without it, every run "forgets" the previous week's snapshot.

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

## Why continuity requires pushing to main

Each Routine firing starts from a **fresh clone of `main`** — it has no memory
of previous runs beyond what's committed to `main` itself. State persistence
here depends entirely on `data/snapshots/` being present on `main` at the
start of the next run.

By default, Routines push to a new `claude/`-prefixed branch every run instead
of committing to `main`. If that branch is never merged, the branch (and that
week's snapshot) is invisible to the next run — which clones `main`, finds
`data/snapshots/` still empty, and logs "no prior snapshot" again. Repeat
weekly, forever, with the tracker perpetually stuck in baseline mode.

**Fix:** enable "Allow unrestricted branch pushes" on the routine so it
commits `data/snapshots/*.json`, `data/latest-delta.json`, and the weekly
report straight to `main`. That's what makes week-over-week deltas work.

If you'd rather keep the PR-review workflow (branch per run + manual merge),
that's fine too — just make sure every run's branch actually gets merged to
`main` before the next scheduled firing, or you'll hit the same "no prior
snapshot" issue.
