import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.ffmpeg_runner import FFmpegManager, FFmpegSession, _build_ffmpeg_command


class FFmpegCommandTests(unittest.TestCase):
    def _build(self, input_url, **kwargs):
        with (
            patch("app.ffmpeg_runner.ffmpeg_http_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.get_outbound_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.is_socks_proxy", return_value=False),
        ):
            return _build_ffmpeg_command("ffmpeg", input_url, "tee-output", **kwargs)

    def _maps(self, cmd):
        return [cmd[i + 1] for i, part in enumerate(cmd) if part == "-map"]

    def _maps(self, cmd):
        return [cmd[index + 1] for index, value in enumerate(cmd) if value == "-map"]

    def test_chaturbate_cdn_uses_persistent_http_before_input(self):
        cmd = self._build(
            "https://edge30-ash.live.mmcdn.com/live/test/llhls.m3u8",
            ffmpeg_video_stream_index=3,
        )
        input_index = cmd.index("-i")

        self.assertLess(cmd.index("-http_persistent"), input_index)
        self.assertEqual(cmd[cmd.index("-http_persistent") + 1], "1")
        self.assertLess(cmd.index("-http_multiple"), input_index)
        self.assertEqual(cmd[cmd.index("-http_multiple") + 1], "0")
        self.assertLess(cmd.index("-multiple_requests"), input_index)
        self.assertEqual(cmd[cmd.index("-multiple_requests") + 1], "1")

        headers = cmd[cmd.index("-headers") + 1]
        self.assertIn("Referer: https://chaturbate.com/", headers)
        self.assertIn("Origin: https://chaturbate.com", headers)
        self.assertIn("Connection: keep-alive", headers)
        self.assertEqual(["0:v:3", "0:a:0"], self._maps(cmd))

    def test_chaturbate_llhls_uses_resolved_video_stream_index(self):
        with (
            patch("app.ffmpeg_runner.ffmpeg_http_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.get_outbound_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.is_socks_proxy", return_value=False),
        ):
            cmd = _build_ffmpeg_command(
                "ffmpeg",
                "https://edge30-ash.live.mmcdn.com/live/test/llhls.m3u8",
                "tee-output",
                max_height=720,
                ffmpeg_video_stream_index=2,
            )

        self.assertEqual(["0:v:2", "0:a:0"], self._maps(cmd))

    def test_proxied_chaturbate_llhls_uses_source_url_for_mapping(self):
        with (
            patch("app.ffmpeg_runner.ffmpeg_http_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.get_outbound_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.is_socks_proxy", return_value=False),
        ):
            cmd = _build_ffmpeg_command(
                "ffmpeg",
                "http://127.0.0.1:8080/api/proxy/hls/token.m3u8",
                "tee-output",
                source_url="https://edge30-ash.live.mmcdn.com/live/test/llhls.m3u8",
                ffmpeg_video_stream_index=3,
            )

        self.assertEqual(["0:v:3", "0:a:0"], self._maps(cmd))
        self.assertNotIn("-reconnect_at_eof", cmd)

    def test_non_chaturbate_hls_keeps_default_http_behavior(self):
        cmd = self._build("https://example.com/live/test/playlist.m3u8")

        self.assertNotIn("-http_persistent", cmd)
        self.assertNotIn("-http_multiple", cmd)
        self.assertNotIn("-multiple_requests", cmd)
        self.assertNotIn("-headers", cmd)
        self.assertIn("-reconnect_at_eof", cmd)
        self.assertLess(cmd.index("-allowed_extensions"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-allowed_extensions") + 1], "ALL")
        self.assertLess(cmd.index("-allowed_segment_extensions"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-allowed_segment_extensions") + 1], "ALL")
        self.assertLess(cmd.index("-extension_picky"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-extension_picky") + 1], "0")
        self.assertIn("-i", cmd)

    def test_local_hls_proxy_skips_eof_reconnect(self):
        cmd = self._build("http://127.0.0.1:8080/api/proxy/hls/token.m3u8")

        self.assertNotIn("-reconnect", cmd)
        self.assertNotIn("-reconnect_at_eof", cmd)
        self.assertNotIn("-reconnect_streamed", cmd)
        self.assertLess(cmd.index("-allowed_extensions"), cmd.index("-i"))
        self.assertEqual(["0"], self._maps(cmd))

    def test_proxied_chaturbate_llhls_uses_source_url_for_best_mapping(self):
        cmd = self._build(
            "http://127.0.0.1:8080/api/proxy/hls/token.m3u8",
            source_url="https://edge30-ash.live.mmcdn.com/live/test/llhls.m3u8",
            ffmpeg_video_stream_index=3,
        )

        self.assertEqual(["0:v:3", "0:a:0"], self._maps(cmd))

    def test_chaturbate_llhls_without_resolved_index_falls_back_to_first_video(self):
        cmd = self._build(
            "https://edge30-ash.live.mmcdn.com/live/test/llhls.m3u8",
            max_height=720,
        )

        self.assertEqual(["0:v:0", "0:a:0"], self._maps(cmd))

    def test_provider_headers_are_passed_before_input(self):
        with (
            patch("app.ffmpeg_runner.ffmpeg_http_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.get_outbound_proxy_url", return_value=None),
            patch("app.ffmpeg_runner.is_socks_proxy", return_value=False),
        ):
            cmd = _build_ffmpeg_command(
                "ffmpeg",
                "https://example.com/live/test/playlist.m3u8",
                "tee-output",
                input_headers={
                    "Referer": "https://example.com/model",
                    "Cookie": "session=secret",
                },
            )

        input_index = cmd.index("-i")
        self.assertLess(cmd.index("-headers"), input_index)
        headers = cmd[cmd.index("-headers") + 1]
        self.assertIn("Referer: https://example.com/model", headers)
        self.assertIn("Cookie: session=secret", headers)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 5, 27, 12, 34, 56)
        return value if tz is None else value.replace(tzinfo=tz)

    @classmethod
    def utcnow(cls):
        return cls(2026, 5, 27, 16, 34, 56)


class FFmpegFilenameTests(unittest.TestCase):
    def _session(self, root: Path, **kwargs):
        with patch("app.ffmpeg_runner.datetime", FixedDatetime):
            return FFmpegSession(
                session_id="abcdef1234",
                input_url="https://example.test/live.m3u8",
                sessions_dir=str(root / "sessions"),
                records_dir_for_person=str(root / "records" / "model"),
                person="model",
                **kwargs,
            )

    def test_default_filename_keeps_timestamp_session_id_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = self._session(Path(tmp))

        self.assertEqual("20260527_123456_abcdef.ts", session.record_filename)

    def test_username_timestamp_filename_omits_session_id_until_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records" / "model"
            records.mkdir(parents=True)

            session = self._session(root, filename_format="username_timestamp")
            self.assertEqual("model_20260527-123456.ts", session.record_filename)

            (records / session.record_filename).write_bytes(b"existing")
            collision = self._session(root, filename_format="username_timestamp")
            self.assertEqual("model_20260527-123456_abcdef.ts", collision.record_filename)

    def test_username_timestamp_segmented_filename_uses_part_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = self._session(
                Path(tmp),
                filename_format="username_timestamp",
                segment_duration_seconds=1800,
            )

        self.assertEqual("model_20260527-123456_part001.ts", session.record_filename)


class FFmpegSessionCleanupTests(unittest.TestCase):
    def _session(self, root: Path, session_id: str = "abcdef1234"):
        session_dir = root / "sessions" / session_id
        records_dir = root / "records" / "model"
        session_dir.mkdir(parents=True)
        records_dir.mkdir(parents=True)
        return FFmpegSession(
            session_id=session_id,
            input_url="https://example.test/live.m3u8",
            sessions_dir=str(session_dir),
            records_dir_for_person=str(records_dir),
            person="model",
        )

    def test_completed_recording_removes_hls_session_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = FFmpegManager(str(root))
            session = self._session(root)
            (Path(session.sessions_dir) / "stream.m3u8").write_text("#EXTM3U")
            (Path(session.sessions_dir) / "seg_000001.ts").write_bytes(b"segment")
            Path(session.record_path).write_bytes(b"recording")
            session.bytes_written = len(b"recording")

            self.assertTrue(manager._cleanup_session_dir(session))
            self.assertFalse(Path(session.sessions_dir).exists())
            self.assertTrue(Path(session.record_path).exists())

    def test_failed_recording_keeps_hls_session_directory_for_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = FFmpegManager(str(root))
            session = self._session(root)
            log_path = Path(session.log_path)
            log_path.write_text("ffmpeg failure")

            self.assertFalse(manager._cleanup_session_dir(session))
            self.assertTrue(log_path.exists())

    def test_cleanup_refuses_session_directory_outside_sessions_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = FFmpegManager(str(root / "managed"))
            outside = root / "outside"
            session = self._session(outside)
            Path(session.record_path).write_bytes(b"recording")
            session.bytes_written = len(b"recording")

            self.assertFalse(manager._cleanup_session_dir(session))
            self.assertTrue(Path(session.sessions_dir).exists())


if __name__ == "__main__":
    unittest.main()
