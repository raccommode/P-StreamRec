"""
Tâche de conversion automatique des enregistrements TS -> MP4
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from ..logger import logger


async def convert_ts_to_mp4(
    ts_path: Path, 
    mp4_path: Optional[Path] = None,
    ffmpeg_path: str = "ffmpeg"
) -> tuple[bool, Optional[Path], Optional[int]]:
    """
    Convertit un fichier TS en MP4 avec compression optimisée
    
    Returns:
        (success, mp4_path, mp4_size)
    """
    if not ts_path.exists():
        logger.error("Fichier TS introuvable", ts_path=str(ts_path))
        return False, None, None
    
    # Générer le nom du fichier MP4 si non fourni
    if mp4_path is None:
        mp4_path = ts_path.with_suffix('.mp4')
    
    logger.info("🔄 Conversion TS->MP4 démarrée", 
               ts_file=ts_path.name, 
               mp4_file=mp4_path.name)
    
    # Commande FFmpeg optimisée pour compression
    # -c:v libx264 : codec H.264 (meilleure compression)
    # -crf 23 : qualité (18-28, 23 = bon équilibre qualité/taille)
    # -preset medium : vitesse de compression (fast, medium, slow)
    # -c:a aac : codec audio AAC
    # -b:a 128k : bitrate audio
    cmd = [
        ffmpeg_path,
        "-i", str(ts_path),
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",  # Optimisation streaming
        "-y",  # Overwrite
        str(mp4_path)
    ]
    
    try:
        # Lancer la conversion
        logger.debug("Commande FFmpeg", command=" ".join(cmd[:8]) + "...")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Conversion réussie
            mp4_size = mp4_path.stat().st_size
            ts_size = ts_path.stat().st_size
            reduction = ((ts_size - mp4_size) / ts_size) * 100
            
            logger.success("✅ Conversion réussie",
                         ts_file=ts_path.name,
                         mp4_file=mp4_path.name,
                         ts_size_mb=f"{ts_size / 1024 / 1024:.1f}",
                         mp4_size_mb=f"{mp4_size / 1024 / 1024:.1f}",
                         reduction_percent=f"{reduction:.1f}%")
            
            return True, mp4_path, mp4_size
        else:
            # Erreur de conversion
            error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
            logger.error("❌ Erreur conversion",
                        ts_file=ts_path.name,
                        error=error_msg[:500])  # Limiter la longueur
            return False, None, None
            
    except Exception as e:
        logger.error("❌ Exception conversion",
                    ts_file=ts_path.name,
                    error=str(e),
                    exc_info=True)
        return False, None, None


async def auto_convert_recordings_task(db, output_dir: Path, ffmpeg_path: str = "ffmpeg"):
    """
    Tâche qui surveille les enregistrements non convertis et les convertit automatiquement
    """
    logger.info("🔄 Tâche de conversion automatique démarrée")
    
    # SCAN INITIAL : Scanner tous les fichiers TS existants au démarrage
    logger.info("📂 Scan initial des fichiers TS existants...")
    try:
        records_root = output_dir / "records"
        if records_root.exists():
            for user_dir in records_root.iterdir():
                if user_dir.is_dir():
                    username = user_dir.name
                    for ts_file in user_dir.glob("*.ts"):
                        # Vérifier si déjà dans la DB
                        recordings = await db.get_recordings(username)
                        existing = next((r for r in recordings if r['filename'] == ts_file.name), None)
                        
                        if not existing:
                            # Ajouter à la DB
                            logger.info("📥 Indexation fichier existant", username=username, file=ts_file.name)
                            import time
                            recording_id = f"{username}_{ts_file.stem}"
                            await db.add_or_update_recording(
                                username=username,
                                filename=ts_file.name,
                                file_path=str(ts_file),
                                file_size=ts_file.stat().st_size,
                                recording_id=recording_id,
                                duration_seconds=0,
                                is_converted=False
                            )
        logger.success("✅ Scan initial terminé")
    except Exception as e:
        logger.error("Erreur scan initial", error=str(e), exc_info=True)
    
    while True:
        try:
            await asyncio.sleep(30)  # Vérifier toutes les 30 secondes
            
            # Scanner TOUS les dossiers users dans /records (pas seulement les modèles connus)
            records_root = output_dir / "records"
            if not records_root.exists():
                continue
                
            for user_dir in records_root.iterdir():
                if not user_dir.is_dir():
                    continue
                    
                username = user_dir.name
                
                # Récupérer les enregistrements non convertis depuis la DB
                recordings = await db.get_recordings(username)
                
                for rec in recordings:
                    # Vérifier si déjà converti
                    if rec.get('is_converted'):
                        continue
                    
                    # Vérifier si l'enregistrement est en cours
                    ts_path = Path(rec['file_path'])
                    
                    # Vérifier si le fichier TS existe
                    if not ts_path.exists():
                        logger.warning("Fichier TS introuvable, skip", file=str(ts_path))
                        continue
                    
                    # Vérifier si le MP4 existe déjà (éviter reconversion)
                    mp4_path = ts_path.with_suffix('.mp4')
                    if mp4_path.exists():
                        # Le MP4 existe, mettre à jour la DB
                        logger.info("MP4 déjà existant, mise à jour DB", file=mp4_path.name)
                        await db.add_or_update_recording(
                            username=username,
                            filename=rec['filename'],
                            file_path=rec['file_path'],
                            file_size=rec['file_size'],
                            recording_id=rec.get('recording_id'),
                            duration_seconds=rec.get('duration_seconds', 0),
                            thumbnail_path=rec.get('thumbnail_path'),
                            mp4_path=str(mp4_path),
                            mp4_size=mp4_path.stat().st_size,
                            is_converted=True
                        )
                        continue
                    
                    # Vérifier si le fichier TS est stable (pas modifié depuis 60s)
                    import time
                    last_modified = ts_path.stat().st_mtime
                    if time.time() - last_modified < 60:
                        # Fichier encore en cours d'écriture
                        logger.debug("Fichier en cours d'écriture, skip", file=ts_path.name)
                        continue
                    
                    # Lancer la conversion
                    logger.info("🎬 Conversion automatique",
                              username=username,
                              filename=rec['filename'])
                    success, mp4_path_result, mp4_size = await convert_ts_to_mp4(
                        ts_path,
                        mp4_path,
                        ffmpeg_path
                    )
                    
                    if success and mp4_path_result:
                        # Mettre à jour la DB
                        await db.add_or_update_recording(
                            username=username,
                            filename=rec['filename'],
                            file_path=rec['file_path'],
                            file_size=rec['file_size'],
                            recording_id=rec.get('recording_id'),
                            duration_seconds=rec.get('duration_seconds', 0),
                            thumbnail_path=rec.get('thumbnail_path'),
                            mp4_path=str(mp4_path_result),
                            mp4_size=mp4_size,
                            is_converted=True
                        )
                        
                        logger.success("📦 Enregistrement converti et indexé",
                                     username=username,
                                     filename=rec['filename'],
                                     mp4_file=mp4_path_result.name)
                    
                    # Attendre un peu entre chaque conversion pour éviter surcharge
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error("Erreur dans tâche de conversion",
                        error=str(e),
                        exc_info=True)
            await asyncio.sleep(60)
