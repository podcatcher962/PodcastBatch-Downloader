# Podcast Batch Downloader v1

> **⚠️ Disclaimer: This tool is for personal learning purposes only — Python programming, tkinter GUI development, API interaction, and web scraping techniques. Commercial use and bulk downloading are strictly prohibited. All downloaded audio content belongs to its respective platforms and copyright holders. Please delete within 24 hours and support creators through official channels. By using this tool, you accept full legal responsibility.**

---

A podcast batch downloader. Pure Python standard library + tkinter GUI. Manual access token setup required.

## Features

- Auto-fetch episode lists (batch podcast support)
- Incremental detection: skips already downloaded episodes
- Discovery tab: 47 curated podcasts
- Download queue with real-time progress
- Multi-threaded concurrent downloads
- ffmpeg M4A→MP3 transcoding (optional)
- Includes token_helper.py for auth token extraction

## Run

```bash
python xiaoyuzhou_watcher.py
```

**Requirements: Python 3.8+, ffmpeg (optional), manual access_token configuration required.**

## Get Access Token

1. Run `python token_helper.py` for auto-extraction
2. Or manually: open the web version → DevTools → Network → find any API request → copy Authorization header
3. Paste into `settings.json` `access_token` field

## Tech Stack

`tkinter` / `urllib` / `re` / `threading` / `sqlite3` / `json` — pure stdlib, zero dependencies

## License

MIT License.
