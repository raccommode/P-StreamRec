import os
import shutil
import uuid
import threading
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse
from .logger import logger
from .core.http_client import (
    ffmpeg_http_proxy_url,
    get_outbound_proxy_url,
    is_socks_proxy,
)
from .core.config import MIN_RECORDING_SECONDS
from .recording_names import (
    FILENAME_FORMAT_TIMESTAMP,
    recording_base_name,
)

_TS_PACKET_SIZE = 188
_CHATURBATE_HLS_HOST_SUFFIXES = ("chaturbate.com", "highwebmedia.com", "mmcdn.com")
_CHATURBATE_HLS_HEADERS = (
    "Referer: https://chaturbate.com/\r\n"
    "Origin: https://chaturbate.com\r\n"
    "Connection: keep-alive\r\n"
)
_FINISHED_SESSION_GRACE_SECONDS = 300


def _is_chaturbate_hls_url(input_url: str) -> bool:
    try:
        hostname = (urlparse(input_url).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _CHATURBATE_HLS_HOST_SUFFIXES
    )


def _is_local_hls_proxy_url(input_url: str) -> bool:
    try:
        parsed = urlparse(input_url)
    except Exception:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return hostname in {"127.0.0.1", "localhost", "::1"} and parsed.path.startswith("/api/proxy/hls/")


def _chaturbate_hls_input_args(input_url: str) -> List[str]:
    if not _is_chaturbate_hls_url(input_url):
        return []
    return [
        "-http_persistent", "1",
        "-http_multiple", "0",
        "-multiple_requests", "1",
        "-headers", _CHATURBATE_HLS_HEADERS,
    ]


def _headers_dict_to_ffmpeg(headers: Optional[Dict[str, str]]) -> str:
    if not headers:
        return ""
    lines = []
    for key, value in headers.items():
        if not key or value is None:
            continue
        clean_key = str(key).replace("\r", "").replace("\n", "").strip()
        clean_value = str(value).replace("\r", " ").replace("\n", " ").strip()
        if not clean_key or ":" in clean_key:
            continue
        lines.append(f"{clean_key}: {clean_value}\r\n")
    return "".join(lines)


def _hls_input_args(input_url: str, input_headers: Optional[Dict[str, str]]) -> List[str]:
    args: List[str] = [
        "-allowed_extensions", "ALL",
        "-allowed_segment_extensions", "ALL",
        "-extension_picky", "0",
    ]
    is_chaturbate = _is_chaturbate_hls_url(input_url)
    if is_chaturbate:
        args.extend([
            "-http_persistent", "1",
            "-http_multiple", "0",
            "-multiple_requests", "1",
        ])

    header_blob = _headers_dict_to_ffmpeg(input_headers)
    if header_blob:
        args.extend(["-headers", header_blob])
    elif is_chaturbate:
        args.extend(["-headers", _CHATURBATE_HLS_HEADERS])
    return args


def _redact_ffmpeg_command(cmd: List[str]) -> List[str]:
    safe_cmd = []
    redact_next = False
    for part in cmd:
        if redact_next:
            safe_cmd.append("***")
            redact_next = False
            continue
        safe_cmd.append(part)
        if part in {"-http_proxy", "-headers"}:
            redact_next = True
    return safe_cmd


