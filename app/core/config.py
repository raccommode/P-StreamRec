"""
Configuration centralisée de l'application P-StreamRec
"""

import os
from pathlib import Path
from typing import Optional

# Chemins de base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "data")))

# Configuration FFmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
HLS_TIME = int(os.getenv("HLS_TIME", "4"))
HLS_LIST_SIZE = int(os.getenv("HLS_LIST_SIZE", "6"))

# Configuration Chaturbate
CB_RESOLVER_ENABLED = os.getenv("CB_RESOLVER_ENABLED", "false").lower() in {"1", "true", "yes"}
CB_COOKIE: Optional[str] = os.getenv("CB_COOKIE")

# Configuration serveur
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

# Configuration auto-record
AUTO_RECORD_INTERVAL = int(os.getenv("AUTO_RECORD_INTERVAL", "120"))  # secondes
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "3600"))  # secondes

# Timezone
TZ = os.getenv("TZ", "UTC")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Créer les répertoires nécessaires
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "sessions").mkdir(exist_ok=True)
(OUTPUT_DIR / "records").mkdir(exist_ok=True)
(OUTPUT_DIR / "thumbnails").mkdir(exist_ok=True)

# Fichiers de données
MODELS_FILE = OUTPUT_DIR / "models.json"

# Configuration CORS
CORS_ORIGINS = ["*"]
CORS_CREDENTIALS = False
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]
