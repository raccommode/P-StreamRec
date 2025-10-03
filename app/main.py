import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ffmpeg_runner import FFmpegManager
import re
from urllib.parse import urlparse

# Environment
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "data")))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
HLS_TIME = int(os.getenv("HLS_TIME", "4"))
HLS_LIST_SIZE = int(os.getenv("HLS_LIST_SIZE", "6"))
CB_RESOLVER_ENABLED = os.getenv("CB_RESOLVER_ENABLED", "false").lower() in {"1", "true", "yes"}

# Ensure dirs
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="P-StreamRec", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/streams", StaticFiles(directory=str(OUTPUT_DIR)), name="streams")

manager = FFmpegManager(str(OUTPUT_DIR), ffmpeg_path=FFMPEG_PATH, hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)


class StartBody(BaseModel):
    target: str  # Either an m3u8 URL or a username (if resolver enabled)
    source_type: Optional[str] = None  # "m3u8" or "chaturbate" or None for auto
    name: Optional[str] = None  # display name
    person: Optional[str] = None  # recording bucket (per person)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "session"


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/model.html")
async def model_page():
    return FileResponse(str(STATIC_DIR / "model.html"))


@app.post("/api/start")
async def api_start(body: StartBody):
    target = (body.target or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Champ 'target' requis")

    m3u8_url: Optional[str] = None
    person: Optional[str] = (body.person or "").strip() or None

    # Determine source type
    stype = (body.source_type or "").lower().strip()

    if stype == "m3u8" or target.startswith("http://") or target.startswith("https://"):
        m3u8_url = target
    else:
        # Try chaturbate if allowed or explicit
        if stype in ("", "chaturbate"):
            if not CB_RESOLVER_ENABLED:
                raise HTTPException(status_code=400, detail="Résolution Chaturbate désactivée. Fournissez une URL m3u8 directe ou activez CB_RESOLVER_ENABLED.")
            try:
                from .resolvers.chaturbate import resolve_m3u8 as resolve_chaturbate
                m3u8_url = resolve_chaturbate(target)
                if not person:
                    person = target  # username
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Échec de résolution Chaturbate: {e}")
        else:
            raise HTTPException(status_code=400, detail="source_type invalide. Utilisez 'm3u8' ou 'chaturbate'.")

    # If person still not set (direct m3u8), infer from URL
    if not person:
        try:
            pu = urlparse(m3u8_url)
            # try last non-empty path part without extension
            parts = [p for p in pu.path.split('/') if p]
            base = parts[-2] if len(parts) >= 2 else (parts[-1] if parts else pu.hostname or "session")
            base = base.split('.')[0]
            person = base or (pu.hostname or "session")
        except Exception:
            person = "session"

    person = slugify(person)

    try:
        sess = manager.start_session(m3u8_url, person=person, display_name=body.name)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "id": sess.id,
        "person": person,
        "name": sess.name,
        "playback_url": sess.playback_url,
        "record_path": sess.record_path_today(),
        "created_at": sess.created_at,
        "running": True,
    }


@app.get("/api/status")
async def api_status():
    return manager.list_status()


@app.post("/api/stop/{session_id}")
async def api_stop(session_id: str):
    ok = manager.stop_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session introuvable")
    return {"stopped": True, "id": session_id}
