#!/usr/bin/env python3
"""
Local-SEO ranking tracker for Istanbul Mediterranean (Strip + Fremont).

Deterministic data layer: queries DataForSEO's Google Maps live SERP for each
location x keyword, records our rank and the top competitors, writes a dated
snapshot, and computes a delta vs the previous snapshot. The routine prompt then
turns the delta into a human-readable weekly report.

Env required:
  DATAFORSEO_LOGIN
  DATAFORSEO_PASSWORD

Outputs:
  data/snapshots/YYYY-MM-DD.json   full snapshot for this run
  data/latest-delta.json           machine-readable change vs previous snapshot
"""

import base64
import datetime as dt
import glob
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "istanbul-seo.json")
SNAP_DIR = os.path.join(ROOT, "data", "snapshots")
DELTA_PATH = os.path.join(ROOT, "data", "latest-delta.json")

DFS_URL = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def auth_header():
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        sys.exit("Missing DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD env vars.")
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


def query_maps(keyword, coordinate, language_code):
    """One Google Maps SERP query. Returns the list of map items or raises."""
    payload = json.dumps([{
        "keyword": keyword,
        "location_coordinate": coordinate,
        "language_code": language_code,
    }]).encode()
    req = urllib.request.Request(
        DFS_URL,
        data=payload,
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    tasks = data.get("tasks") or []
    if not tasks:
        raise RuntimeError("no tasks in response")
    result = tasks[0].get("result") or []
    if not result:
        raise RuntimeError(tasks[0].get("status_message", "empty result"))
    return result[0].get("items") or []


def is_brand(title, aliases):
    t = (title or "").lower()
    return any(a in t for a in aliases)


def parse_items(items, aliases, top_n):
    """Pull our local-pack rank, organic rank, and top competitors out of the SERP items.

    The maps/live/advanced endpoint only ever returns "maps_search" (local pack)
    items, never organic web results, so organic_rank is recorded as None unless
    a future/alternate response shape actually includes an "organic" item.
    """
    listings = [it for it in items if it.get("type") == "maps_search"]
    listings.sort(key=lambda it: it.get("rank_absolute") or 999)

    organic_items = [it for it in items if it.get("type") == "organic"]

    our_rank = None
    organic_rank = None
    competitors = []
    for it in listings:
        rating = it.get("rating") or {}
        entry = {
            "name": it.get("title"),
            "rank": it.get("rank_absolute"),
            "rating": rating.get("value"),
            "review_count": rating.get("votes_count"),
        }
        if is_brand(it.get("title"), aliases):
            if our_rank is None:
                our_rank = it.get("rank_absolute")
        elif len(competitors) < top_n:
            competitors.append(entry)

    for it in organic_items:
        if is_brand(it.get("title") or it.get("url"), aliases):
            organic_rank = it.get("rank_absolute")
            break

    return our_rank, organic_rank, competitors


def build_snapshot(cfg):
    aliases = [a.lower() for a in cfg.get("brand_aliases", [])]
    top_n = cfg.get("top_competitors", 5)
    lang = cfg.get("language_code", "en")

    snapshot = {"date": dt.date.today().isoformat(), "locations": {}, "errors": []}

    for loc in cfg["locations"]:
        loc_block = {"name": loc["name"], "keywords": {}}
        for kw in loc["keywords"]:
            try:
                items = query_maps(kw, loc["coordinate"], lang)
                our_rank, organic_rank, comps = parse_items(items, aliases, top_n)
                loc_block["keywords"][kw] = {
                    "our_rank": our_rank,
                    "organic_rank": organic_rank,
                    "competitors": comps,
                }
            except (urllib.error.URLError, RuntimeError, ValueError) as e:
                loc_block["keywords"][kw] = {
                    "our_rank": None,
                    "organic_rank": None,
                    "competitors": [],
                    "error": str(e),
                }
                snapshot["errors"].append(f"{loc['id']} / {kw}: {e}")
        snapshot["locations"][loc["id"]] = loc_block
    return snapshot


def previous_snapshot(exclude_date):
    files = sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))
    files = [f for f in files if os.path.basename(f) != f"{exclude_date}.json"]
    if not files:
        return None
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def compute_delta(curr, prev):
    delta = {
        "date": curr["date"],
        "baseline": prev is None,
        "changes": [],
        "competitors_entered": [],
        "competitors_dropped": [],
        "competitor_changes": [],
    }
    if prev is None:
        return delta

    for loc_id, loc in curr["locations"].items():
        prev_loc = (prev.get("locations") or {}).get(loc_id, {})
        prev_kw = prev_loc.get("keywords", {})
        for kw, data in loc["keywords"].items():
            before_data = prev_kw.get(kw) or {}

            now_rank = data.get("our_rank")
            before_rank = before_data.get("our_rank")
            if now_rank != before_rank:
                delta["changes"].append({
                    "location": loc_id,
                    "keyword": kw,
                    "type": "local_pack_rank",
                    "from": before_rank,
                    "to": now_rank,
                    "direction": _direction(before_rank, now_rank),
                })

            now_organic = data.get("organic_rank")
            before_organic = before_data.get("organic_rank")
            if now_organic != before_organic:
                delta["changes"].append({
                    "location": loc_id,
                    "keyword": kw,
                    "type": "organic_rank",
                    "from": before_organic,
                    "to": now_organic,
                    "direction": _direction(before_organic, now_organic),
                })

            now_comps = {c["name"]: c for c in data.get("competitors", []) if c.get("name")}
            before_comps = {c["name"]: c for c in before_data.get("competitors", []) if c.get("name")}

            for name in now_comps.keys() - before_comps.keys():
                delta["competitors_entered"].append({
                    "location": loc_id,
                    "keyword": kw,
                    "name": name,
                    "rank": now_comps[name].get("rank"),
                })
            for name in before_comps.keys() - now_comps.keys():
                delta["competitors_dropped"].append({
                    "location": loc_id,
                    "keyword": kw,
                    "name": name,
                    "rank": before_comps[name].get("rank"),
                })
            for name in now_comps.keys() & before_comps.keys():
                now_c, before_c = now_comps[name], before_comps[name]
                rank_changed = now_c.get("rank") != before_c.get("rank")
                rating_changed = now_c.get("rating") != before_c.get("rating")
                reviews_changed = now_c.get("review_count") != before_c.get("review_count")
                if rank_changed or rating_changed or reviews_changed:
                    delta["competitor_changes"].append({
                        "location": loc_id,
                        "keyword": kw,
                        "name": name,
                        "rank": {"from": before_c.get("rank"), "to": now_c.get("rank")},
                        "rating": {"from": before_c.get("rating"), "to": now_c.get("rating")},
                        "review_count": {
                            "from": before_c.get("review_count"),
                            "to": now_c.get("review_count"),
                        },
                    })
    return delta


def _direction(before, now):
    if before is None and now is not None:
        return "entered"
    if before is not None and now is None:
        return "dropped"
    if now < before:
        return "up"
    if now > before:
        return "down"
    return "same"


def main():
    cfg = load_config()
    snapshot = build_snapshot(cfg)

    os.makedirs(SNAP_DIR, exist_ok=True)
    snap_path = os.path.join(SNAP_DIR, f"{snapshot['date']}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    prev = previous_snapshot(snapshot["date"])
    delta = compute_delta(snapshot, prev)
    with open(DELTA_PATH, "w", encoding="utf-8") as f:
        json.dump(delta, f, indent=2, ensure_ascii=False)

    print(f"Wrote {snap_path}")
    print(f"Wrote {DELTA_PATH}")
    print(
        f"Errors: {len(snapshot['errors'])}, Rank changes: {len(delta['changes'])}, "
        f"Competitors entered: {len(delta['competitors_entered'])}, "
        f"Competitors dropped: {len(delta['competitors_dropped'])}, "
        f"Competitor rating/review changes: {len(delta['competitor_changes'])}"
    )


if __name__ == "__main__":
    main()
