# YT Batch Downloader

A locally-hosted web app for batch downloading YouTube videos as **MP4** or **MP3**, built with Python, FastAPI, and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> **Disclaimer:** This tool is intended for **personal use and testing purposes only.**
> Only download content you own, have permission to download, or that is in the public domain / licensed under Creative Commons.
> Downloading copyrighted content without authorisation may violate YouTube's Terms of Service and applicable law in your country.
> The author does not condone or take responsibility for any misuse of this tool.

---

## Features

- Paste multiple YouTube URLs at once (batch mode)
- Choose format per batch: **MP4** (video), **MP3** (audio only), or **Best** (auto)
- Quality selector: **Best**, **1080p**, **720p**, **480p**
- Real-time progress bar with download speed and ETA
- Start all downloads at once or individually
- One-click save button when a download completes
- Runs entirely on your own machine — no data leaves your computer

---

## Requirements

| Requirement | Notes |
|---|---|
| **Python 3.10+** | [python.org](https://www.python.org/downloads/) |
| **FFmpeg** | Bundled automatically via `static-ffmpeg` — no manual install needed |

---

## Installation & Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/yt-downloader.git
cd yt-downloader
```

### 2. Create a virtual environment and install dependencies

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the app

**Windows (one-click):**

Double-click `start.bat` — it handles the venv, installs deps, and starts the server automatically.

**Manual / macOS / Linux:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Open your browser

```
http://localhost:8000
```

---

## How to use

1. **Paste URLs** — enter one or more YouTube URLs in the text box, one per line
2. **Pick a format** — choose MP4 (video), MP3 (audio), or Best (automatic)
3. **Pick quality** — choose Best, 1080p, 720p, or 480p (MP4 only)
4. **Add to queue** — click **+ Add to Queue** or press `Ctrl + Enter`
5. **Download** — click **▶ Download All** to start everything, or **▶ Start** on individual items
6. **Save** — once a download finishes, click the **↓ Save** button to save the file to your computer

Downloaded files are temporarily stored in the `downloads/` folder inside the project directory until you save or remove them.

---

## Project structure

```
yt-downloader/
├── main.py              # FastAPI backend + yt-dlp integration
├── requirements.txt     # Python dependencies
├── start.bat            # Windows one-click launcher
├── static/
│   ├── index.html       # App UI
│   ├── styles.css       # Styles
│   └── app.js           # Frontend logic + SSE progress
└── downloads/           # Temporary output folder (git-ignored)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) |
| Downloader | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Server | [Uvicorn](https://www.uvicorn.org/) |
| Frontend | Vanilla HTML / CSS / JS |
| Progress streaming | Server-Sent Events (SSE) |

---

## Updating yt-dlp

YouTube frequently changes its internal API. If downloads start failing, update yt-dlp:

```bash
pip install -U yt-dlp
```

---

## License

MIT — see [LICENSE](LICENSE)

---

*For personal use and testing only. Please respect copyright laws and content creators.*
