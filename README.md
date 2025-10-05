# P-StreamRec

**Complete application for automatic recording of Chaturbate and m3u8 streams**

All-in-one Docker container to watch and automatically record HLS/m3u8 streams, with a modern web interface.

## Main Features

- **Automatic recording** of Chaturbate streams by username
- **Modern web interface** to control recordings
- **Automatic detection** when a user goes online
- **Daily rotation** of files (1 TS file per day)
- **Direct m3u8 URL support** for any type of stream
- **Docker ready** with docker-compose for Portainer/Umbrel
- **Background auto-recording** (no need to keep page open)
- **Server-side storage** (works in private browsing)
- **Multilingual** (French/English)

## Data Structure

- **Recordings:** `/data/records/<person>/YYYY-MM-DD.ts`
- **HLS streaming:** `/data/sessions/<session_id>/`
- **Format:** MPEG-TS compatible with all players (VLC, MPV, etc.)
- **Models list:** `/data/models.json` (server-side storage)

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTPUT_DIR` | `/data` | Recordings folder (Docker volume) |
| `PORT` | `8080` | Web interface port |
| `FFMPEG_PATH` | `ffmpeg` | Path to ffmpeg |
| `HLS_TIME` | `4` | HLS segment duration (seconds) |
| `HLS_LIST_SIZE` | `6` | Number of segments in playlist |
| `CB_RESOLVER_ENABLED` | `true` | **Enable Chaturbate support** |
| `CB_COOKIE` | - | Chaturbate session cookie (optional) |
| `AUTO_RECORD_USERS` | - | Comma-separated list of users to auto-record |
| `TZ` | `UTC` | Timezone (e.g., `America/New_York`) |

## Quick Start

### Option 1: Docker Run
```bash
docker run -d \
  --name p-streamrec \
  -p 8080:8080 \
  -v ./data:/data \
  -e CB_RESOLVER_ENABLED=true \
  ghcr.io/raccommode/p-streamrec:latest
```

### Option 2: Docker Compose (Portainer)
```yaml
version: "3.8"
services:
  p-streamrec:
    image: ghcr.io/raccommode/p-streamrec:latest
    container_name: p-streamrec
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - CB_RESOLVER_ENABLED=true
      - TZ=America/New_York
    restart: unless-stopped
```

If error "failed to load the compose file":
1. Verify that `docker-compose.yml` is present in the repo
2. Check that "Compose path" = `docker-compose.yml`
3. Check that branch = `main`

## Usage

### Web Interface (http://localhost:8080)

1. **Add a model:**
   - Click the **+** button
   - Enter a Chaturbate username (e.g., `username`)
   - Or paste a direct m3u8 URL
   - Click **Add**

2. **Automatic recording:**
   - Once a model is added, the system checks every 2 minutes
   - When the model goes online, recording starts automatically
   - No need to keep the page open!

3. **Watch replays:**
   - Click on a model card
   - Go to the **Replays** tab
   - Click on a recording to watch
   - Progress is automatically saved

4. **Manage models:**
   - Click on a model card to view details
   - Click the delete button to remove from list
   - Models are saved server-side (works in private browsing)

### Features

#### Background Auto-Recording
- The server checks every 2 minutes if your models are online
- Automatically starts recording when they go online
- Works 24/7 even if you close your browser
- Logs available in Docker/Portainer

#### Quality Selector
- Automatically selects the highest quality available
- Manual quality selection if multiple streams available
- Options: Auto (best), 1080p, 720p, 480p, etc.

#### Smart Caching
- Replay metadata cached for fast loading
- 30x faster on subsequent loads
- Automatic cache invalidation when files change

## Local Development
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Accessing Recordings

Files are stored in `/data/records/<username>/YYYY-MM-DD.ts`

**To play TS files:**
- **VLC:** Open file directly
- **MPV:** `mpv /path/to/file.ts`
- **FFmpeg convert to MP4:** 
  ```bash
  ffmpeg -i input.ts -c copy output.mp4
  ```

## Important Notes

- **Privacy respect:** Use only for public content
- **Storage:** TS files can be large (~2-4 GB/hour)
- **Bandwidth:** Each stream uses approximately 1-3 Mbps
- **CPU:** Minimal usage (simple stream copy)

## Version

Current version: **v1.0.0**

See `version.json` for changelog and release information.

## Legal Notice

- Use this software in compliance with laws and service ToS
- Does not bypass any technical protection measures
- Ensure you have the right to record the content
- Respect privacy and copyright laws
