"""Collect recent uploads from the channels in channels.json.

Reads each channel's public YouTube RSS feed (latest ~15 videos), merges them
into data/uploads.json, and keeps a rolling window so the history grows past
the 15 items a feed returns. Standard library only.
"""
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNELS = ROOT / "channels.json"
OUT = ROOT / "data" / "uploads.json"
KEEP_DAYS = 60

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "m": "http://search.yahoo.com/mrss/",
}
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
UA = {"User-Agent": "Mozilla/5.0 (ai-radar-feeds; +https://github.com)"}


def fetch(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # YouTube feeds intermittently 404/500
            last = e
            time.sleep(2 + i * 3)
    raise last


def parse(xml_bytes, ch):
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", default="", namespaces=NS)
        link = e.find("a:link", NS)
        href = link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}"
        group = e.find("m:group", NS)
        desc = ""
        views = None
        if group is not None:
            desc = (group.findtext("m:description", default="", namespaces=NS) or "").strip()
            stats = group.find("m:community/m:statistics", NS)
            if stats is not None and stats.get("views") is not None:
                views = int(stats.get("views"))
        out.append({
            "id": vid,
            "channel": ch["name"],
            "channelId": ch["id"],
            "lang": ch.get("lang", "en"),
            "title": e.findtext("a:title", default="", namespaces=NS),
            "published": e.findtext("a:published", default="", namespaces=NS),
            "url": href,
            "isShort": "/shorts/" in href,
            "views": views,
            "description": desc[:400],
        })
    return out


def main():
    channels = json.loads(CHANNELS.read_text())["channels"]
    old = {}
    if OUT.exists():
        try:
            for v in json.loads(OUT.read_text()).get("videos", []):
                old[v["id"]] = v
        except Exception:
            old = {}

    status = []
    for ch in channels:
        try:
            vids = parse(fetch(FEED.format(ch["id"])), ch)
            for v in vids:
                old[v["id"]] = {**old.get(v["id"], {}), **v}
            status.append({"channel": ch["name"], "ok": True, "count": len(vids)})
        except Exception as e:
            status.append({"channel": ch["name"], "ok": False, "error": str(e)[:200]})
        time.sleep(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    keep = []
    for v in old.values():
        try:
            ts = datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ts >= cutoff:
            keep.append(v)
    keep.sort(key=lambda v: v["published"], reverse=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": channels,
        "status": status,
        "videos": keep,
    }, ensure_ascii=False, indent=1))
    ok = sum(1 for s in status if s["ok"])
    print(f"{ok}/{len(status)} channels fetched, {len(keep)} videos kept")


if __name__ == "__main__":
    main()
