import asyncio
import os
import logging
from typing import Set, Dict
from datetime import datetime
import aiohttp
import json

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutoRecorder:
    """
    Enregistreur automatique qui surveille une liste d'utilisateurs
    et démarre automatiquement l'enregistrement quand ils sont en ligne.
    """
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.active_sessions: Dict[str, str] = {}  # username -> session_id
        self.monitored_users: Set[str] = set()
        
    def load_users_from_file(self, filepath: str = "/data/auto_record_users.txt"):
        """Charge la liste des utilisateurs à surveiller depuis un fichier."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    users = [line.strip().lower() for line in f if line.strip()]
                    self.monitored_users = set(users)
                    logger.info(f"Chargé {len(self.monitored_users)} utilisateurs à surveiller")
            else:
                logger.warning(f"Fichier {filepath} non trouvé. Créez-le avec un nom d'utilisateur par ligne.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des utilisateurs: {e}")
    
    def load_users_from_env(self):
        """Charge la liste des utilisateurs depuis une variable d'environnement."""
        users_str = os.getenv("AUTO_RECORD_USERS", "")
        if users_str:
            users = [u.strip().lower() for u in users_str.split(",") if u.strip()]
            self.monitored_users.update(users)
            logger.info(f"Chargé {len(users)} utilisateurs depuis AUTO_RECORD_USERS")
    
    async def check_user_status(self, session: aiohttp.ClientSession, username: str) -> bool:
        """Vérifie si un utilisateur est en ligne."""
        try:
            # Utiliser l'API de status si disponible
            url = f"https://roomlister.stream/api/rooms/{username}"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("online", False)
        except Exception:
            pass
        return False
    
    async def start_recording(self, session: aiohttp.ClientSession, username: str) -> bool:
        """Démarre l'enregistrement pour un utilisateur."""
        try:
            url = f"{self.base_url}/api/start"
            data = {
                "target": username,
                "source_type": "chaturbate",
                "person": username,
                "name": f"{username} (auto)"
            }
            
            async with session.post(url, json=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    session_id = result.get("id")
                    if session_id:
                        self.active_sessions[username] = session_id
                        logger.info(f"✅ Enregistrement démarré pour {username} (session: {session_id})")
                        return True
                else:
                    error = await resp.text()
                    logger.error(f"❌ Impossible de démarrer {username}: {error}")
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage de {username}: {e}")
        return False
    
    async def check_active_sessions(self, session: aiohttp.ClientSession):
        """Vérifie l'état des sessions actives."""
        try:
            url = f"{self.base_url}/api/status"
            async with session.get(url) as resp:
                if resp.status == 200:
                    sessions = await resp.json()
                    
                    # Mettre à jour notre liste
                    current_active = {}
                    for s in sessions:
                        if s.get("running"):
                            person = s.get("person", "").lower()
                            if person in self.monitored_users:
                                current_active[person] = s.get("id")
                    
                    self.active_sessions = current_active
                    logger.debug(f"Sessions actives: {list(self.active_sessions.keys())}")
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des sessions: {e}")
    
    async def monitor_loop(self):
        """Boucle principale de surveillance."""
        logger.info("🚀 Démarrage du monitoring automatique")
        
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # Recharger la liste des utilisateurs
                    self.load_users_from_file()
                    self.load_users_from_env()
                    
                    if not self.monitored_users:
                        logger.warning("Aucun utilisateur à surveiller")
                        await asyncio.sleep(60)
                        continue
                    
                    # Vérifier les sessions actives
                    await self.check_active_sessions(session)
                    
                    # Vérifier chaque utilisateur
                    for username in self.monitored_users:
                        if username not in self.active_sessions:
                            # Pas de session active, vérifier si en ligne
                            is_online = await self.check_user_status(session, username)
                            if is_online:
                                logger.info(f"🟢 {username} est en ligne, démarrage de l'enregistrement...")
                                await self.start_recording(session, username)
                            else:
                                logger.debug(f"⚫ {username} est hors ligne")
                        else:
                            logger.debug(f"🔴 {username} est déjà en cours d'enregistrement")
                    
                    # Attendre avant la prochaine vérification
                    await asyncio.sleep(30)  # Vérifier toutes les 30 secondes
                    
                except Exception as e:
                    logger.error(f"Erreur dans la boucle de monitoring: {e}")
                    await asyncio.sleep(60)

async def main():
    recorder = AutoRecorder()
    
    # Charger la configuration initiale
    recorder.load_users_from_file()
    recorder.load_users_from_env()
    
    # Démarrer le monitoring
    await recorder.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
