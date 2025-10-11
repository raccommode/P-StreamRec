import os
import uuid
import threading
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional
from .logger import logger


class FFmpegSession:
    def __init__(self, session_id: str, input_url: str, sessions_dir: str, records_dir_for_person: str, person: str, display_name: Optional[str] = None):
        self.id = session_id
        self.input_url = input_url
        self.sessions_dir = sessions_dir
        self.records_dir_for_person = records_dir_for_person
        self.person = person
        self.name = display_name or person or session_id
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.start_time = time.time()
        self.start_date = datetime.now().strftime("%Y-%m-%d")  # Date de début du stream
        self.start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # Timestamp complet
        self.recording_id = f"{person}_{self.start_timestamp}_{session_id[:6]}"  # ID unique
        self.process: Optional[subprocess.Popen] = None
        # Playback HLS is served from /streams/sessions/<id>/stream.m3u8
        self.playback_url = f"/streams/sessions/{self.id}/stream.m3u8"
        # Recording file using unique name: YYYYMMDD_HHMMSS_ID.ts
        self.record_filename = f"{self.start_timestamp}_{session_id[:6]}.ts"
        self.record_path = os.path.join(self.records_dir_for_person, self.record_filename)
        self.log_path = os.path.join(self.sessions_dir, "ffmpeg.log")
        self._stop_evt = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        
        logger.debug("FFmpegSession initialisée", 
                    session_id=session_id, 
                    person=person, 
                    display_name=display_name,
                    sessions_dir=sessions_dir,
                    records_dir=records_dir_for_person)

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
    
    def record_path_today(self) -> str:
        # Utilise la date de début du stream (pas de rotation)
        return self.record_path

    def _writer_loop(self):
        """Read TS from ffmpeg stdout and append to single file (no rotation)."""
        if not self.process or not self.process.stdout:
            logger.warning("Writer loop: pas de processus ou stdout", session_id=self.id)
            return
            
        os.makedirs(self.records_dir_for_person, exist_ok=True)
        
        logger.info("Writer loop démarré", 
                   session_id=self.id, 
                   person=self.person,
                   record_path=self.record_path,
                   start_date=self.start_date)
        
        f = open(self.record_path, "ab", buffering=0)
        total_bytes = 0
        chunk_count = 0
        
        try:
            while not self._stop_evt.is_set():
                chunk = self.process.stdout.read(64 * 1024)
                if not chunk:
                    logger.info("Writer loop: fin du flux", 
                               session_id=self.id,
                               total_bytes=total_bytes,
                               chunk_count=chunk_count)
                    break
                    
                f.write(chunk)
                total_bytes += len(chunk)
                chunk_count += 1
                
                # Log tous les 100MB
                if total_bytes % (100 * 1024 * 1024) < 64 * 1024:
                    logger.debug("Progression écriture", 
                               session_id=self.id,
                               bytes_written=total_bytes,
                               mb_written=f"{total_bytes / 1024 / 1024:.1f}")
                    
        except Exception as e:
            logger.error("Erreur dans writer loop", 
                        session_id=self.id, 
                        exc_info=True,
                        total_bytes=total_bytes)
        finally:
            try:
                f.flush()
                f.close()
                logger.info("Writer loop terminé", 
                           session_id=self.id,
                           total_bytes=total_bytes,
                           mb_written=f"{total_bytes / 1024 / 1024:.1f}")
            except Exception as e:
                logger.error("Erreur fermeture finale fichier", 
                           session_id=self.id, 
                           error=str(e))


