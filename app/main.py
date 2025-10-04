import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ffmpeg_runner import FFmpegManager

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

# Configuration CORS permissive pour Umbrel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autoriser toutes les origines
    allow_credentials=False,  # Pas de credentials avec wildcard origin
    allow_methods=["*"],  # Autoriser toutes les méthodes (GET, POST, etc.)
    allow_headers=["*"],  # Autoriser tous les headers
)

# Static mounts
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Route protégée pour les enregistrements
@app.get("/streams/records/{username}/{filename}")
async def serve_recording_protected(username: str, filename: str):
    """Sert un enregistrement avec vérification qu'il n'est pas en cours"""
    from fastapi.responses import FileResponse
    from datetime import datetime
    
    # Sécurité: vérifier le nom de fichier
    if ".." in filename or "/" in filename or not filename.endswith(".ts"):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    
    # Vérifier que ce n'est pas l'enregistrement du jour en cours
    today = datetime.now().strftime("%Y-%m-%d")
    recording_date = filename.replace(".ts", "")
    
    # Vérifier si une session est active pour cet utilisateur
    active_sessions = manager.list_status()
    is_recording = any(s.get('person') == username and s.get('running') for s in active_sessions)
    
    if is_recording and recording_date == today:
        raise HTTPException(
            status_code=403, 
            detail="Cet enregistrement est en cours. Regardez le live à la place."
        )
    
    # Servir le fichier
    file_path = OUTPUT_DIR / "records" / username / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    
    return FileResponse(
        path=str(file_path),
        media_type="video/mp2t",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600"
        }
    )

# Mount pour les sessions HLS live uniquement
app.mount("/streams/sessions", StaticFiles(directory=str(OUTPUT_DIR / "sessions")), name="streams_sessions")
app.mount("/streams/thumbnails", StaticFiles(directory=str(OUTPUT_DIR / "thumbnails")), name="streams_thumbnails")

manager = FFmpegManager(str(OUTPUT_DIR), ffmpeg_path=FFMPEG_PATH, hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)

# Fichier de sauvegarde des modèles (côté serveur)
MODELS_FILE = OUTPUT_DIR / "models.json"

