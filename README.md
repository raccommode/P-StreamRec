# P-StreamRec

**Application complète pour l'enregistrement automatique de streams Chaturbate et m3u8**

Conteneur Docker tout-en-un pour regarder et enregistrer automatiquement des flux HLS/m3u8, avec une interface web moderne.

## Fonctionnalités principales

- **Enregistrement automatique** des streams Chaturbate par nom d'utilisateur
- **Interface web moderne** pour contrôler les enregistrements
- **Détection automatique** quand un utilisateur est en ligne
- **Rotation journalière** des fichiers (1 fichier TS par jour)
- **Support des URLs m3u8 directes** pour tout type de stream
- **Docker ready** avec docker-compose pour Portainer/Umbrel

## Structure des données

- **Enregistrements:** `/data/records/<person>/YYYY-MM-DD.ts`
- **HLS streaming:** `/data/sessions/<session_id>/`
- **Format:** MPEG-TS compatible avec tous les lecteurs (VLC, MPV, etc.)

## Configuration (Variables d'environnement)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `OUTPUT_DIR` | `/data` | Dossier des enregistrements (volume Docker) |
| `PORT` | `8080` | Port de l'interface web |
| `FFMPEG_PATH` | `ffmpeg` | Chemin vers ffmpeg |
| `HLS_TIME` | `4` | Durée des segments HLS (secondes) |
| `HLS_LIST_SIZE` | `6` | Nombre de segments dans la playlist |
| `CB_RESOLVER_ENABLED` | `true` | **Activer le support Chaturbate** |
| `CB_COOKIE` | - | Cookie de session Chaturbate (optionnel) |
| `AUTO_RECORD_USERS` | - | Liste d'utilisateurs à enregistrer automatiquement (séparés par virgule) |
| `TZ` | `UTC` | Fuseau horaire (ex: `Europe/Paris`) |

## Démarrage rapide

### Option 1: Docker Run
```bash
{{ ... }}
Si erreur "failed to load the compose file":
1. Vérifiez que `docker-compose.yml` est présent dans le repo
2. Vérifiez que "Compose path" = `docker-compose.yml`
3. Vérifiez que la branche = `main`

## Utilisation

### Interface Web (http://localhost:8080)

1. **Démarrer un enregistrement:**
   - Entrez un nom d'utilisateur Chaturbate (ex: `username`)
   - Ou collez une URL m3u8 directe
   - Cliquez sur **Démarrer l'enregistrement**

2. **Regarder en direct:**
   - L'enregistrement actif apparait dans la liste
   - Cliquez sur **Regarder** pour voir le stream en direct
   - Le lecteur vidéo intégré supporte HLS nativement

3. **Gérer les sessions:**
   - **URL** : Copier le lien du stream
   - **Stop** : Arrêter un enregistrement
   - **Arrêter tout** : Stopper tous les enregistrements

### Enregistrement automatique

#### Méthode 1: Variable d'environnement
```yaml
AUTO_RECORD_USERS=user1,user2,user3
```

#### Méthode 2: Fichier de configuration
Créez `/data/auto_record_users.txt` avec un nom d'utilisateur par ligne:
```
user1
user2
user3
```

Le système vérifie automatiquement toutes les 30 secondes si les utilisateurs sont en ligne et démarre l'enregistrement.

## Développement local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Récupération des enregistrements

Les fichiers sont stockés dans `/data/records/<username>/YYYY-MM-DD.ts`

**Pour lire les fichiers TS:**
- **VLC:** Ouvrir directement le fichier
- **MPV:** `mpv /path/to/file.ts`
- **FFmpeg conversion en MP4:** 
  ```bash
  ffmpeg -i input.ts -c copy output.mp4
  ```

## Notes importantes

- **Respect de la vie privée:** Utilisez uniquement pour du contenu public
- **Stockage:** Les fichiers TS peuvent être volumineux (~2-4 GB/heure)
- **Bande passante:** Chaque stream consomme environ 1-3 Mbps
- **CPU:** Utilisation minimale (simple copie de flux)

## Notes légales

- Utilisez ce logiciel dans le respect des lois et des CGU des services
- Ne contourne aucune protection technique
- Assurez-vous d'avoir le droit d'enregistrer le contenu
- Respectez la vie privée et les droits d'auteur
