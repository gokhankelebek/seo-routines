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
    with urllib.request.urlopen(req, timeout=180) as resp:
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


def _rank(it):
    # rank_group = position among organic map listings. rank_absolute also counts
    # paid items, so our own ad at the top would look like an organic drop.
    return it.get("rank_group") or it.get("rank_absolute")


def parse_items(items, aliases, top_n):
    """Pull our rank + top competitors out of the maps items.

    Returns (our_rank, competitors, our_ad) where our_ad says whether one of
    our own paid listings was showing for this query.
    """
    our_ad = any(
        it.get("type") == "maps_paid_item" and is_brand(it.get("title"), aliases)
        for it in items
    )
    listings = [it for it in items if it.get("type") == "maps_search"]
    listings.sort(key=lambda it: _rank(it) or 999)

    our_rank = None
    competitors = []
    for it in listings:
        if is_brand(it.get("title"), aliases):
            # Our own listings (either location) are never competitors.
            if our_rank is None:
                our_rank = _rank(it)
            continue
        if len(competitors) < top_n:
            rating = it.get("rating") or {}
            competitors.append({
                "name": it.get("title"),
                "rank": _rank(it),
                "rating": rating.get("value"),
                "reviews": rating.get("votes_count"),
            })
    return our_rank, competitors, our_ad


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
                our_rank, comps, our_ad = parse_items(items, aliases, top_n)
                loc_block["keywords"][kw] = {
                    "our_rank": our_rank,
                    "our_ad_showing": our_ad,
                    "competitors": comps,
                }
            except (urllib.error.URLError, RuntimeError, ValueError, OSError) as e:
                loc_block["keywords"][kw] = {"our_rank": None, "competitors": [], "error": str(e)}
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
        "previous_date": prev.get("date") if prev else None,
        "baseline": prev is None,
        "changes": [],
        "competitor_changes": [],
    }
    if prev is None:
        return delta
    for loc_id, loc in curr["locations"].items():
        prev_loc = (prev.get("locations") or {}).get(loc_id, {})
        prev_kw = prev_loc.get("keywords", {})
        for kw, data in loc["keywords"].items():
            now = data.get("our_rank")
            before = (prev_kw.get(kw) or {}).get("our_rank")
            if now != before:
                delta["changes"].append({
                    "location": loc_id,
                    "keyword": kw,
                    "from": before,
                    "to": now,
                    "direction": _direction(before, now),
                })
            if kw not in prev_kw or data.get("error") or prev_kw[kw].get("error"):
                continue
            now_c = {c["name"]: c for c in data.get("competitors", [])}
            old_c = {c["name"]: c for c in prev_kw[kw].get("competitors", [])}
            entry = {
                "location": loc_id,
                "keyword": kw,
                "entered": [now_c[n] for n in now_c if n not in old_c],
                "dropped": [old_c[n] for n in old_c if n not in now_c],
                "moved": [],
            }
            for n in now_c:
                if n not in old_c:
                    continue
                a, b = old_c[n], now_c[n]
                if (a["rank"], a["rating"], a["reviews"]) != (b["rank"], b["rating"], b["reviews"]):
                    entry["moved"].append({
                        "name": n,
                        "rank_from": a["rank"], "rank_to": b["rank"],
                        "rating_from": a["rating"], "rating_to": b["rating"],
                        "reviews_from": a["reviews"], "reviews_to": b["reviews"],
                    })
            if entry["entered"] or entry["dropped"] or entry["moved"]:
                delta["competitor_changes"].append(entry)
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
    print(f"Errors: {len(snapshot['errors'])}, Changes: {len(delta['changes'])}")


if __name__ == "__main__":
    main()
