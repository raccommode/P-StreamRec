"""
Tâche background: Monitoring continu des modèles
Vérifie l'état en ligne, génère les miniatures et met à jour SQLite
"""
import asyncio
import aiohttp
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ..ffmpeg_runner import FFmpegManager
    from ..core.database import Database

from ..logger import logger
from ..core.config import OUTPUT_DIR

# Intervalle de vérification (en secondes)
MONITOR_INTERVAL = 30  # Vérifie toutes les 30 secondes
THUMBNAIL_UPDATE_INTERVAL = 60  # Miniature mise à jour toutes les 60 secondes

async def check_model_status(session: aiohttp.ClientSession, username: str) -> dict:
    """Vérifie le statut d'un modèle via l'API Chaturbate"""
    try:
        url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://chaturbate.com/",
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                
                is_online = bool(data.get("hls_source")) or data.get("room_status") == "public"
                viewers = data.get("num_users", 0)
                hls_source = data.get("hls_source")
                
                return {
                    "is_online": is_online,
                    "viewers": viewers,
                    "hls_source": hls_source
                }
    except Exception as e:
        logger.debug("Erreur vérification statut modèle", username=username, error=str(e))
    
    return {
        "is_online": False,
        "viewers": 0,
        "hls_source": None
    }

async def generate_thumbnail_from_stream(
    username: str,
    session_id: str,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg"
) -> str | None:
    """Génère une miniature depuis le stream HLS en cours"""
    try:
        session_dir = output_dir / "sessions" / session_id
        m3u8_file = session_dir / "stream.m3u8"
        
        if not m3u8_file.exists():
            return None
        
        # Dossier pour les miniatures live
        live_thumbs_dir = output_dir / "thumbnails" / "live"
        live_thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = live_thumbs_dir / f"{username}.jpg"
        
        # Générer la miniature
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-i", str(m3u8_file),
            "-vframes", "1",
            "-vf", "scale=280:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(process.wait(), timeout=10)
        
        if thumb_path.exists():
            return str(thumb_path)
    
    except Exception as e:
        logger.debug("Erreur génération miniature stream", username=username, error=str(e))
    
    return None

