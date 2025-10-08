"""
Background task: Nettoyage automatique
Supprime les anciennes rediffusions selon la rétention configurée
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from ..logger import logger
from ..core.config import CLEANUP_INTERVAL, OUTPUT_DIR

# Fichier de sauvegarde des modèles
MODELS_FILE = OUTPUT_DIR / "models.json"


def load_models() -> list:
    """Charge la liste des modèles depuis le fichier JSON"""
    if MODELS_FILE.exists():
        try:
            with open(MODELS_FILE, 'r') as f:
                data = json.load(f)
                return data.get('models', []) if isinstance(data, dict) else data
        except Exception as e:
            logger.error("Erreur chargement models.json", exc_info=True, error=str(e))
    return []


async def cleanup_old_recordings_task():
    """
    Tâche de nettoyage automatique en arrière-plan
    Supprime les rediffusions selon la rétention configurée par modèle
    """
    logger.background_task("cleanup", "Démarrage")
    
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            
            logger.background_task("cleanup", "Début du nettoyage")
            
            # Charger les modèles avec leurs paramètres de rétention
            models = load_models()
            
            total_deleted = 0
            total_freed = 0  # bytes
            
            for model in models:
                username = model.get('username')
                retention_days = model.get('retentionDays', 30)  # Défaut 30 jours
                
                if not username:
                    continue
                
                records_dir = OUTPUT_DIR / "records" / username
                thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
                
                if not records_dir.exists():
                    continue
                
                logger.debug("Nettoyage modèle",
                           task="cleanup",
                           username=username,
                           retention_days=retention_days)
                
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
                            # Taille du fichier avant suppression
                            file_size = ts_file.stat().st_size
                            
                            # Supprimer le fichier TS
                            ts_file.unlink()
                            total_deleted += 1
                            total_freed += file_size
                            
                            logger.info("Fichier supprimé (rétention)",
                                      task="cleanup",
                                      username=username,
                                      filename=ts_file.name,
                                      file_date=date_str,
                                      retention_days=retention_days,
                                      size_mb=f"{file_size / 1024 / 1024:.1f}")
                            
                            # Supprimer la miniature associée
                            thumb_file = thumbnails_dir / f"{ts_file.stem}.jpg"
                            if thumb_file.exists():
                                thumb_file.unlink()
                                logger.debug("Miniature supprimée",
                                           task="cleanup",
                                           filename=thumb_file.name)
                            
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
                                        logger.debug("Cache nettoyé",
                                                   task="cleanup",
                                                   filename=ts_file.name)
                                except Exception as e:
                                    logger.warning("Erreur nettoyage cache",
                                                 task="cleanup",
                                                 error=str(e))
                                    
                    except ValueError:
                        # Nom de fichier invalide, ignorer
                        logger.warning("Nom de fichier invalide ignoré",
                                     task="cleanup",
                                     filename=ts_file.name)
                        continue
                    except Exception as e:
                        logger.error("Erreur suppression fichier",
                                   task="cleanup",
                                   filename=ts_file.name,
                                   error=str(e))
                        continue
            
            if total_deleted > 0:
                logger.success("Nettoyage terminé",
                             task="cleanup",
                             files_deleted=total_deleted,
                             space_freed_mb=f"{total_freed / 1024 / 1024:.1f}")
            else:
                logger.debug("Aucun fichier à supprimer",
                           task="cleanup")
                        
        except Exception as e:
            logger.error("Erreur dans cleanup task",
                        task="cleanup",
                        exc_info=True,
                        error=str(e))
            await asyncio.sleep(3600)