def load_models():
    """Charge la liste des modèles depuis le fichier JSON"""
    if MODELS_FILE.exists():
        try:
            with open(MODELS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_models_to_file(models):
    """Sauvegarde la liste des modèles dans le fichier JSON"""
    try:
        with open(MODELS_FILE, 'w') as f:
            json.dump(models, f, indent=2)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde modèles: {e}")
        return False


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
    """Génère miniature depuis le flux HLS si disponible, sinon fallback Chaturbate"""
    import requests
    from fastapi.responses import FileResponse, Response
    import subprocess
    import time
    
    # Dossier pour les miniatures live
    live_thumbs_dir = OUTPUT_DIR / "thumbnails" / "live"
    live_thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = live_thumbs_dir / f"{username}.jpg"
    
    # Vérifier si une session HLS est active pour ce username
    active_sessions = manager.list_status()
    session = next((s for s in active_sessions if s.get('person') == username and s.get('running')), None)
    
    # Si session active et miniature n'existe pas ou ancienne (>5min), générer depuis le stream
    if session:
        needs_update = not thumb_path.exists() or (time.time() - thumb_path.stat().st_mtime > 300)
        
        if needs_update:
            # Trouver le fichier M3U8 de la session
            session_dir = OUTPUT_DIR / "sessions" / session['id']
            m3u8_file = session_dir / "stream.m3u8"
            
            if m3u8_file.exists():
                try:
                    # Capturer une frame depuis le stream HLS
                    subprocess.run([
                        FFMPEG_PATH, "-i", str(m3u8_file),
                        "-vframes", "1",
                        "-vf", "scale=280:-1",
                        "-y",
                        str(thumb_path)
                    ], capture_output=True, timeout=5, check=False)
                except:
                    pass
        
        # Retourner la miniature générée si elle existe
        if thumb_path.exists():
            return FileResponse(
                path=str(thumb_path),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=60"}
            )
    
    # Fallback: essayer Chaturbate
    try:
        img_urls = [
            f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg",
            f"https://cbjpeg.stream.highwebmedia.com/stream?room={username}&f=.jpg",
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://chaturbate.com/",
        }
        
        for img_url in img_urls:
            try:
                response = requests.get(img_url, headers=headers, timeout=3, allow_redirects=True)
                
                if response.status_code == 200 and len(response.content) > 1000:
                    return Response(
                        content=response.content,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=60"}
                    )
            except:
                continue
    except:
        pass
    
    # SVG placeholder si tout échoue
    svg_placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="200">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#6366f1;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#a855f7;stop-opacity:1" />
            </linearGradient>
        </defs>
        <rect fill="url(#grad)" width="280" height="200"/>
        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="18" font-weight="600">{username}</text>
        <text x="50%" y="70%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="12" opacity="0.8">📷 Chargement...</text>
    </svg>'''
    
    return Response(
        content=svg_placeholder,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=10"}
    )


@app.get("/api/recordings/{username}")
async def list_recordings(username: str):
    """Liste les enregistrements disponibles pour un modèle (optimisé avec cache)"""
    import json
    from datetime import datetime
    
    records_dir = OUTPUT_DIR / "records" / username
    thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
    cache_file = OUTPUT_DIR / "records" / username / ".metadata_cache.json"
    
    if not records_dir.exists():
        return {"recordings": []}
    
    # Créer le dossier thumbnails si nécessaire
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    
    # Charger le cache
    cache = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
        except:
            cache = {}
    
    # Trouver tous les fichiers .ts
    recordings = []
    cache_updated = False
    
    for ts_file in sorted(records_dir.glob("*.ts"), reverse=True):
        stat = ts_file.stat()
        filename = ts_file.name
        file_mtime = stat.st_mtime
        
        # Vérifier si les métadonnées sont en cache et à jour
        if filename in cache and cache[filename].get('mtime') == file_mtime:
            # Utiliser le cache
            cached_data = cache[filename]
            duration_seconds = cached_data.get('duration', 0)
            duration_str = cached_data.get('duration_str', '0m00s')
        else:
            # Calculer la durée (en arrière-plan pour la prochaine fois)
            duration_seconds = 0
            try:
                import subprocess
                result = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(ts_file)
                ], capture_output=True, text=True, timeout=3)
                if result.returncode == 0 and result.stdout.strip():
                    duration_seconds = int(float(result.stdout.strip()))
            except:
                pass
            
            # Formater la durée
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            if hours > 0:
                duration_str = f"{hours}h{minutes:02d}m"
            else:
                duration_str = f"{minutes}m{seconds:02d}s"
            
            # Mettre en cache
            cache[filename] = {
                'duration': duration_seconds,
                'duration_str': duration_str,
                'mtime': file_mtime
            }
            cache_updated = True
        
        # Miniature
        thumb_path = thumbnails_dir / f"{ts_file.stem}.jpg"
        thumb_url = f"/api/recording-thumbnail/{username}/{ts_file.stem}.jpg"
        
        # Générer miniature en arrière-plan si elle n'existe pas
        if not thumb_path.exists() and stat.st_size > 1024 * 1024:
            import subprocess
            try:
                subprocess.Popen([
                    FFMPEG_PATH, "-i", str(ts_file),
                    "-ss", "00:00:10",
                    "-vframes", "1",
                    "-vf", "scale=320:-1",
                    "-y",
                    str(thumb_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass
        
        recordings.append({
            "filename": filename,
            "date": ts_file.stem,
            "size": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/streams/records/{username}/{filename}",
            "thumbnail": thumb_url if thumb_path.exists() else None,
            "duration": duration_seconds,
            "duration_str": duration_str
        })
    
    # Sauvegarder le cache si mis à jour
    if cache_updated:
        try:
            with open(cache_file, 'w') as f:
                json.dump(cache, f)
        except:
            pass
    
    return {"recordings": recordings}


@app.get("/api/recording-thumbnail/{username}/{filename}")
async def get_recording_thumbnail(username: str, filename: str):
    """Récupère la miniature d'un enregistrement"""
    from fastapi.responses import FileResponse, Response
    
    # Sécurité
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nom invalide")
    
    thumb_path = OUTPUT_DIR / "thumbnails" / username / filename
    
    if thumb_path.exists():
        return FileResponse(
            path=str(thumb_path),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    
    # Placeholder SVG si pas de miniature
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">
        <rect fill="#1a1f3a" width="320" height="180"/>
        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#a0aec0" font-size="16">📹 Génération...</text>
    </svg>'''
    
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/models")
async def get_models():
    """Récupère la liste des modèles sauvegardés"""
    models = load_models()
    return {"models": models}


@app.post("/api/models")
async def add_model(model: dict):
    """Ajoute un modèle à la liste"""
    models = load_models()
    
    # Vérifier si le modèle existe déjà
    username = model.get('username')
    if not username:
        raise HTTPException(status_code=400, detail="Username requis")
    
    # Éviter les doublons
    if any(m.get('username') == username for m in models):
        raise HTTPException(status_code=409, detail="Modèle déjà existant")
    
    models.append(model)
    
    if save_models_to_file(models):
        return {"success": True, "models": models}
    else:
        raise HTTPException(status_code=500, detail="Erreur de sauvegarde")


@app.delete("/api/models/{username}")
async def delete_model(username: str):
    """Supprime un modèle de la liste"""
    models = load_models()
    filtered = [m for m in models if m.get('username') != username]
    
    if len(filtered) == len(models):
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    
    if save_models_to_file(filtered):
        return {"success": True, "models": filtered}
    else:
        raise HTTPException(status_code=500, detail="Erreur de sauvegarde")


@app.delete("/api/recordings/{username}/{filename}")
async def delete_recording(username: str, filename: str):
    """Supprime un enregistrement (sauf celui du jour en cours)"""
    from fastapi.responses import Response
    from datetime import datetime
    
    # Sécurité
    if ".." in filename or "/" in filename or not filename.endswith(".ts"):
        raise HTTPException(status_code=400, detail="Nom invalide")
    
    # Vérifier que ce n'est pas l'enregistrement du jour en cours
    today = datetime.now().strftime("%Y-%m-%d")
    recording_date = filename.replace(".ts", "")
    
    # Vérifier si une session est active pour cet utilisateur
    active_sessions = manager.list_status()
    is_recording = any(s.get('person') == username and s.get('running') for s in active_sessions)
    
    if is_recording and recording_date == today:
        raise HTTPException(
            status_code=403, 
            detail="Impossible de supprimer l'enregistrement en cours."
        )
    
    ts_path = OUTPUT_DIR / "records" / username / filename
    thumb_path = OUTPUT_DIR / "thumbnails" / username / f"{Path(filename).stem}.jpg"
    
    if not ts_path.exists():
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    
    # Supprimer le fichier TS et la miniature
    try:
        ts_path.unlink()
        if thumb_path.exists():
            thumb_path.unlink()
        return {"success": True, "message": f"{filename} supprimé"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