class FFmpegManager:
    def __init__(self, base_output_dir: str, ffmpeg_path: str = "ffmpeg", hls_time: int = 4, hls_list_size: int = 6):
        self.base_output_dir = base_output_dir
        self.ffmpeg_path = ffmpeg_path
        self.hls_time = hls_time
        self.hls_list_size = hls_list_size
        self._lock = threading.Lock()
        self._sessions: Dict[str, FFmpegSession] = {}
        # Create subdirectories for sessions (HLS) and records (TS by person/day)
        self.sessions_root = os.path.join(self.base_output_dir, "sessions")
        self.records_root = os.path.join(self.base_output_dir, "records")
        os.makedirs(self.sessions_root, exist_ok=True)
        os.makedirs(self.records_root, exist_ok=True)
        
        logger.info("FFmpegManager initialisé",
                   base_output_dir=base_output_dir,
                   ffmpeg_path=ffmpeg_path,
                   hls_time=hls_time,
                   hls_list_size=hls_list_size,
                   sessions_root=self.sessions_root,
                   records_root=self.records_root)

    def start_session(self, input_url: str, person: str, display_name: Optional[str] = None) -> FFmpegSession:
        logger.ffmpeg_start("new", person, input_url)
        
        with self._lock:
            # Prevent concurrent session for the same person to avoid TS conflicts
            for s in self._sessions.values():
                if getattr(s, "person", None) == person and s.is_running():
                    logger.warning("Session déjà en cours", person=person, existing_session_id=s.id)
                    raise RuntimeError(f"Une session est déjà en cours pour '{person}'.")

            session_id = uuid.uuid4().hex[:10]
            logger.info("Génération Session ID", session_id=session_id, person=person)
            
            sessions_dir = os.path.join(self.sessions_root, session_id)
            os.makedirs(sessions_dir, exist_ok=True)
            logger.debug("Création répertoire session", path=sessions_dir)
            
            records_dir_for_person = os.path.join(self.records_root, person)
            os.makedirs(records_dir_for_person, exist_ok=True)
            logger.debug("Création répertoire enregistrement", path=records_dir_for_person)
            
            sess = FFmpegSession(session_id, input_url, sessions_dir, records_dir_for_person, person, display_name=display_name)

            # Build tee spec: one branch to stdout (pipe:1) as MPEG-TS, one for HLS playback
            hls_seg = os.path.join(sessions_dir, 'seg_%06d.ts')
            hls_m3u8 = os.path.join(sessions_dir, 'stream.m3u8')

            tee_spec = (
                f"[f=mpegts]pipe:1|"
                f"[f=hls:hls_time={self.hls_time}:hls_list_size={self.hls_list_size}:"
                f"hls_flags=delete_segments+append_list+omit_endlist:"
                f"hls_segment_filename={hls_seg}]"
                f"{hls_m3u8}"
            )

            cmd = [
                self.ffmpeg_path,
                "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-y",
                # Options de reconnexion pour stabilité
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "10",
                "-i", sess.input_url,
                "-map", "0",
                "-c", "copy",
                "-f", "tee", tee_spec,
            ]

            logger.debug("Construction commande FFmpeg",
                        session_id=session_id,
                        command=" ".join(cmd[:15]) + "...",  # Première partie seulement
                        log_path=sess.log_path)
            
            log_f = open(sess.log_path, "ab", buffering=0)
            try:
                logger.progress("Lancement processus FFmpeg", session_id=session_id, person=person)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log_f)
                sess.process = proc
                self._sessions[sess.id] = sess
                
                logger.success("Processus FFmpeg démarré", 
                             session_id=session_id, 
                             pid=proc.pid,
                             person=person)
                
                # Start writer thread
                t = threading.Thread(target=sess._writer_loop, name=f"ts-writer-{sess.id}", daemon=True)
                sess._writer_thread = t
                t.start()
                
                logger.info("Thread d'écriture TS démarré", 
                          session_id=session_id, 
                          thread_name=t.name)
                logger.success("Session FFmpeg prête", 
                             session_id=session_id,
                             person=person,
                             playback_url=sess.playback_url,
                             record_path=sess.record_path_today())
                
            except Exception as e:
                logger.critical("Erreur démarrage FFmpeg", 
                              exc_info=True,
                              session_id=session_id,
                              person=person,
                              error=str(e))
                log_f.close()
                raise

            return sess

    def stop_session(self, session_id: str) -> bool:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                logger.warning("Tentative d'arrêt session inexistante", session_id=session_id)
                return False
            
            duration = time.time() - sess.start_time
            logger.ffmpeg_stop(session_id, sess.person, duration)
            
            if sess.process and sess.process.poll() is None:
                try:
                    logger.debug("Arrêt événement writer", session_id=session_id)
                    sess._stop_evt.set()
                    
                    logger.debug("Terminate processus FFmpeg", session_id=session_id, pid=sess.process.pid)
                    sess.process.terminate()
                    
                    try:
                        sess.process.wait(timeout=10)
                        logger.info("Processus FFmpeg terminé proprement", session_id=session_id)
                    except subprocess.TimeoutExpired:
                        logger.warning("Timeout terminate, kill forcé", session_id=session_id)
                        sess.process.kill()
                except Exception as e:
                    logger.error("Erreur arrêt processus FFmpeg", 
                               session_id=session_id, 
                               error=str(e))
                               
            if sess._writer_thread and sess._writer_thread.is_alive():
                try:
                    logger.debug("Attente fin thread writer", session_id=session_id)
                    sess._writer_thread.join(timeout=2)
                    if sess._writer_thread.is_alive():
                        logger.warning("Thread writer toujours actif après timeout", session_id=session_id)
                    else:
                        logger.debug("Thread writer terminé", session_id=session_id)
                except Exception as e:
                    logger.error("Erreur join thread writer", 
                               session_id=session_id, 
                               error=str(e))
            
            logger.success("Session arrêtée", 
                          session_id=session_id, 
                          person=sess.person,
                          duration_seconds=f"{duration:.1f}")
            return True

    def list_status(self) -> List[dict]:
        with self._lock:
            out = []
            for sess in self._sessions.values():
                out.append({
                    "id": sess.id,
                    "person": sess.person,
                    "name": sess.name,
                    "input_url": sess.input_url,
                    "created_at": sess.created_at,
                    "running": sess.is_running(),
                    "playback_url": sess.playback_url,
                    "record_path": sess.record_path,
                    "start_date": sess.start_date,
                })
            logger.debug("Liste status sessions", count=len(out), sessions=[s["id"] for s in out])
            return out