def _build_ffmpeg_command(
    ffmpeg_path: str,
    input_url: str,
    tee_spec: str,
    max_height: Optional[int] = None,
    input_headers: Optional[Dict[str, str]] = None,
    source_url: Optional[str] = None,
    ffmpeg_video_stream_index: Optional[int] = None,
) -> List[str]:
    cmd = [
        ffmpeg_path,
        "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-y",
    ]

    if not _is_local_hls_proxy_url(input_url):
        # Options de reconnexion pour stabilité. The local HLS proxy serves
        # short-lived playlists/segments; reconnecting at EOF can stall with
        # an empty recording.
        cmd.extend([
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_on_network_error", "1",
            # 403/404 generally mean an expired HLS token/segment. Retrying
            # the same URL keeps a dead session around; let the monitor
            # re-resolve instead. 5xx remains worth retrying briefly.
            "-reconnect_on_http_error", "5xx",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "10",
            "-reconnect_delay_total_max", "120",
        ])

    cmd.extend([
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ])

    proxy_url = ffmpeg_http_proxy_url()
    if proxy_url:
        cmd.extend(["-http_proxy", proxy_url])
    elif is_socks_proxy(get_outbound_proxy_url()):
        logger.warning(
            "Proxy SOCKS configuré: les requêtes Python l'utilisent, "
            "mais FFmpeg ne supporte ici que les proxys HTTP(S)"
        )

    cmd.extend(_hls_input_args(input_url, input_headers))

    stream_identity_url = source_url or input_url

    # For Chaturbate LL-HLS master playlists, the master URL contains both
    # video variants and a separate audio rendition group. The FFmpeg transport
    # URL may be the local HLS proxy, so use the original upstream URL for this
    # detection when available.
    is_chaturbate_llhls = (
        "llhls.m3u8" in stream_identity_url.lower()
        and _is_chaturbate_hls_url(stream_identity_url)
    )
    if is_chaturbate_llhls:
        try:
            v_idx = int(ffmpeg_video_stream_index) if ffmpeg_video_stream_index is not None else 0
        except (TypeError, ValueError):
            v_idx = 0
        if v_idx < 0:
            v_idx = 0
        map_args = ["-map", f"0:v:{v_idx}", "-map", "0:a:0"]
    else:
        map_args = ["-map", "0"]

    cmd.extend([
        "-i", input_url,
        *map_args,
        "-c", "copy",
        "-f", "tee", tee_spec,
    ])
    return cmd


