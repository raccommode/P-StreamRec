import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import os
import asyncio
import requests
import json
import subprocess
import sys
import time
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .ffmpeg_runner import FFmpegManager
from .logger import logger
from .core.database import Database
from .tasks.monitor import monitor_models_task

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

logger.info("📂 Répertoire de sortie", path=str(OUTPUT_DIR))
logger.info("🎥 FFmpeg path", path=FFMPEG_PATH)
logger.info("⚙️  HLS Configuration", hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)
logger.info("🔧 Chaturbate Resolver", enabled=CB_RESOLVER_ENABLED)

app = FastAPI(title="P-StreamRec", version="0.1.0")

# Middleware pour logger toutes les requêtes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log requête
    logger.api_request(request.method, request.url.path)
    
    # Traiter requête
    response = await call_next(request)
    
    # Log réponse
    duration_ms = (time.time() - start_time) * 1000
    logger.api_response(response.status_code, request.url.path, duration_ms)
    
    return response

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
    
    logger.api_request("GET", f"/streams/records/{username}/{filename}")
    
    # Sécurité: vérifier le nom de fichier
    if ".." in filename or "/" in filename or not filename.endswith(".ts"):
        logger.warning("Tentative d'accès fichier invalide", username=username, filename=filename)
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    
    # Vérifier que ce n'est pas l'enregistrement du jour en cours
    today = datetime.now().strftime("%Y-%m-%d")
    recording_date = filename.replace(".ts", "")
    
    # Vérifier si une session est active pour cet utilisateur
    active_sessions = manager.list_status()
    is_recording = any(s.get('person') == username and s.get('running') for s in active_sessions)
    
    if is_recording and recording_date == today:
        logger.warning("Accès bloqué à enregistrement en cours", username=username, filename=filename, date=today)
        raise HTTPException(
            status_code=403, 
            detail="Cet enregistrement est en cours. Regardez le live à la place."
        )
    
    # Servir le fichier
    file_path = OUTPUT_DIR / "records" / username / filename
    
    if not file_path.exists():
        logger.error("Fichier introuvable", username=username, filename=filename, path=str(file_path))
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    
    file_size = file_path.stat().st_size
    logger.file_operation("Lecture", str(file_path), size=file_size)
    
    return FileResponse(
        path=str(file_path),
        media_type="video/mp2t",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes"  # Important pour la lecture vidéo
        }
    )

# Mount pour les sessions HLS live uniquement
app.mount("/streams/sessions", StaticFiles(directory=str(OUTPUT_DIR / "sessions")), name="streams_sessions")
app.mount("/streams/thumbnails", StaticFiles(directory=str(OUTPUT_DIR / "thumbnails")), name="streams_thumbnails")

manager = FFmpegManager(str(OUTPUT_DIR), ffmpeg_path=FFMPEG_PATH, hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)

# Database SQLite
DB_FILE = OUTPUT_DIR / "streamrec.db"
db = Database(DB_FILE)

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
        logger.error("Erreur sauvegarde modèles", exc_info=True, error=str(e))
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


