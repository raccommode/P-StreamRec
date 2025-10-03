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
    print(f"\n{'='*60}")
    print(f"🎯 REQUÊTE /api/start")
    print(f"{'='*60}")
    print(f"📥 Body: {body}")
    
    target = (body.target or "").strip()
    if not target:
        print(f"❌ Champ 'target' vide")
        raise HTTPException(status_code=400, detail="Champ 'target' requis")

    print(f"🎯 Target: {target}")
    print(f"🔖 Source type: {body.source_type}")
    print(f"👤 Person: {body.person}")
    print(f"📛 Name: {body.name}")

    m3u8_url: Optional[str] = None
    person: Optional[str] = (body.person or "").strip() or None

    # Determine source type
    stype = (body.source_type or "").lower().strip()
    print(f"📌 Source type déterminé: {stype or 'auto'}")

    if stype == "m3u8" or target.startswith("http://") or target.startswith("https://"):
        print(f"✅ URL M3U8 directe détectée")
        m3u8_url = target
    else:
        print(f"🔍 Résolution Chaturbate requise...")
        # Try chaturbate if allowed or explicit
        if stype in ("", "chaturbate"):
            if not CB_RESOLVER_ENABLED:
                print(f"❌ CB_RESOLVER_ENABLED est désactivé")
                raise HTTPException(status_code=400, detail="Résolution Chaturbate désactivée. Fournissez une URL m3u8 directe ou activez CB_RESOLVER_ENABLED.")
            try:
                print(f"🔄 Appel du resolver Chaturbate...")
                from .resolvers.chaturbate import resolve_m3u8 as resolve_chaturbate
                m3u8_url = resolve_chaturbate(target)
                if not m3u8_url:
                    print(f"❌ Resolver a retourné None")
                    raise HTTPException(status_code=400, detail=f"Impossible de trouver le flux pour {target}")
                print(f"✅ M3U8 résolu: {m3u8_url}")
                if not person:
                    person = target  # username
                    print(f"👤 Person défini: {person}")
            except HTTPException:
                raise
            except Exception as e:
                import traceback
                error_detail = f"Échec résolution Chaturbate pour {target}: {str(e)}"
                print(f"❌ ERROR: {error_detail}")
                print(traceback.format_exc())
                raise HTTPException(status_code=400, detail=error_detail)
        else:
            print(f"❌ Source type invalide: {stype}")
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
    print(f"🔖 Person slugifié: {person}")
    print(f"\n🚀 Démarrage de la session FFmpeg...")

    try:
        sess = manager.start_session(m3u8_url, person=person, display_name=body.name)
        print(f"✅ Session créée avec succès: {sess.id}")
    except RuntimeError as e:
        print(f"❌ RuntimeError: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

    print(f"{'='*60}")
    print(f"✅ SUCCÈS - Session {sess.id} démarrée")
    print(f"{'='*60}\n")

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


@app.get("/api/model/{username}/status")
async def get_model_status(username: str):
    """Récupère le statut et les infos d'un modèle Chaturbate"""
    if not CB_RESOLVER_ENABLED:
        raise HTTPException(status_code=400, detail="Résolution Chaturbate désactivée")
    
    try:
        import requests
        url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Utiliser le proxy local pour les miniatures
            thumbnail = f"/api/thumbnail/{username}"
            
            return {
                "username": username,
                "isOnline": data.get("room_status") == "public" or bool(data.get("hls_source")),
                "thumbnail": thumbnail,
                "viewers": data.get("num_users", 0)
            }
        else:
            # Fallback si l'API ne répond pas
            return {
                "username": username,
                "isOnline": False,
                "thumbnail": f"/api/thumbnail/{username}",
                "viewers": 0
            }
    except Exception as e:
        # En cas d'erreur, retourner offline
        return {
            "username": username,
            "isOnline": False,
            "thumbnail": f"/api/thumbnail/{username}",
            "viewers": 0
        }


@app.get("/api/thumbnail/{username}")
async def get_thumbnail(username: str):
    """Proxy pour récupérer les miniatures Chaturbate"""
    import requests
    from fastapi.responses import Response
    
    try:
        # URL directe de l'image Chaturbate
        img_url = f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg"
        
        # Récupérer l'image
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://chaturbate.com/",
        }
        
        response = requests.get(img_url, headers=headers, timeout=5, allow_redirects=True)
        
        if response.status_code == 200:
            return Response(
                content=response.content,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=600",
                }
            )
        
        # Si erreur, retourner image par défaut (SVG placeholder)
        svg_placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="200">
            <rect fill="#1a1f3a" width="280" height="200"/>
            <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#a0aec0" font-family="system-ui" font-size="16">{username}</text>
        </svg>'''
        
        return Response(
            content=svg_placeholder,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=60"}
        )
            
    except Exception as e:
        # SVG placeholder en cas d'erreur
        svg_placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="200">
            <rect fill="#1a1f3a" width="280" height="200"/>
            <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#a0aec0" font-family="system-ui" font-size="16">{username}</text>
        </svg>'''
        
        return Response(
            content=svg_placeholder,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=60"}
        )