class FFmpegSession:
    def __init__(
        self,
        session_id: str,
        input_url: str,
        sessions_dir: str,
        records_dir_for_person: str,
        person: str,
        display_name: Optional[str] = None,
        segment_duration_seconds: int = 0,
        segment_size_bytes: int = 0,
        input_headers: Optional[Dict[str, str]] = None,
        source_url: Optional[str] = None,
        ffmpeg_video_stream_index: Optional[int] = None,
        filename_format: str = FILENAME_FORMAT_TIMESTAMP,
        source_type: Optional[str] = None,
        target: Optional[str] = None,
        session_key: Optional[str] = None,
    ):
        self.id = session_id
        self.input_url = input_url
        self.source_url = source_url or input_url
        self.ffmpeg_video_stream_index = ffmpeg_video_stream_index
        self.source_type = (source_type or "").strip().lower()
        self.target = (target or "").strip()
        self.input_headers = dict(input_headers or {})
        self.sessions_dir = sessions_dir
        self.records_dir_for_person = records_dir_for_person
        self.person = person
        self.session_key = session_key or person
        self.name = display_name or person or session_id
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.start_time = time.time()
        self.start_date = datetime.now().strftime("%Y-%m-%d")  # Date de début du stream
        self.start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # Timestamp complet
        self.recording_id = f"{person}_{self.start_timestamp}_{session_id[:6]}"  # ID unique
        self.process: Optional[subprocess.Popen] = None
        # Playback HLS is served from /streams/sessions/<id>/stream.m3u8
        self.playback_url = f"/streams/sessions/{self.id}/stream.m3u8"
        self.filename_format = filename_format
        self.segment_duration_seconds = max(0, int(segment_duration_seconds or 0))
        self.segment_size_bytes = max(0, int(segment_size_bytes or 0))
        self.segment_enabled = self.segment_duration_seconds > 0 or self.segment_size_bytes > 0
        self.record_base = self._unique_record_base(
            recording_base_name(person, self.start_timestamp, session_id, filename_format)
        )
        self.segment_index = 1
        # Recording file using unique name: YYYYMMDD_HHMMSS_ID.ts. Segmented
        # sessions append _partNNN only when segmentation is enabled.
        self.record_filename = self._record_filename_for_segment(self.segment_index)
        self.record_path = os.path.join(self.records_dir_for_person, self.record_filename)
        self.log_path = os.path.join(self.sessions_dir, "ffmpeg.log")
        self._stop_evt = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self.bytes_written = 0
        self.last_progress_at = self.start_time
        self.exit_returncode: Optional[int] = None
        self.completed_at: Optional[str] = None
        self.completed_monotonic: Optional[float] = None
        
        logger.debug("FFmpegSession initialisée", 
                    session_id=session_id, 
                    person=person, 
                    display_name=display_name,
                    sessions_dir=sessions_dir,
                    records_dir=records_dir_for_person,
                    segment_duration_seconds=self.segment_duration_seconds,
                    segment_size_bytes=self.segment_size_bytes,
                    filename_format=self.filename_format)

    def is_running(self) -> bool:
        if self.process is None:
            return False
        rc = self.process.poll()
        if rc is not None:
            self.exit_returncode = rc
            return False
        return True

    def seconds_since_progress(self) -> float:
        return max(0.0, time.time() - self.last_progress_at)
    
    def record_path_today(self) -> str:
        return self.record_path

    def _record_filename_for_segment(self, segment_index: int) -> str:
        if self.segment_enabled:
            return f"{self.record_base}_part{segment_index:03d}.ts"
        return f"{self.record_base}.ts"

    def _unique_record_base(self, base: str) -> str:
        first_name = f"{base}_part001.ts" if self.segment_enabled else f"{base}.ts"
        first_path = os.path.join(self.records_dir_for_person, first_name)
        if not os.path.exists(first_path):
            return base
        return f"{base}_{self.id[:6]}"

    def _advance_segment_path(self):
        self.segment_index += 1
        self.record_filename = self._record_filename_for_segment(self.segment_index)
        self.record_path = os.path.join(self.records_dir_for_person, self.record_filename)

    def _recording_paths_for_cleanup(self) -> List[str]:
        if not self.segment_enabled:
            return [self.record_path]

        paths: List[str] = []
        prefix = f"{self.record_base}_part"
        try:
            for filename in os.listdir(self.records_dir_for_person):
                if filename.startswith(prefix) and filename.endswith(".ts"):
                    paths.append(os.path.join(self.records_dir_for_person, filename))
        except OSError:
            pass
        if self.record_path not in paths:
            paths.append(self.record_path)
        return paths

    def _writer_loop(self):
        """Read TS from ffmpeg stdout and optionally rotate recording segments."""
        if not self.process or not self.process.stdout:
            logger.warning("Writer loop: pas de processus ou stdout", session_id=self.id)
            return
            
        os.makedirs(self.records_dir_for_person, exist_ok=True)
        
        logger.info("Writer loop démarré", 
                   session_id=self.id, 
                   person=self.person,
                   record_path=self.record_path,
                   start_date=self.start_date,
                   segment_duration_seconds=self.segment_duration_seconds,
                   segment_size_bytes=self.segment_size_bytes)
        
        # 1 MiB chunks + 1 MiB write buffer: drastically fewer read/write syscalls
        # vs. the previous 64 KiB/unbuffered loop. CPU overhead of the writer
        # thread goes from "wakes ~100 times/sec on a busy stream" to a handful.
        CHUNK_SIZE = 1024 * 1024
        f = None
        total_bytes = 0
        segment_bytes = 0
        segment_started_at = time.time()
        chunk_count = 0
        last_log_threshold = 0
        pending = b""

        def open_current_file():
            nonlocal f, segment_started_at
            if f is None:
                os.makedirs(self.records_dir_for_person, exist_ok=True)
                f = open(self.record_path, "ab", buffering=CHUNK_SIZE)
                segment_started_at = time.time()
                logger.info(
                    "Segment recording démarré",
                    session_id=self.id,
                    person=self.person,
                    segment_index=self.segment_index,
                    record_path=self.record_path,
                )

        def close_current_file(reason: str):
            nonlocal f
            if f is None:
                return
            try:
                f.flush()
                f.close()
                logger.info(
                    "Segment recording fermé",
                    session_id=self.id,
                    person=self.person,
                    segment_index=self.segment_index,
                    segment_bytes=segment_bytes,
                    reason=reason,
                    record_path=self.record_path,
                )
            finally:
                f = None

        def should_rotate_for_duration() -> bool:
            if not self.segment_enabled or self.segment_duration_seconds <= 0:
                return False
            return segment_bytes > 0 and (time.time() - segment_started_at) >= self.segment_duration_seconds

        def rotate_segment(reason: str):
            nonlocal segment_bytes
            if not self.segment_enabled:
                return
            close_current_file(reason)
            self._advance_segment_path()
            segment_bytes = 0

        def write_segmented(data: bytes):
            nonlocal total_bytes, segment_bytes, chunk_count, last_log_threshold
            offset = 0
            data_len = len(data)

            while offset < data_len:
                if should_rotate_for_duration():
                    rotate_segment("duration")

                open_current_file()

                write_len = data_len - offset
                if self.segment_size_bytes > 0:
                    capacity = self.segment_size_bytes - segment_bytes
                    if capacity < _TS_PACKET_SIZE and segment_bytes > 0:
                        rotate_segment("size")
                        open_current_file()
                        capacity = self.segment_size_bytes

                    capacity = max(_TS_PACKET_SIZE, capacity)
                    capacity -= capacity % _TS_PACKET_SIZE
                    if capacity <= 0:
                        capacity = _TS_PACKET_SIZE
                    write_len = min(write_len, capacity)

                f.write(data[offset:offset + write_len])
                offset += write_len
                total_bytes += write_len
                segment_bytes += write_len
                chunk_count += 1
                self.bytes_written = total_bytes
                self.last_progress_at = time.time()

                threshold_100mb = total_bytes // (100 * 1024 * 1024)
                if threshold_100mb > last_log_threshold:
                    last_log_threshold = threshold_100mb
                    logger.debug(
                        "Progression écriture",
                        session_id=self.id,
                        bytes_written=total_bytes,
                        mb_written=f"{total_bytes / 1024 / 1024:.1f}",
                        current_segment=self.segment_index,
                    )

                if self.segment_size_bytes > 0 and segment_bytes >= self.segment_size_bytes:
                    rotate_segment("size")
                elif should_rotate_for_duration():
                    rotate_segment("duration")

        def write_plain(data: bytes):
            nonlocal total_bytes, chunk_count, last_log_threshold
            open_current_file()
            f.write(data)
            total_bytes += len(data)
            chunk_count += 1
            self.bytes_written = total_bytes
            self.last_progress_at = time.time()

            threshold_100mb = total_bytes // (100 * 1024 * 1024)
            if threshold_100mb > last_log_threshold:
                last_log_threshold = threshold_100mb
                logger.debug(
                    "Progression écriture",
                    session_id=self.id,
                    bytes_written=total_bytes,
                    mb_written=f"{total_bytes / 1024 / 1024:.1f}",
                )

        try:
            open_current_file()
            while True:
                chunk = self.process.stdout.read(CHUNK_SIZE)
                if not chunk:
                    logger.info("Writer loop: fin du flux",
                               session_id=self.id,
                               total_bytes=total_bytes,
                               chunk_count=chunk_count)
                    break

                if self.segment_enabled:
                    data = pending + chunk
                    packet_bytes = (len(data) // _TS_PACKET_SIZE) * _TS_PACKET_SIZE
                    if packet_bytes:
                        write_segmented(data[:packet_bytes])
                    pending = data[packet_bytes:]
                else:
                    write_plain(chunk)

            if pending:
                write_segmented(pending)

        except Exception:
            logger.error("Erreur dans writer loop", 
                        session_id=self.id, 
                        exc_info=True,
                        total_bytes=total_bytes)
        finally:
            elapsed = time.time() - self.start_time
            try:
                close_current_file("finished")
                logger.info("Writer loop terminé", 
                           session_id=self.id,
                           total_bytes=total_bytes,
                           mb_written=f"{total_bytes / 1024 / 1024:.1f}",
                           elapsed_seconds=f"{elapsed:.1f}")
            except Exception as e:
                logger.error("Erreur fermeture finale fichier", 
                           session_id=self.id, 
                           error=str(e))
            self.bytes_written = total_bytes
            if self.process:
                self.exit_returncode = self.process.poll()
            self.completed_at = datetime.utcnow().isoformat() + "Z"
            self.completed_monotonic = time.time()
            self._cleanup_short_recording(total_bytes, elapsed)

    def _cleanup_short_recording(self, total_bytes: int, elapsed_seconds: float):
        """Remove startup failures and tiny fragments before they reach the UI."""
        if total_bytes > 0:
            return
        reason = "empty"

        try:
            deleted_paths = []
            for path in self._recording_paths_for_cleanup():
                if os.path.exists(path):
                    os.remove(path)
                    deleted_paths.append(path)
            if deleted_paths:
                logger.warning(
                    "Fragment recording supprimé",
                    session_id=self.id,
                    person=self.person,
                    reason=reason,
                    elapsed_seconds=f"{elapsed_seconds:.1f}",
                    bytes_written=total_bytes,
                    min_seconds=MIN_RECORDING_SECONDS,
                    deleted_paths=deleted_paths,
                )
        except Exception as e:
            logger.error(
                "Erreur suppression fragment recording",
                session_id=self.id,
                person=self.person,
                error=str(e),
            )


class FFmpegManager:
    def __init__(self, base_output_dir: str, ffmpeg_path: str = "ffmpeg", hls_time: int = 4, hls_list_size: int = 6):
        self.base_output_dir = base_output_dir
        self.ffmpeg_path = ffmpeg_path
        self.hls_time = hls_time
        self.hls_list_size = hls_list_size
        self._lock = threading.Lock()
        self._sessions: Dict[str, FFmpegSession] = {}
        try:
            self.stall_timeout_seconds = int(os.getenv("FFMPEG_STALL_TIMEOUT_SECONDS", "180"))
        except ValueError:
            self.stall_timeout_seconds = 180
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
                   stall_timeout_seconds=self.stall_timeout_seconds,
                   sessions_root=self.sessions_root,
                   records_root=self.records_root)

    def start_session(
        self,
        input_url: str,
        person: str,
        display_name: Optional[str] = None,
        max_height: Optional[int] = None,
        segment_duration_seconds: int = 0,
        segment_size_bytes: int = 0,
        input_headers: Optional[Dict[str, str]] = None,
        source_url: Optional[str] = None,
        ffmpeg_video_stream_index: Optional[int] = None,
        filename_format: str = FILENAME_FORMAT_TIMESTAMP,
        records_dir_for_person: Optional[str] = None,
        source_type: Optional[str] = None,
        target: Optional[str] = None,
        session_key: Optional[str] = None,
    ) -> FFmpegSession:
        logger.ffmpeg_start("new", person, input_url)
        
        with self._lock:
            self._prune_finished_locked()

            session_key = session_key or person
            # Prevent concurrent session for the same logical target. Multi-source
            # Media profiles pass a source-specific key so they can record more
            # than one channel into the same profile folder.
            for s in self._sessions.values():
                existing_key = getattr(s, "session_key", None) or getattr(s, "person", None)
                if existing_key == session_key and s.is_running():
                    logger.warning("Session déjà en cours", person=person, session_key=session_key, existing_session_id=s.id)
                    raise RuntimeError(f"Une session est déjà en cours pour '{person}'.")

            session_id = uuid.uuid4().hex[:10]
            logger.info("Génération Session ID", session_id=session_id, person=person)
            
            sessions_dir = os.path.join(self.sessions_root, session_id)
            os.makedirs(sessions_dir, exist_ok=True)
            logger.debug("Création répertoire session", path=sessions_dir)
            
            records_dir_for_person = records_dir_for_person or os.path.join(self.records_root, person)
            os.makedirs(records_dir_for_person, exist_ok=True)
            logger.debug("Création répertoire enregistrement", path=records_dir_for_person)
            
            sess = FFmpegSession(
                session_id,
                input_url,
                sessions_dir,
                records_dir_for_person,
                person,
                display_name=display_name,
                segment_duration_seconds=segment_duration_seconds,
                segment_size_bytes=segment_size_bytes,
                input_headers=input_headers,
                source_url=source_url,
                ffmpeg_video_stream_index=ffmpeg_video_stream_index,
                filename_format=filename_format,
                source_type=source_type,
                target=target,
                session_key=session_key,
            )

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

            cmd = _build_ffmpeg_command(
                self.ffmpeg_path,
                sess.input_url,
                tee_spec,
                max_height=max_height,
                input_headers=sess.input_headers,
                source_url=sess.source_url,
                ffmpeg_video_stream_index=sess.ffmpeg_video_stream_index,
            )

            safe_cmd = _redact_ffmpeg_command(cmd)

            logger.debug("Construction commande FFmpeg",
                        session_id=session_id,
                        command=" ".join(safe_cmd[:17]) + "...",
                        log_path=sess.log_path)
            
            log_f = open(sess.log_path, "ab", buffering=0)
            try:
                logger.progress("Lancement processus FFmpeg", session_id=session_id, person=person)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log_f)
                log_f.close()
                log_f = None
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

                time.sleep(1)
                if proc.poll() is not None:
                    if sess._writer_thread and sess._writer_thread.is_alive():
                        sess._writer_thread.join(timeout=2)
                    self._sessions.pop(sess.id, None)
                    sess.exit_returncode = proc.returncode
                    logger.warning(
                        "FFmpeg arrêté immédiatement",
                        session_id=session_id,
                        person=person,
                        returncode=proc.returncode,
                        log_path=sess.log_path,
                    )
                    raise RuntimeError(
                        "FFmpeg s'est arrêté immédiatement. Le flux est probablement indisponible ou le token HLS a expiré."
                    )
                
            except Exception as e:
                logger.critical("Erreur démarrage FFmpeg", 
                              exc_info=True,
                              session_id=session_id,
                              person=person,
                              error=str(e))
                if log_f is not None:
                    log_f.close()
                if sess.process and sess.process.poll() is None:
                    try:
                        sess.process.terminate()
                        sess.process.wait(timeout=5)
                    except Exception:
                        try:
                            sess.process.kill()
                        except Exception:
                            pass
                self._sessions.pop(sess.id, None)
                raise

            return sess

    def get_session(self, session_id: str) -> Optional[FFmpegSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def _finalize_session_locked(self, sess: FFmpegSession, join_timeout: float = 0.2):
        if sess.process:
            sess.exit_returncode = sess.process.poll()
        if sess._writer_thread and sess._writer_thread.is_alive():
            sess._writer_thread.join(timeout=join_timeout)
        if sess.completed_monotonic is None and sess.exit_returncode is not None:
            sess.completed_monotonic = time.time()
            sess.completed_at = sess.completed_at or (datetime.utcnow().isoformat() + "Z")

    def _cleanup_session_dir(self, sess: FFmpegSession) -> bool:
        writer = sess._writer_thread
        if writer and writer.is_alive():
            logger.warning(
                "Nettoyage session HLS reporté: writer actif",
                session_id=sess.id,
                person=sess.person,
            )
            return False

        has_recording = False
        for path in sess._recording_paths_for_cleanup():
            try:
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    has_recording = True
                    break
            except OSError:
                continue
        if sess.bytes_written <= 0 or not has_recording:
            logger.info(
                "Répertoire session HLS conservé pour diagnostic",
                session_id=sess.id,
                person=sess.person,
                bytes_written=sess.bytes_written,
            )
            return False

        sessions_root = os.path.realpath(self.sessions_root)
        session_dir = os.path.realpath(sess.sessions_dir)
        if os.path.dirname(session_dir) != sessions_root:
            logger.error(
                "Nettoyage session HLS refusé hors racine",
                session_id=sess.id,
                session_dir=session_dir,
                sessions_root=sessions_root,
            )
            return False

        try:
            if os.path.isdir(session_dir):
                shutil.rmtree(session_dir)
                logger.info(
                    "Répertoire session HLS supprimé",
                    session_id=sess.id,
                    person=sess.person,
                    path=session_dir,
                )
            return True
        except OSError as exc:
            logger.warning(
                "Échec nettoyage répertoire session HLS",
                session_id=sess.id,
                person=sess.person,
                path=session_dir,
                error=str(exc),
            )
            return False

    def _prune_finished_locked(self) -> int:
        pruned = 0
        for session_id, sess in list(self._sessions.items()):
            if sess.is_running():
                continue
            self._finalize_session_locked(sess)
            if sess._writer_thread and sess._writer_thread.is_alive():
                continue
            if (
                sess.bytes_written > 0
                and sess.completed_monotonic is not None
                and time.time() - sess.completed_monotonic < _FINISHED_SESSION_GRACE_SECONDS
            ):
                continue
            self._cleanup_session_dir(sess)
            self._sessions.pop(session_id, None)
            pruned += 1
            logger.info(
                "Session FFmpeg terminée retirée du registre",
                session_id=session_id,
                person=sess.person,
                returncode=sess.exit_returncode,
                bytes_written=sess.bytes_written,
            )
        return pruned

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
                        try:
                            sess.process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            logger.error("Processus FFmpeg toujours vivant après kill", session_id=session_id)
                    sess.exit_returncode = sess.process.poll()
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
            writer_active = bool(sess._writer_thread and sess._writer_thread.is_alive())
            if not writer_active:
                self._cleanup_session_dir(sess)
                self._sessions.pop(session_id, None)
            else:
                logger.warning(
                    "Session FFmpeg conservée jusqu'à la fin du writer",
                    session_id=session_id,
                    person=sess.person,
                )
            return True

    def stalled_session_ids(self, max_idle_seconds: Optional[int] = None) -> List[str]:
        if max_idle_seconds is None:
            max_idle_seconds = self.stall_timeout_seconds
        if max_idle_seconds <= 0:
            return []

        with self._lock:
            self._prune_finished_locked()
            stalled = []
            for sess in self._sessions.values():
                if not sess.is_running():
                    continue
                runtime = time.time() - sess.start_time
                idle = sess.seconds_since_progress()
                if runtime >= max_idle_seconds and idle >= max_idle_seconds:
                    stalled.append(sess.id)
            return stalled

    def stop_stalled_sessions(self, max_idle_seconds: Optional[int] = None) -> List[dict]:
        stopped = []
        for session_id in self.stalled_session_ids(max_idle_seconds):
            with self._lock:
                sess = self._sessions.get(session_id)
                if not sess:
                    continue
                info = {
                    "id": sess.id,
                    "person": sess.person,
                    "bytes_written": sess.bytes_written,
                    "idle_seconds": int(sess.seconds_since_progress()),
                }
                logger.warning(
                    "Session FFmpeg sans progression, arrêt watchdog",
                    session_id=sess.id,
                    person=sess.person,
                    bytes_written=sess.bytes_written,
                    idle_seconds=info["idle_seconds"],
                )
            if self.stop_session(session_id):
                stopped.append(info)
        return stopped

    def list_status(self) -> List[dict]:
        with self._lock:
            self._prune_finished_locked()
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
                    "bytes_written": sess.bytes_written,
                    "seconds_since_progress": int(sess.seconds_since_progress()),
                    "source_type": sess.source_type,
                    "target": sess.target,
                    "session_key": sess.session_key,
                })
            logger.debug("Liste status sessions", count=len(out), sessions=[s["id"] for s in out])
            return out