@app.get("/favicon.ico")
async def favicon():
    """Retourne un favicon SVG simple"""
    from fastapi.responses import Response
    svg_favicon = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#6366f1"/>
        <circle cx="50" cy="35" r="8" fill="white"/>
        <rect x="35" y="45" width="30" height="35" rx="5" fill="white"/>
        <rect x="42" y="52" width="16" height="20" fill="#6366f1"/>
    </svg>'''
    return Response(content=svg_favicon, media_type="image/svg+xml")


@app.get("/api/version")
async def get_version():
    """Retourne les informations de version"""
    version_file = BASE_DIR / "version.json"
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lecture version.json: {e}")
    else:
        logger.warning(f"Fichier version.json introuvable: {version_file}")
    return {"version": "1.0.0", "releaseDate": "2025-10-05"}


# ============================================
# GitOps Endpoints
# ============================================

@app.get("/api/git/status")
async def git_status():
    """Vérifie s'il y a des mises à jour disponibles depuis Git"""
    try:
        # Vérifier si on est dans un repo Git
        is_git = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).returncode == 0
        
        if not is_git:
            return {
                "isGitRepo": False,
                "message": "Not a Git repository"
            }
        
        # Récupérer le commit actuel
        current_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Récupérer la branche actuelle
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Fetch pour vérifier les updates
        subprocess.run(
            ["git", "fetch"],
            cwd=BASE_DIR,
            capture_output=True
        )
        
        # Vérifier s'il y a des commits en avance sur origin
        remote_commit = subprocess.run(
            ["git", "rev-parse", f"origin/{current_branch}"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        has_updates = current_commit != remote_commit
        
        # Compter les commits en retard
        if has_updates:
            behind_count = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..origin/{current_branch}"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True
            ).stdout.strip()
        else:
            behind_count = "0"
        
        return {
            "isGitRepo": True,
            "currentBranch": current_branch,
            "currentCommit": current_commit[:8],
            "remoteCommit": remote_commit[:8],
            "hasUpdates": has_updates,
            "behindBy": int(behind_count),
            "canUpdate": has_updates
        }
        
    except Exception as e:
        return {
            "isGitRepo": False,
            "error": str(e)
        }


@app.post("/api/git/update")
async def git_update():
    """Effectue un git pull et redémarre l'application"""
    try:
        # Vérifier si on est dans un repo Git
        is_git = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).returncode == 0
        
        if not is_git:
            raise HTTPException(status_code=400, detail="Not a Git repository")
        
        # Sauvegarder le commit actuel
        old_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Git pull
        pull_result = subprocess.run(
            ["git", "pull"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        )
        
        if pull_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Git pull failed: {pull_result.stderr}"
            )
        
        # Nouveau commit
        new_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        updated = old_commit != new_commit
        
        # Si des changements ont été appliqués, redémarrer
        if updated:
            # Planifier le redémarrage dans 2 secondes
            asyncio.create_task(restart_application())
            
            return {
                "success": True,
                "updated": True,
                "oldCommit": old_commit[:8],
                "newCommit": new_commit[:8],
                "message": "Update applied. Application will restart in 2 seconds...",
                "output": pull_result.stdout
            }
        else:
            return {
                "success": True,
                "updated": False,
                "commit": new_commit[:8],
                "message": "Already up to date",
                "output": pull_result.stdout
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def restart_application():
    """Redémarre l'application après un délai"""
    await asyncio.sleep(2)
    logger.info("🔄 Redémarrage application après GitOps update")
    
    # Si on utilise uvicorn avec --reload, toucher un fichier Python suffit
    try:
        # Toucher main.py pour déclencher le reload
        Path(__file__).touch()
    except:
        # Sinon, exit et laisser le processus manager redémarrer
        os.execv(sys.executable, [sys.executable] + sys.argv)


@app.get("/model.html")
async def model_page():
    return FileResponse(str(STATIC_DIR / "model.html"))


@app.post("/api/start")
async def api_start(body: StartBody):
    start_time = time.time()
    logger.section("🎯 API /api/start - Démarrage Enregistrement")
    logger.debug("Requête reçue", 
                target=body.target, 
                source_type=body.source_type,
                person=body.person,
                name=body.name)
    
    target = (body.target or "").strip()
    if not target:
        logger.error("Champ 'target' vide dans la requête")
        raise HTTPException(status_code=400, detail="Champ 'target' requis")

    logger.info("Paramètres validés", target=target, source_type=body.source_type)

    m3u8_url: Optional[str] = None
    person: Optional[str] = (body.person or "").strip() or None

    # Determine source type
    stype = (body.source_type or "").lower().strip()
    logger.debug("Détermination type source", source_type=stype or 'auto', target=target)

    if stype == "m3u8" or target.startswith("http://") or target.startswith("https://"):
        logger.info("URL M3U8 directe détectée", url=target[:80])
        m3u8_url = target
    else:
        logger.subsection("Résolution Chaturbate")
        # Try chaturbate if allowed or explicit
        if stype in ("", "chaturbate"):
            if not CB_RESOLVER_ENABLED:
                logger.error("Chaturbate Resolver désactivé", CB_RESOLVER_ENABLED=False)
                raise HTTPException(status_code=400, detail="Résolution Chaturbate désactivée. Fournissez une URL m3u8 directe ou activez CB_RESOLVER_ENABLED.")
            try:
                logger.progress("Appel Chaturbate Resolver", username=target)
                from .resolvers.chaturbate import resolve_m3u8 as resolve_chaturbate
                m3u8_url = resolve_chaturbate(target)
                if not m3u8_url:
                    logger.error("Resolver retourné None", username=target)
                    raise HTTPException(status_code=400, detail=f"Impossible de trouver le flux pour {target}")
                logger.success("M3U8 résolu", username=target, url=m3u8_url[:80])
                if not person:
                    person = target  # username
                    logger.debug("Person défini depuis target", person=person)
            except HTTPException:
                raise
            except Exception as e:
                error_detail = f"Échec résolution Chaturbate pour {target}: {str(e)}"
                logger.error(error_detail, exc_info=True, username=target)
                raise HTTPException(status_code=400, detail=error_detail)
        else:
            logger.error("Source type invalide", source_type=stype)
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
    logger.info("Identifiant slugifié", person=person, display_name=body.name)

    logger.subsection("🚀 Démarrage Session FFmpeg")
    try:
        sess = manager.start_session(m3u8_url, person=person, display_name=body.name)
        duration_ms = (time.time() - start_time) * 1000
        logger.success("Session créée avec succès", 
                      session_id=sess.id,
                      person=person,
                      duration_ms=f"{duration_ms:.2f}")
    except RuntimeError as e:
        logger.error("Session déjà en cours", person=person, error=str(e))
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.critical("Erreur création session", exc_info=True, person=person, error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

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
    """Récupère le statut et les infos d'un modèle depuis le cache SQLite"""
    # Lire directement depuis le cache SQLite (mis à jour par la tâche de monitoring)
    model = await db.get_model(username)
    
    if model:
        return {
            "username": username,
            "isOnline": bool(model.get('is_online')),
            "thumbnail": f"/api/thumbnail/{username}",
            "viewers": model.get('viewers', 0)
        }
    else:
        # Modèle non trouvé dans le cache
        return {
            "username": username,
            "isOnline": False,
            "thumbnail": f"/api/thumbnail/{username}",
            "viewers": 0
        }


@app.get("/api/thumbnail/{username}")
async def get_thumbnail(username: str):
    """Sert la miniature depuis le cache (générée par la tâche de monitoring)"""
    from fastapi.responses import FileResponse, Response
    
    # Récupérer le chemin de la miniature depuis SQLite
    model = await db.get_model(username)
    
    if model and model.get('thumbnail_path'):
        thumb_path = Path(model['thumbnail_path'])
        
        if thumb_path.exists():
            return FileResponse(
                path=str(thumb_path),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=60"}
            )
    
    # Chercher manuellement dans les dossiers si pas en cache
    # Ordre de préférence: live > chaturbate > offline
    for subdir in ["live", "chaturbate", "offline"]:
        thumb_path = OUTPUT_DIR / "thumbnails" / subdir / f"{username}.jpg"
        if thumb_path.exists():
            return FileResponse(
                path=str(thumb_path),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=60"}
            )
    
    # SVG placeholder si aucune miniature trouvée
    svg_placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="200">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#6366f1;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#a855f7;stop-opacity:1" />
            </linearGradient>
        </defs>
        <rect fill="url(#grad)" width="280" height="200"/>
        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="18" font-weight="600">{username}</text>
        <text x="50%" y="70%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="12" opacity="0.8">📷 Loading...</text>
    </svg>'''
    
    return Response(
        content=svg_placeholder,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=10"}
    )


