import os
import uuid
import threading
import subprocess
from datetime import datetime
from typing import Dict, List, Optional


class FFmpegSession:
    def __init__(self, session_id: str, input_url: str, sessions_dir: str, records_dir_for_person: str, person: str, display_name: Optional[str] = None):
        self.id = session_id
        self.input_url = input_url
        self.sessions_dir = sessions_dir
        self.records_dir_for_person = records_dir_for_person
        self.person = person
        self.name = display_name or person or session_id
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.process: Optional[subprocess.Popen] = None
        # Playback HLS is served from /streams/sessions/<id>/stream.m3u8
        self.playback_url = f"/streams/sessions/{self.id}/stream.m3u8"
        # Recording template per day
        self.record_template = os.path.join(self.records_dir_for_person, "%Y-%m-%d.ts")
        self.log_path = os.path.join(self.sessions_dir, "ffmpeg.log")
        self._stop_evt = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
    
    def record_path_today(self) -> str:
        # Use server local date, aligned with segment_atclocktime behaviour
        return datetime.now().strftime(self.record_template)

    def _writer_loop(self):
        """Read TS from ffmpeg stdout and append to daily file, rotating at midnight."""
        if not self.process or not self.process.stdout:
            return
        current_day = datetime.now().strftime("%Y-%m-%d")
        current_path = self.record_path_today()
        os.makedirs(self.records_dir_for_person, exist_ok=True)
        f = open(current_path, "ab", buffering=0)
        try:
            while not self._stop_evt.is_set():
                chunk = self.process.stdout.read(64 * 1024)
                if not chunk:
                    break
                today = datetime.now().strftime("%Y-%m-%d")
                if today != current_day:
                    # rotate
                    try:
                        f.flush()
                        f.close()
                    except Exception:
                        pass
                    current_day = today
                    current_path = self.record_path_today()
                    f = open(current_path, "ab", buffering=0)
                f.write(chunk)
        finally:
            try:
                f.flush(); f.close()
            except Exception:
                pass


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

    def start_session(self, input_url: str, person: str, display_name: Optional[str] = None) -> FFmpegSession:
        with self._lock:
            # Prevent concurrent session for the same person to avoid TS conflicts
            for s in self._sessions.values():
                if getattr(s, "person", None) == person and s.is_running():
                    raise RuntimeError(f"Une session est déjà en cours pour '{person}'.")

            session_id = uuid.uuid4().hex[:10]
            sessions_dir = os.path.join(self.sessions_root, session_id)
            os.makedirs(sessions_dir, exist_ok=True)
            records_dir_for_person = os.path.join(self.records_root, person)
            os.makedirs(records_dir_for_person, exist_ok=True)
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
                "-nostdin", "-hide_banner", "-loglevel", "error",
                "-y",
                "-fflags", "+genpts",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "30",
                "-i", sess.input_url,
                "-map", "0", "-c", "copy",
                "-f", "tee", tee_spec,
            ]

            log_f = open(sess.log_path, "ab", buffering=0)
            try:
                # Capture stdout for TS writer, keep logs on stderr
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log_f)
                sess.process = proc
                self._sessions[sess.id] = sess
                # Start writer thread
                t = threading.Thread(target=sess._writer_loop, name=f"ts-writer-{sess.id}", daemon=True)
                sess._writer_thread = t
                t.start()
            except Exception:
                log_f.close()
                raise

            return sess

    def stop_session(self, session_id: str) -> bool:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return False
            if sess.process and sess.process.poll() is None:
                try:
                    sess._stop_evt.set()
                    sess.process.terminate()
                    try:
                        sess.process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        sess.process.kill()
                except Exception:
                    pass
            if sess._writer_thread and sess._writer_thread.is_alive():
                try:
                    sess._writer_thread.join(timeout=2)
                except Exception:
                    pass
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
                    "record_path": sess.record_path_today(),
                    "record_template": sess.record_template,
                })
            return out
