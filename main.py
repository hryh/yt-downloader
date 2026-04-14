import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import static_ffmpeg
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="YT Batch Downloader")

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

MAX_CONCURRENT_DOWNLOADS = 3
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)

# In-memory job store
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()

# SSE broadcast infrastructure
sse_clients: List[asyncio.Queue] = []
sse_clients_lock = threading.Lock()
main_loop: Optional[asyncio.AbstractEventLoop] = None


@app.on_event("startup")
async def startup() -> None:
    global main_loop
    main_loop = asyncio.get_running_loop()
    # Add bundled FFmpeg binaries to PATH (downloads on first run, cached after)
    static_ffmpeg.add_paths()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def broadcast_update(job_id: str) -> None:
    """Thread-safe push of a job update to all SSE clients."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or not main_loop:
        return
    payload = f"data: {json.dumps({'type': 'update', 'job': job})}\n\n"
    with sse_clients_lock:
        for q in list(sse_clients):
            main_loop.call_soon_threadsafe(q.put_nowait, payload)


def make_job(job_id: str, url: str, fmt: str, quality: str) -> dict:
    return {
        "id": job_id,
        "url": url,
        "format": fmt,
        "quality": quality,
        "status": "pending",   # pending | downloading | done | error
        "progress": 0,
        "title": url,
        "filename": None,
        "error": None,
        "speed": None,
        "eta": None,
    }


# ---------------------------------------------------------------------------
# Download logic (runs in thread pool)
# ---------------------------------------------------------------------------

def _build_ydl_opts(job_id: str, fmt: str, quality: str) -> dict:
    output_template = str(DOWNLOADS_DIR / f"{job_id}_%(title)s.%(ext)s")

    postprocessors: list = []

    if fmt == "mp3":
        ydl_format = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    elif fmt == "mp4":
        height_map = {"1080": 1080, "720": 720, "480": 480}
        if quality in height_map:
            h = height_map[quality]
            ydl_format = (
                f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                f"/best[height<={h}][ext=mp4]/best"
            )
        else:
            ydl_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        # "best" — let yt-dlp decide
        ydl_format = "bestvideo+bestaudio/best"

    def progress_hook(d: dict) -> None:
        if d["status"] == "downloading":
            pct = 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = int(d.get("downloaded_bytes", 0) / total * 100)
            with jobs_lock:
                jobs[job_id]["progress"] = min(pct, 99)
                jobs[job_id]["speed"] = d.get("_speed_str", "").strip() or None
                jobs[job_id]["eta"] = d.get("_eta_str", "").strip() or None
            broadcast_update(job_id)
        elif d["status"] == "finished":
            with jobs_lock:
                jobs[job_id]["progress"] = 99   # postprocessing still pending
                jobs[job_id]["speed"] = None
                jobs[job_id]["eta"] = "merging…"
            broadcast_update(job_id)

    opts: dict = {
        "format": ydl_format,
        "outtmpl": output_template,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4" if fmt in ("mp4", "best") else None,
    }
    if postprocessors:
        opts["postprocessors"] = postprocessors
    return opts


def download_job(job_id: str) -> None:
    """Executed inside the thread-pool executor."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return

    with jobs_lock:
        jobs[job_id]["status"] = "downloading"
        jobs[job_id]["progress"] = 0
        jobs[job_id]["error"] = None
    broadcast_update(job_id)

    try:
        opts = _build_ydl_opts(job_id, job["format"], job["quality"])
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job["url"], download=True)

        title = info.get("title", job_id)

        # Find the output file (prefixed with job_id)
        files = sorted(DOWNLOADS_DIR.glob(f"{job_id}_*"))
        filename = files[0].name if files else None

        with jobs_lock:
            jobs[job_id].update(
                status="done",
                progress=100,
                title=title,
                filename=filename,
                speed=None,
                eta=None,
            )
        broadcast_update(job_id)

    except Exception as exc:
        with jobs_lock:
            jobs[job_id].update(status="error", error=str(exc), speed=None, eta=None)
        broadcast_update(job_id)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

class AddJobsRequest(BaseModel):
    urls: List[str]
    format: str = "mp4"   # mp4 | mp3 | best
    quality: str = "best" # best | 1080 | 720 | 480


@app.post("/api/jobs", status_code=201)
async def add_jobs(req: AddJobsRequest):
    created = []
    for raw_url in req.urls:
        url = raw_url.strip()
        if not url:
            continue
        job_id = uuid.uuid4().hex[:8]
        with jobs_lock:
            jobs[job_id] = make_job(job_id, url, req.format, req.quality)
        broadcast_update(job_id)
        created.append(job_id)
    return {"created": created}


@app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("pending", "error"):
        raise HTTPException(400, f"Job already in state '{job['status']}'")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, download_job, job_id)
    return {"ok": True}


@app.post("/api/start-all")
async def start_all():
    with jobs_lock:
        pending = [jid for jid, j in jobs.items() if j["status"] in ("pending", "error")]
    loop = asyncio.get_event_loop()
    for job_id in pending:
        loop.run_in_executor(executor, download_job, job_id)
    return {"started": len(pending)}


@app.get("/api/jobs")
async def list_jobs():
    with jobs_lock:
        return {"jobs": list(jobs.values())}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    with jobs_lock:
        job = jobs.pop(job_id, None)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("filename"):
        fp = DOWNLOADS_DIR / job["filename"]
        if fp.exists():
            fp.unlink()
    # Tell clients to remove this job
    payload = f"data: {json.dumps({'type': 'remove', 'id': job_id})}\n\n"
    with sse_clients_lock:
        for q in list(sse_clients):
            if main_loop:
                main_loop.call_soon_threadsafe(q.put_nowait, payload)
    return {"ok": True}


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    # Prevent path traversal
    safe = DOWNLOADS_DIR / Path(filename).name
    if not safe.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(
        safe,
        filename=safe.name,
        headers={"Content-Disposition": f'attachment; filename="{safe.name}"'},
    )


@app.get("/api/events")
async def sse_events():
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with sse_clients_lock:
        sse_clients.append(q)

    async def generate():
        try:
            # Send current state immediately on connect
            with jobs_lock:
                for job in jobs.values():
                    yield f"data: {json.dumps({'type': 'update', 'job': job})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield msg
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            with sse_clients_lock:
                try:
                    sse_clients.remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Serve frontend (must be mounted last)
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