@app.get("/api/dashboard")
async def get_dashboard():
    """
    Endpoint optimisé qui retourne TOUTES les données depuis le cache SQLite
    Ultra-rapide car tout est pré-calculé par la tâche de monitoring
    """
    try:
        # Récupérer tous les modèles depuis SQLite (déjà avec statut à jour)
        models = await db.get_all_models()
        
        # Récupérer les sessions actives
        active_sessions = manager.list_status()
        
        # Formater les données pour le frontend
        models_info = []
        
        for model in models:
            username = model['username']
            
            # Récupérer le nombre d'enregistrements depuis SQLite
            recordings_count = await db.get_recordings_count(username)
            
            model_info = {
                "username": username,
                "isOnline": bool(model.get('is_online', False)),
                "isRecording": bool(model.get('is_recording', False)),
                "viewers": model.get('viewers', 0),
                "thumbnail": f"/api/thumbnail/{username}",
                "recordingsCount": recordings_count,
                "recordQuality": model.get('record_quality', 'best'),
                "retentionDays": model.get('retention_days', 30),
                "autoRecord": bool(model.get('auto_record', True))
            }
            
            models_info.append(model_info)
        
        # Retourner tout d'un coup
        return {
            "models": models_info,
            "sessions": active_sessions,
            "timestamp": int(time.time() * 1000)
        }
    
    except Exception as e:
        logger.error("Erreur dashboard", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/{username}")
async def list_recordings(username: str):
    """Liste les enregistrements depuis le cache SQLite (ultra-rapide)"""
    from datetime import datetime
    
    # Récupérer depuis SQLite
    recordings_db = await db.get_recordings(username)
    
    recordings = []
    thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
    
    for rec in recordings_db:
        filename = rec['filename']
        file_path = Path(rec['file_path'])
        
        # Vérifier que le fichier existe toujours
        if not file_path.exists():
            continue
        
        stat = file_path.stat()
        
        # Miniature
        thumb_path = thumbnails_dir / f"{file_path.stem}.jpg"
        thumb_url = f"/api/recording-thumbnail/{username}/{file_path.stem}.jpg"
        
        # Formater la durée
        duration_seconds = rec.get('duration_seconds', 0)
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        if hours > 0:
            duration_str = f"{hours}h{minutes:02d}m"
        else:
            duration_str = f"{minutes}m{seconds:02d}s"
        
        recordings.append({
            "filename": filename,
            "date": file_path.stem,
            "size": rec['file_size'],
            "size_mb": round(rec['file_size'] / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/streams/records/{username}/{filename}",
            "thumbnail": thumb_url if thumb_path.exists() else None,
            "duration": duration_seconds,
            "duration_str": duration_str
        })
    
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
    """Récupère la liste des modèles depuis SQLite"""
    models = await db.get_all_models()
    
    # Formater pour compatibilité avec le frontend
    formatted_models = []
    for model in models:
        formatted_models.append({
            "username": model['username'],
            "autoRecord": bool(model.get('auto_record', True)),
            "recordQuality": model.get('record_quality', 'best'),
            "retentionDays": model.get('retention_days', 30)
        })
    
    return {"models": formatted_models}


@app.post("/api/models")
async def add_model(model: dict):
    """Ajoute un modèle dans SQLite"""
    username = model.get('username')
    if not username:
        raise HTTPException(status_code=400, detail="Username requis")
    
    # Vérifier si le modèle existe déjà
    existing = await db.get_model(username)
    if existing:
        raise HTTPException(status_code=409, detail="Modèle déjà existant")
    
    # Ajouter dans SQLite
    await db.add_or_update_model(
        username=username,
        auto_record=model.get('autoRecord', True),
        record_quality=model.get('recordQuality', 'best'),
        retention_days=model.get('retentionDays', 30)
    )
    
    # Récupérer tous les modèles pour retourner
    all_models = await db.get_all_models()
    formatted = [{
        "username": m['username'],
        "autoRecord": bool(m.get('auto_record', True)),
        "recordQuality": m.get('record_quality', 'best'),
        "retentionDays": m.get('retention_days', 30)
    } for m in all_models]
    
    return {"success": True, "models": formatted}


@app.put("/api/models/{username}")
async def update_model(username: str, model_data: dict):
    """Met à jour les paramètres d'un modèle dans SQLite"""
    # Vérifier si le modèle existe
    existing = await db.get_model(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    
    # Mettre à jour dans SQLite
    await db.add_or_update_model(
        username=username,
        auto_record=model_data.get('autoRecord', existing.get('auto_record', True)),
        record_quality=model_data.get('recordQuality', existing.get('record_quality', 'best')),
        retention_days=model_data.get('retentionDays', existing.get('retention_days', 30))
    )
    
    # Récupérer le modèle mis à jour
    updated = await db.get_model(username)
    
    return {
        "success": True,
        "model": {
            "username": updated['username'],
            "autoRecord": bool(updated.get('auto_record', True)),
            "recordQuality": updated.get('record_quality', 'best'),
            "retentionDays": updated.get('retention_days', 30)
        }
    }


@app.delete("/api/models/{username}")
async def delete_model(username: str):
    """Supprime un modèle de SQLite"""
    # Vérifier si le modèle existe
    existing = await db.get_model(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    
    # Supprimer de SQLite
    await db.delete_model(username)
    
    # Récupérer la liste mise à jour
    all_models = await db.get_all_models()
    formatted = [{
        "username": m['username'],
        "autoRecord": bool(m.get('auto_record', True)),
        "recordQuality": m.get('record_quality', 'best'),
        "retentionDays": m.get('retention_days', 30)
    } for m in all_models]
    
    return {"success": True, "models": formatted}


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


@app.post("/api/recordings/recalculate-durations")
async def recalculate_all_durations():
    """Recalcule les durées de tous les enregistrements"""
    from app.tasks.monitor import get_video_duration, generate_recording_thumbnail
    
    logger.info("🔄 API: Demande de recalcul des durées")
    
    try:
        # Créer une tâche en arrière-plan
        asyncio.create_task(_recalculate_durations_task())
        
        return {
            "success": True,
            "message": "Recalcul des durées démarré en arrière-plan"
        }
    except Exception as e:
        logger.error("Erreur lancement recalcul durées", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _recalculate_durations_task():
    """Tâche de recalcul des durées en arrière-plan"""
    from app.tasks.monitor import get_video_duration, generate_recording_thumbnail
    
    logger.background_task("recalculate-durations", "Démarrage du recalcul")
    
    try:
        # Récupérer tous les modèles
        models = await db.get_all_models()
        
        total_processed = 0
        total_updated = 0
        
        for model in models:
            username = model['username']
            records_dir = OUTPUT_DIR / "records" / username
            
            if not records_dir.exists():
                continue
            
            logger.info(f"📁 Recalcul durées: {username}")
            
            ts_files = list(records_dir.glob("*.ts"))
            
            for ts_file in ts_files:
                try:
                    total_processed += 1
                    
                    # Récupérer l'enregistrement depuis la DB
                    recordings = await db.get_recordings(username)
                    existing_rec = next((r for r in recordings if r['filename'] == ts_file.name), None)
                    
                    current_duration = 0
                    if existing_rec:
                        current_duration = existing_rec.get('duration_seconds', 0)
                    
                    # Calculer la durée si elle est à 0
                    if current_duration == 0:
                        duration = await get_video_duration(ts_file, FFMPEG_PATH)
                        
                        if duration > 0:
                            # Générer aussi la miniature
                            thumbnail_path = await generate_recording_thumbnail(
                                ts_file, OUTPUT_DIR, username, FFMPEG_PATH
                            )
                            
                            # Mettre à jour dans la DB
                            await db.add_or_update_recording(
                                username=username,
                                filename=ts_file.name,
                                file_path=str(ts_file),
                                file_size=ts_file.stat().st_size,
                                duration_seconds=duration,
                                thumbnail_path=thumbnail_path
                            )
                            
                            total_updated += 1
                            
                            logger.success(f"Durée calculée: {ts_file.name} = {duration}s", 
                                         username=username, 
                                         duration=duration)
                        
                except Exception as e:
                    logger.error(f"Erreur recalcul: {ts_file.name}", 
                               username=username, 
                               error=str(e))
                    continue
        
        logger.success(f"✅ Recalcul terminé: {total_updated}/{total_processed} mis à jour",
                      task="recalculate-durations")
        
    except Exception as e:
        logger.error("Erreur tâche recalcul durées", 
                    task="recalculate-durations", 
                    error=str(e), 
                    exc_info=True)


# ============================================
# Background Task - Auto-enregistrement
# ============================================

async def auto_record_task():
    """Vérifie automatiquement les modèles et lance les enregistrements (utilise SQLite)"""
    while True:
        try:
            await asyncio.sleep(120)  # Vérifier toutes les 2 minutes
            
            # Charger les modèles depuis SQLite avec auto_record activé
            models = await db.get_models_for_auto_record()
            if not models:
                continue
            
            # Récupérer les sessions actives
            active_sessions = manager.list_status()
            
            for model in models:
                username = model.get('username')
                
                if not username:
                    continue
                
                # Vérifier si déjà en enregistrement
                is_recording = any(
                    s.get('person') == username and s.get('running')
                    for s in active_sessions
                )
                
                if is_recording:
                    continue  # Déjà en cours
                
                # Vérifier le statut depuis le cache SQLite (mis à jour par monitor)
                cached_status = await db.get_model(username)
                
                if cached_status and cached_status.get('is_online'):
                    # Modèle en ligne selon le cache, vérifier le flux HLS
                    try:
                        api_url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Referer": "https://chaturbate.com/",
                        }
                        
                        resp = requests.get(api_url, headers=headers, timeout=10)
                        if resp.status_code == 200:
                            data = resp.json()
                            hls_source = data.get('hls_source')
                            
                            if hls_source:
                                # Lancer l'enregistrement
                                logger.background_task("auto-record", f"Modèle en ligne: {username}")
                                
                                try:
                                    sess = manager.start_session(
                                        input_url=hls_source,
                                        display_name=username,
                                        person=username
                                    )
                                    
                                    if sess:
                                        logger.success("Auto-enregistrement démarré", 
                                                     task="auto-record",
                                                     username=username,
                                                     session_id=sess.id)
                                except RuntimeError as e:
                                    logger.warning("Impossible démarrer enregistrement",
                                                 task="auto-record",
                                                 username=username,
                                                 error=str(e))
                                    continue
                                
                    except Exception as e:
                        logger.error("Erreur vérification modèle",
                                   task="auto-record",
                                   username=username,
                                   error=str(e))
                        continue
                
        except Exception as e:
            logger.error("Erreur auto-record task", task="auto-record", exc_info=True, error=str(e))
            await asyncio.sleep(60)


async def cleanup_old_recordings_task():
    """Nettoie automatiquement les anciennes rediffusions selon la rétention configurée"""
    from datetime import datetime, timedelta
    
    while True:
        try:
            await asyncio.sleep(3600)  # Vérifier toutes les heures
            
            logger.background_task("cleanup", "Début nettoyage anciennes rediffusions")
            
            # Charger les modèles depuis SQLite avec leurs paramètres de rétention
            models = await db.get_all_models()
            
            for model in models:
                username = model.get('username')
                retention_days = model.get('retention_days', 30)  # Défaut 30 jours
                
                if not username:
                    continue
                
                records_dir = OUTPUT_DIR / "records" / username
                thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
                
                if not records_dir.exists():
                    continue
                
                # Date limite (aujourd'hui - rétention)
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                
                # Parcourir les fichiers .ts
                for ts_file in records_dir.glob("*.ts"):
                    try:
                        # Le nom du fichier est au format YYYY-MM-DD.ts
                        date_str = ts_file.stem  # Enlève .ts
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        # Si le fichier est plus vieux que la limite
                        if file_date < cutoff_date:
                            # Supprimer le fichier TS
                            file_size = ts_file.stat().st_size
                            ts_file.unlink()
                            logger.info("Fichier supprimé (rétention)",
                                      task="cleanup",
                                      username=username,
                                      filename=ts_file.name,
                                      retention_days=retention_days,
                                      size_mb=f"{file_size / 1024 / 1024:.1f}")
                            
                            # Supprimer la miniature associée
                            thumb_file = thumbnails_dir / f"{ts_file.stem}.jpg"
                            if thumb_file.exists():
                                thumb_file.unlink()
                            
                            # Supprimer l'entrée du cache
                            cache_file = records_dir / ".metadata_cache.json"
                            if cache_file.exists():
                                try:
                                    with open(cache_file, 'r') as f:
                                        cache = json.load(f)
                                    if ts_file.name in cache:
                                        del cache[ts_file.name]
                                        with open(cache_file, 'w') as f:
                                            json.dump(cache, f)
                                except:
                                    pass
                                    
                    except Exception as e:
                        logger.error("Erreur nettoyage fichier",
                                   task="cleanup",
                                   filename=ts_file.name,
                                   error=str(e))
                        continue
                        
        except Exception as e:
            logger.error("Erreur cleanup task", task="cleanup", exc_info=True, error=str(e))
            await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event():
    """Démarre les background tasks au démarrage de l'application"""
    # Initialiser la base de données
    await db.initialize()
    
    # Migrer les données depuis le JSON si nécessaire
    await db.migrate_from_json(MODELS_FILE)
    
    # Démarrer les tâches de fond
    asyncio.create_task(monitor_models_task(db, manager, FFMPEG_PATH))
    asyncio.create_task(auto_record_task())
    asyncio.create_task(cleanup_old_recordings_task())
    logger.info("🚀 Background tasks démarrés", tasks=["monitor", "auto-record", "cleanup"])
