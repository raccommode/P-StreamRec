#!/usr/bin/env python3
"""
Script utilitaire pour recalculer les durées de tous les enregistrements existants
"""
import asyncio
import sys
from pathlib import Path

# Ajouter le chemin parent pour importer les modules de l'app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import Database
from app.core.config import OUTPUT_DIR, FFMPEG_PATH
from app.tasks.monitor import get_video_duration, generate_recording_thumbnail
from app.logger import logger


async def recalculate_all_durations():
    """Recalcule les durées de tous les enregistrements"""
    db_file = OUTPUT_DIR / "streamrec.db"
    db = Database(db_file)
    
    await db.initialize()
    
    logger.info("🔄 Début du recalcul des durées")
    
    # Récupérer tous les modèles
    models = await db.get_all_models()
    
    total_processed = 0
    total_updated = 0
    
    for model in models:
        username = model['username']
        records_dir = OUTPUT_DIR / "records" / username
        
        if not records_dir.exists():
            continue
        
        logger.info(f"📁 Traitement de {username}...")
        
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
                
                # Calculer la durée si elle est à 0 ou absente
                if current_duration == 0:
                    logger.info(f"  ⏱️  Calcul durée: {ts_file.name}...")
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
                        
                        # Formater la durée
                        hours = duration // 3600
                        minutes = (duration % 3600) // 60
                        seconds = duration % 60
                        if hours > 0:
                            duration_str = f"{hours}h{minutes:02d}m{seconds:02d}s"
                        else:
                            duration_str = f"{minutes}m{seconds:02d}s"
                        
                        logger.success(f"    ✅ {ts_file.name}: {duration_str}")
                    else:
                        logger.warning(f"    ⚠️  Impossible de calculer la durée pour {ts_file.name}")
                else:
                    logger.debug(f"  ⏭️  {ts_file.name} déjà traité ({current_duration}s)")
                    
            except Exception as e:
                logger.error(f"  ❌ Erreur: {ts_file.name}", error=str(e), exc_info=True)
                continue
    
    logger.success(f"✅ Terminé ! {total_updated} enregistrements mis à jour sur {total_processed} traités")


if __name__ == "__main__":
    asyncio.run(recalculate_all_durations())
