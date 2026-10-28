# ai-radar-feeds

Daily upload feed for **The AI Radar** Hype Leaderboard.

- `channels.json`: the YouTube channels tracked (edit this to add or remove one)
- `scripts/fetch_feeds.py`: reads each channel's public RSS feed (standard library only)
- `.github/workflows/fetch.yml`: runs every day at 06:22 IST and commits `data/uploads.json`
- `data/uploads.json`: the last 60 days of uploads across all channels

To add a channel, append `{ "name", "handle", "id", "lang", "group" }` to `channels.json` and push. The workflow reruns on push.
