"""
Gestion de la base de données SQLite pour le cache des modèles
"""
import aiosqlite
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from ..logger import logger

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False
    
    async def initialize(self):
        """Initialise la base de données et crée les tables"""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            # Table pour les modèles et leur statut
            await db.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    username TEXT PRIMARY KEY,
                    display_name TEXT,
                    is_online BOOLEAN DEFAULT 0,
                    is_recording BOOLEAN DEFAULT 0,
                    viewers INTEGER DEFAULT 0,
                    thumbnail_path TEXT,
                    thumbnail_updated_at INTEGER,
                    last_check_at INTEGER,
                    auto_record BOOLEAN DEFAULT 1,
                    record_quality TEXT DEFAULT 'best',
                    retention_days INTEGER DEFAULT 30,
                    created_at INTEGER,
                    updated_at INTEGER
                )
            """)
            
            # Table pour les rediffusions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    recording_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    duration_seconds INTEGER,
                    thumbnail_path TEXT,
                    mp4_path TEXT,
                    mp4_size INTEGER,
                    is_converted BOOLEAN DEFAULT 0,
                    created_at INTEGER,
                    UNIQUE(username, filename)
                )
            """)
            
            # Index pour les requêtes fréquentes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_models_online 
                ON models(is_online, username)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_recordings_username 
                ON recordings(username, created_at DESC)
            """)
            
            await db.commit()
            
        self._initialized = True
        logger.info("Base de données initialisée", db_path=str(self.db_path))
    
    async def add_or_update_model(
        self, 
        username: str,
        display_name: Optional[str] = None,
        auto_record: bool = True,
        record_quality: str = "best",
        retention_days: int = 30
    ):
        """Ajoute ou met à jour un modèle"""
        await self.initialize()
        
        now = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO models (
                    username, display_name, auto_record, record_quality, 
                    retention_days, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    display_name = COALESCE(?, display_name),
                    auto_record = ?,
                    record_quality = ?,
                    retention_days = ?,
                    updated_at = ?
            """, (
                username, display_name, auto_record, record_quality,
                retention_days, now, now,
                display_name, auto_record, record_quality, retention_days, now
            ))
            await db.commit()
        
        logger.debug("Modèle ajouté/mis à jour", username=username)
    
    async def update_model_status(
        self,
        username: str,
        is_online: bool,
        viewers: int = 0,
        is_recording: bool = False,
        thumbnail_path: Optional[str] = None
    ):
        """Met à jour le statut d'un modèle"""
        await self.initialize()
        
        now = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            update_fields = {
                'is_online': is_online,
                'viewers': viewers,
                'is_recording': is_recording,
                'last_check_at': now,
                'updated_at': now
            }
            
            if thumbnail_path:
                update_fields['thumbnail_path'] = thumbnail_path
                update_fields['thumbnail_updated_at'] = now
            
            placeholders = ', '.join(f"{k} = ?" for k in update_fields.keys())
            values = list(update_fields.values()) + [username]
            
            await db.execute(
                f"UPDATE models SET {placeholders} WHERE username = ?",
                values
            )
            await db.commit()
    
    async def get_model(self, username: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un modèle"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM models WHERE username = ?",
                (username,)
            )
            row = await cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    async def get_all_models(self) -> List[Dict[str, Any]]:
        """Récupère tous les modèles"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM models ORDER BY username"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_models_for_auto_record(self) -> List[Dict[str, Any]]:
        """Récupère les modèles avec auto-record activé"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM models WHERE auto_record = 1 ORDER BY username"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def delete_model(self, username: str):
        """Supprime un modèle"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM models WHERE username = ?", (username,))
            await db.commit()
        
        logger.info("Modèle supprimé", username=username)
    
    async def add_or_update_recording(
        self,
        username: str,
        filename: str,
        file_path: str,
        file_size: int,
        recording_id: Optional[str] = None,
        duration_seconds: int = 0,
        thumbnail_path: Optional[str] = None,
        mp4_path: Optional[str] = None,
        mp4_size: Optional[int] = None,
        is_converted: bool = False
    ):
        """Ajoute ou met à jour un enregistrement"""
        await self.initialize()
        
        now = int(datetime.now().timestamp())
        
        # Générer recording_id si non fourni
        if not recording_id:
            from datetime import datetime
            recording_id = f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO recordings (
                    username, recording_id, filename, file_path, file_size, 
                    duration_seconds, thumbnail_path, mp4_path, mp4_size, is_converted, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username, filename) DO UPDATE SET
                    file_size = ?,
                    duration_seconds = ?,
                    thumbnail_path = COALESCE(?, thumbnail_path),
                    mp4_path = COALESCE(?, mp4_path),
                    mp4_size = COALESCE(?, mp4_size),
                    is_converted = ?
            """, (
                username, recording_id, filename, file_path, file_size,
                duration_seconds, thumbnail_path, mp4_path, mp4_size, is_converted, now,
                file_size, duration_seconds, thumbnail_path, mp4_path, mp4_size, is_converted
            ))
            await db.commit()
    
    async def get_recordings(self, username: str) -> List[Dict[str, Any]]:
        """Récupère les enregistrements d'un modèle"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM recordings 
                WHERE username = ? 
                ORDER BY created_at DESC
                """,
                (username,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_recordings_count(self, username: str) -> int:
        """Compte les enregistrements d'un modèle"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM recordings WHERE username = ?",
                (username,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def migrate_from_json(self, json_path: Path):
        """Migre les données depuis le fichier JSON vers SQLite"""
        if not json_path.exists():
            return
        
        await self.initialize()
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                models = data.get('models', []) if isinstance(data, dict) else data
            
            for model in models:
                username = model.get('username')
                if username:
                    await self.add_or_update_model(
                        username=username,
                        auto_record=model.get('autoRecord', True),
                        record_quality=model.get('recordQuality', 'best'),
                        retention_days=model.get('retentionDays', 30)
                    )
            
            logger.info("Migration JSON vers SQLite terminée", models_count=len(models))
        
        except Exception as e:
            logger.error("Erreur lors de la migration JSON", error=str(e), exc_info=True)
