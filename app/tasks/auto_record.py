"""
Background task: Auto-enregistrement
Vérifie automatiquement les modèles et lance les enregistrements
"""

import asyncio
import requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ffmpeg_runner import FFmpegManager

from ..logger import logger
from ..core.config import AUTO_RECORD_INTERVAL, OUTPUT_DIR

# Fichier de sauvegarde des modèles
MODELS_FILE = OUTPUT_DIR / "models.json"


def load_models() -> list:
    """Charge la liste des modèles depuis le fichier JSON"""
    import json
    if MODELS_FILE.exists():
        try:
            with open(MODELS_FILE, 'r') as f:
                data = json.load(f)
                return data.get('models', []) if isinstance(data, dict) else data
        except Exception as e:
            logger.error("Erreur chargement models.json", exc_info=True, error=str(e))
    return []


async def auto_record_task(manager: 'FFmpegManager'):
    """
    Tâche d'auto-enregistrement en arrière-plan
    Vérifie les modèles toutes les 2 minutes et lance les enregistrements
    """
    logger.background_task("auto-record", "Démarrage")
    
    while True:
        try:
            await asyncio.sleep(AUTO_RECORD_INTERVAL)
            
            # Charger les modèles
            models = load_models()
            if not models:
                logger.debug("Aucun modèle à surveiller", task="auto-record")
                continue
            
            logger.background_task("auto-record", f"Vérification de {len(models)} modèles")
            
            # Récupérer les sessions actives
            active_sessions = manager.list_status()
            
            for model in models:
                username = model.get('username')
                auto_record = model.get('autoRecord', True)  # Par défaut activé
                
                if not username:
                    continue
                
                # Vérifier si l'auto-record est activé pour ce modèle
                if not auto_record:
                    logger.debug("Auto-record désactivé", 
                               task="auto-record",
                               username=username)
                    continue
                
                # Vérifier si déjà en enregistrement
                is_recording = any(
                    s.get('person') == username and s.get('running')
                    for s in active_sessions
                )
                
                if is_recording:
                    logger.debug("Déjà en enregistrement", 
                               task="auto-record",
                               username=username)
                    continue
                
                # Vérifier si le modèle est en ligne
                try:
                    logger.debug("Vérification statut en ligne", 
                               task="auto-record",
                               username=username)
                    
                    # Utiliser l'API Chaturbate
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
                            # Modèle en ligne avec flux HLS disponible
                            logger.info("Modèle en ligne détecté", 
                                      task="auto-record",
                                      username=username)
                            
                            try:
                                # Lancer l'enregistrement
                                session_id = manager.start_session(
                                    input_url=hls_source,
                                    person=username,
                                    display_name=username
                                )
                                
                                if session_id:
                                    logger.success("Auto-enregistrement démarré", 
                                                 task="auto-record",
                                                 username=username,
                                                 session_id=session_id.id)
                            except Exception as e:
                                logger.error("Erreur démarrage auto-enregistrement",
                                           task="auto-record",
                                           username=username,
                                           exc_info=True,
                                           error=str(e))
                        else:
                            logger.debug("Modèle hors ligne", 
                                       task="auto-record",
                                       username=username)
                            
                except Exception as e:
                    logger.error("Erreur vérification modèle",
                               task="auto-record",
                               username=username,
                               error=str(e))
                    continue
                
        except Exception as e:
            logger.error("Erreur dans auto-record task", 
                        task="auto-record",
                        exc_info=True,
                        error=str(e))
            await asyncio.sleep(60)
