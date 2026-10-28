"""Turn creator uploads + topic tags into The AI Radar's Hype Leaderboard.

Usage:
  python build_leaderboard.py UPLOADS TOPICS OUT [--prev PREV] [--date YYYY-MM-DD] [--window 14]

UPLOADS  data/uploads.json from this repo
TOPICS   JSON written by the daily run (Claude) after reading the video titles:
         {
           "summary": "two sentences",
           "topics": [{"id", "topic", "category", "videoIds": [...],
                       "radar": bool, "action": "optional advice"}],
           "aheadOfCreators": [{"topic", "note", "radarDate"}]
         }
PREV     yesterday's leaderboard (optional) for rank movement
All counting, dates, phases and scores are computed here so they stay consistent.
"""
import argparse
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
PHASE_ADVICE = {
    "emerging": "Get in first: one or two creators so far, and it's fresh.",
    "heating": "Your window: several creators are on it and the audience is forming.",
    "peak": "Ride it with a different angle: everyone is covering this.",
    "cooling": "Late: only cover it if there's genuinely new news.",
    "niche": "One or two creators with little traction: fine as a Short, not a main video.",
}


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uploads")
    ap.add_argument("topics")
    ap.add_argument("out")
    ap.add_argument("--prev")
    ap.add_argument("--date")
    ap.add_argument("--window", type=int, default=14)
    a = ap.parse_args()

    up = json.load(open(a.uploads))
    tags = json.load(open(a.topics))
    prev = None
    if a.prev:
        try:
            prev = json.load(open(a.prev))
        except Exception:
            prev = None

    today = date.fromisoformat(a.date) if a.date else datetime.now(timezone.utc).date()
    now = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
    start = now - timedelta(days=a.window)

    channels = {c["name"]: c for c in up.get("channels", [])}
    vids = {}
    for v in up.get("videos", []):
        try:
            ts = parse_ts(v["published"])
        except Exception:
            continue
        if start <= ts <= now:
            vids[v["id"]] = {**v, "_ts": ts}

    def is_hindi(v):
        ch = channels.get(v["channel"], {})
        t = v.get("title", "")
        return ch.get("lang") == "hi" or bool(DEVANAGARI.search(t)) or "hindi" in t.lower()

    prev_rank = {}
    if prev:
        for i, t in enumerate(prev.get("topics", [])):
            prev_rank[t["id"]] = i + 1

    topics = []
    for t in tags.get("topics", []):
        tv = [vids[i] for i in t.get("videoIds", []) if i in vids]
        if not tv:
            continue
        tv.sort(key=lambda v: v["_ts"], reverse=True)
        chs = []
        for v in tv:
            if v["channel"] not in chs:
                chs.append(v["channel"])
        views = sum(v.get("views") or 0 for v in tv)
        first = min(v["_ts"] for v in tv).date()
        latest = max(v["_ts"] for v in tv).date()
        fresh = sum(1 for v in tv if (now - v["_ts"]).days <= 3) / len(tv)
        n = len(chs)

        age_latest = (today - latest).days
        age_first = (today - first).days
        if age_latest > 6:
            phase = "cooling"
        elif n >= 5:
            phase = "peak"
        elif n >= 3:
            phase = "heating"
        elif age_first <= 5 and (t.get("radar") or views >= 20000):
            phase = "emerging"
        else:
            phase = "niche"

        hype = 50 * min(n / 6, 1) + 20 * fresh + 30 * min(math.log10(views + 1) / 6.5, 1)
        if phase == "cooling":
            hype *= 0.6
        topics.append({
            "id": t["id"],
            "topic": t["topic"],
            "category": t.get("category", ""),
            "phase": phase,
            "hype": round(hype),
            "channelCount": n,
            "videoCount": len(tv),
            "views": views,
            "channels": chs,
            "firstSeen": first.isoformat(),
            "latest": latest.isoformat(),
            "hindi": "covered" if any(is_hindi(v) for v in tv) else "open",
            "radar": bool(t.get("radar")),
            "action": t.get("action") or PHASE_ADVICE[phase],
            "videos": [{
                "channel": v["channel"], "title": v["title"], "url": v["url"],
                "date": v["_ts"].date().isoformat(), "views": v.get("views"),
                "isShort": v.get("isShort", False),
            } for v in tv[:12]],
        })

    topics.sort(key=lambda t: (t["hype"], t["channelCount"], t["views"]), reverse=True)
    for i, t in enumerate(topics):
        r = prev_rank.get(t["id"])
        if not prev:
            t["change"] = "NEW"
        elif r is None:
            t["change"] = "NEW"
        elif r == i + 1:
            t["change"] = "="
        else:
            t["change"] = ("▲" if r > i + 1 else "▼") + str(abs(r - (i + 1)))

    topic_of = {}
    for t in topics:
        for v in t["videos"]:
            topic_of.setdefault(v["url"], []).append(t["id"])
    by_ch = []
    for name, c in channels.items():
        cv = sorted([v for v in vids.values() if v["channel"] == name], key=lambda v: v["_ts"], reverse=True)
        tids = []
        for t in topics:
            if name in t["channels"]:
                tids.append(t["id"])
        by_ch.append({
            "name": name,
            "handle": c.get("handle", ""),
            "group": c.get("group", ""),
            "lang": c.get("lang", "en"),
            "uploads": len(cv),
            "latestTitle": cv[0]["title"] if cv else "",
            "latestUrl": cv[0]["url"] if cv else "",
            "latestDate": cv[0]["_ts"].date().isoformat() if cv else "",
            "topics": tids,
        })
    by_ch.sort(key=lambda c: (c["uploads"], c["latestDate"]), reverse=True)

    out = {
        "date": today.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataAsOf": up.get("fetchedAt", ""),
        "windowDays": a.window,
        "channelsTracked": len(channels),
        "channelsOk": sum(1 for s in up.get("status", []) if s.get("ok")),
        "videosScanned": len(vids),
        "summary": tags.get("summary", ""),
        "topics": topics,
        "aheadOfCreators": tags.get("aheadOfCreators", []),
        "channels": by_ch,
    }
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(topics)} topics, {len(vids)} videos, {len(channels)} channels -> {a.out}")


if __name__ == "__main__":
    main()
