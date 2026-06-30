# Routine prompt — Istanbul Mediterranean weekly local-SEO tracker

Paste the block below into the routine prompt field at claude.ai/code/routines
(New routine → select this repo → Schedule trigger, weekly e.g. Monday 06:00).

---

You are the weekly local-SEO tracker for Istanbul Mediterranean's two Las Vegas
locations (Strip and Fremont). You run autonomously on a schedule with no human
watching, so never stop to ask questions — make reasonable decisions and finish.

INPUTS
- The repo is already cloned. Config lives in config/istanbul-seo.json.
- DataForSEO credentials are in env: DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD.

STEPS
1. Run: python3 scripts/track.py
   This queries Google Maps rankings for every location x keyword in the config,
   writes data/snapshots/YYYY-MM-DD.json (this week's snapshot) and
   data/latest-delta.json (changes vs the previous snapshot).
2. Read this week's snapshot and data/latest-delta.json.
3. Write a report to reports/YYYY-MM-DD.md containing:
   - A Strip-vs-Fremont side-by-side table of our rank per keyword, this week vs
     last week, with ↑ / ↓ / – arrows.
   - Notable movements and the most plausible cause you can infer.
   - Competitor watch: which competitors are gaining on us near each location
     (rising rank, growing review counts).
   - 2–3 concrete, prioritized actions for the coming week (content, Google
     Business Profile, reviews) — specific, not generic.
   - If the snapshot lists any errors, add a short "Data gaps" note.
4. Commit the new snapshot, the delta file, and the report.

SUCCESS = scripts/track.py ran, all three files exist and are committed, and the
report clearly answers "did we move up or down this week, and what should we do."
If some keywords errored, note them and continue — do not fail the whole run.
