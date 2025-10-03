# P-StreamRec

Conteneur tout‑en‑un pour lire un flux HLS et l’enregistrer au format TS, via une interface web.

- Interface: FastAPI + HTML/JS (hls.js)
- Lecture: HLS local généré par ffmpeg (stream.m3u8 + segments)
- Enregistrement: 1 fichier TS par personne et par jour
  - Chemin: `OUTPUT_DIR/records/<person>/YYYY-MM-DD.ts`
  - HLS par session: `OUTPUT_DIR/sessions/<session_id>/`

## Variables d’environnement
- `OUTPUT_DIR` (défaut: `/data`) — Dossier des sorties (monté en volume)
- `PORT` (défaut: `8080`) — Port HTTP du service
- `FFMPEG_PATH` (défaut: `ffmpeg`)
- `HLS_TIME` (défaut: `4`) — Durée de segment HLS (s)
- `HLS_LIST_SIZE` (défaut: `6`) — Taille de la playlist HLS
- `CB_RESOLVER_ENABLED` (défaut: `false`) — Activer la résolution Chaturbate depuis un pseudo
- `CB_COOKIE` — Cookie de session si requis par la résolution Chaturbate
- `TZ` (optionnel) — Fuseau horaire à l’intérieur du conteneur

## Démarrage rapide (Docker run)
```bash
# Construire l'image localement (ou utiliser docker-compose/Portainer)
docker build -t p-streamrec:latest .

mkdir -p ./data

docker run --name p-streamrec \
  -p 8080:8080 \
  -v "$(pwd)/data:/data" \
  -e OUTPUT_DIR=/data \
  -e PORT=8080 \
  -e CB_RESOLVER_ENABLED=false \
  p-streamrec:latest
```
Puis, ouvrez http://localhost:8080, saisissez une URL m3u8 ou un pseudo (si Chaturbate activé), cliquez « Démarrer ».

## docker-compose
Un fichier `docker-compose.yml` est fourni à la racine.

```bash
# Lancer avec compose (standalone)
# Variables optionnelles: HOST_PORT, PORT, HOST_DATA_DIR, HLS_TIME, HLS_LIST_SIZE, CB_RESOLVER_ENABLED, TZ
HOST_PORT=8080 PORT=8080 HOST_DATA_DIR=./data \
  docker compose up -d --build
```
Compose expose le service sur `http://localhost:${HOST_PORT}` et monte `${HOST_DATA_DIR}` sur `/data` dans le conteneur.

## Portainer (Stack -> Repository)
1) Dans Portainer, allez dans « Stacks » > « Add stack » > « Repository »
2) Renseignez:
   - Repository URL: `https://github.com/raccommode/P-StreamRec`
   - Compose path: `docker-compose.yml` (chemin par défaut)
   - Reference/Branch: `main` (ou la branche cible)
3) Variables (optionnel):
   - `HOST_PORT` (ex: 8080), `PORT` (ex: 8080)
   - `HOST_DATA_DIR` (ex: `./data` ou `/srv/p-streamrec/data`)
   - `CB_RESOLVER_ENABLED` (`false` ou `true`), `TZ` (ex: `Europe/Paris`)
4) Déployez la stack.

Si Portainer affiche « failed to load the compose file … docker-compose.yml: no such file or directory », assurez‑vous que:
- `docker-compose.yml` est bien présent à la racine du repo (commité et poussé),
- « Compose path » est `docker-compose.yml`,
- La branche choisie contient ce fichier.

## Utilisation de l’UI
- Champ « URL m3u8 ou nom d’utilisateur »: l’URL HLS directe ou le pseudo (si résolveur actif)
- « Personne » (optionnel): le nom de bucket d’enregistrement. Si vide, il est déduit (pseudo ou extrait de l’URL)
- « Démarrer »: crée une session HLS locale et enregistre vers `records/<person>/YYYY-MM-DD.ts`
- « Stop »: arrête la session

## Développement local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Notes légales
- Utilisez ce logiciel dans le respect des lois et des CGU des services concernés.
- Ce projet ne contourne aucune protection.
- Assurez‑vous d’avoir le droit de lire et d’enregistrer le contenu cible.