async def generate_thumbnail_from_recording(
    username: str,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg"
) -> str | None:
    """Génère une miniature depuis la dernière rediffusion"""
    try:
        records_dir = output_dir / "records" / username
        
        if not records_dir.exists():
            return None
        
        # Trouver la dernière rediffusion
        ts_files = sorted(records_dir.glob("*.ts"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not ts_files:
            return None
        
        latest_recording = ts_files[0]
        
        # Dossier pour les miniatures offline
        offline_thumbs_dir = output_dir / "thumbnails" / "offline"
        offline_thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = offline_thumbs_dir / f"{username}.jpg"
        
        # Ne régénérer que si la miniature n'existe pas ou est plus ancienne que l'enregistrement
        if thumb_path.exists() and thumb_path.stat().st_mtime > latest_recording.stat().st_mtime:
            return str(thumb_path)
        
        # Extraire une frame au milieu de la vidéo
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-ss", "00:00:30",
            "-i", str(latest_recording),
            "-vframes", "1",
            "-vf", "scale=280:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(process.wait(), timeout=15)
        
        if thumb_path.exists():
            return str(thumb_path)
    
    except Exception as e:
        logger.debug("Erreur génération miniature offline", username=username, error=str(e))
    
    return None

async def download_thumbnail_from_chaturbate(
    session: aiohttp.ClientSession,
    username: str,
    output_dir: Path
) -> str | None:
    """Télécharge la miniature depuis Chaturbate"""
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
                async with session.get(img_url, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        if len(content) > 1000:
                            # Sauvegarder la miniature
                            cb_thumbs_dir = output_dir / "thumbnails" / "chaturbate"
                            cb_thumbs_dir.mkdir(parents=True, exist_ok=True)
                            thumb_path = cb_thumbs_dir / f"{username}.jpg"
                            
                            with open(thumb_path, 'wb') as f:
                                f.write(content)
                            
                            return str(thumb_path)
            except:
                continue
    
    except Exception as e:
        logger.debug("Erreur téléchargement miniature Chaturbate", username=username, error=str(e))
    
    return None

async def update_recordings_cache(db: 'Database', username: str, output_dir: Path):
    """Met à jour le cache des enregistrements dans SQLite"""
    try:
        records_dir = output_dir / "records" / username
        
        if not records_dir.exists():
            return
        
        for ts_file in records_dir.glob("*.ts"):
            stat = ts_file.stat()
            
            await db.add_or_update_recording(
                username=username,
                filename=ts_file.name,
                file_path=str(ts_file),
                file_size=stat.st_size,
                duration_seconds=0  # Peut être calculé plus tard si nécessaire
            )
    
    except Exception as e:
        logger.debug("Erreur mise à jour cache enregistrements", username=username, error=str(e))

async def monitor_models_task(
    db: 'Database',
    manager: 'FFmpegManager',
    ffmpeg_path: str = "ffmpeg"
):
    """
    Tâche de monitoring en arrière-plan
    Vérifie continuellement l'état des modèles et génère les miniatures
    """
    logger.background_task("monitor", "Démarrage du monitoring continu")
    
    # Initialiser la base de données
    await db.initialize()
    
    # Créer une session HTTP persistante
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Récupérer tous les modèles depuis la DB
                models = await db.get_all_models()
                
                if not models:
                    await asyncio.sleep(MONITOR_INTERVAL)
                    continue
                
                logger.debug("Vérification des modèles", count=len(models))
                
                # Récupérer les sessions actives
                active_sessions = manager.list_status()
                
                # Vérifier chaque modèle
                for model in models:
                    username = model['username']
                    
                    try:
                        # Vérifier le statut en ligne
                        status = await check_model_status(session, username)
                        
                        # Vérifier si en cours d'enregistrement
                        active_session = next(
                            (s for s in active_sessions if s.get('person') == username and s.get('running')),
                            None
                        )
                        is_recording = active_session is not None
                        
                        # Générer/mettre à jour la miniature
                        thumbnail_path = None
                        last_thumbnail_update = model.get('thumbnail_updated_at', 0)
                        needs_thumbnail_update = (
                            datetime.now().timestamp() - last_thumbnail_update > THUMBNAIL_UPDATE_INTERVAL
                        )
                        
                        if needs_thumbnail_update:
                            if is_recording and active_session:
                                # Miniature depuis le stream en cours
                                thumbnail_path = await generate_thumbnail_from_stream(
                                    username,
                                    active_session['id'],
                                    OUTPUT_DIR,
                                    ffmpeg_path
                                )
                            
                            if not thumbnail_path and status['is_online']:
                                # Miniature depuis Chaturbate
                                thumbnail_path = await download_thumbnail_from_chaturbate(
                                    session,
                                    username,
                                    OUTPUT_DIR
                                )
                            
                            if not thumbnail_path:
                                # Miniature depuis la dernière rediffusion
                                thumbnail_path = await generate_thumbnail_from_recording(
                                    username,
                                    OUTPUT_DIR,
                                    ffmpeg_path
                                )
                        
                        # Mettre à jour le statut dans la DB
                        await db.update_model_status(
                            username=username,
                            is_online=status['is_online'],
                            viewers=status['viewers'],
                            is_recording=is_recording,
                            thumbnail_path=thumbnail_path
                        )
                        
                        # Mettre à jour le cache des enregistrements
                        await update_recordings_cache(db, username, OUTPUT_DIR)
                        
                        logger.debug("Modèle mis à jour",
                                   username=username,
                                   is_online=status['is_online'],
                                   is_recording=is_recording,
                                   viewers=status['viewers'])
                    
                    except Exception as e:
                        logger.error("Erreur monitoring modèle",
                                   username=username,
                                   error=str(e),
                                   exc_info=True)
                        continue
                
                # Attendre avant la prochaine vérification
                await asyncio.sleep(MONITOR_INTERVAL)
            
            except Exception as e:
                logger.error("Erreur dans monitor task",
                           error=str(e),
                           exc_info=True)
                await asyncio.sleep(60)
