import unittest
from unittest.mock import AsyncMock, patch

from app.providers.base import (
    ProviderAuthError,
    ProviderCapabilities,
    ProviderInteractionRequired,
    ProviderOfflineError,
    ProviderPrivateError,
    ResolvedStream,
)
from app.providers.browser import BrowserCaptureProvider
from app.providers.browser import extract_media_urls
from app.providers.browser import extract_hls_url_fields
from app.providers.browser import _page_metadata
from app.providers.sessions import ProviderSessionStore
from app.providers.builtin import CAM4Provider, ChaturbateProvider
from app.providers.registry import create_provider_registry
from app.providers.ytdlp import YtDlpProvider
from app.services.cam4_source import (
    CAM4FollowingError,
    _is_followed_page_html,
    _parse_broadcasts,
    list_followed,
)


class _DummyDB:
    pass


class _MemorySessionStore:
    def __init__(self, state=None):
        self.state = dict(state or {})
        self.saved = []

    async def get(self, source_type):
        return dict(self.state)

    async def save(
        self,
        source_type,
        username=None,
        is_logged_in=False,
        cookies=None,
        local_storage=None,
        last_error=None,
    ):
        saved = {
            "source_type": source_type,
            "username": username,
            "is_logged_in": is_logged_in,
            "cookies": cookies or [],
            "localStorage": local_storage or [],
            "last_error": last_error,
        }
        self.saved.append(saved)
        self.state.update(saved)

    async def cookie_header(self, source_type):
        return ProviderSessionStore.cookies_to_header(self.state.get("cookies"))


class ProviderRegistryTests(unittest.IsolatedAsyncioTestCase):
    def test_builtin_registry_includes_supported_sources(self):
        registry = create_provider_registry(_DummyDB())

        self.assertEqual(
            {
                "chaturbate",
                "cam4",
                "stripchat",
                "bongacams",
                "myfreecams",
                "livejasmin",
                "camsoda",
                "cams",
                "xcams",
            },
            registry.source_types(),
        )
        self.assertEqual(
            {
                "chaturbate",
                "cam4",
                "stripchat",
                "bongacams",
                "myfreecams",
                "livejasmin",
                "camsoda",
                "cams",
                "xcams",
            },
            {
                provider.source_type
                for provider in registry.all()
                if provider.capabilities.can_discover
            },
        )
        self.assertTrue(registry.get("xcams").capabilities.can_stream)
        self.assertTrue(registry.get("xcams").capabilities.can_record)
        self.assertTrue(registry.get("livejasmin").capabilities.can_stream)
        self.assertTrue(registry.get("livejasmin").capabilities.can_record)
        self.assertFalse(registry.has("onlyfans"))
        self.assertFalse(registry.has("fansly"))
        self.assertFalse(registry.has("manyvids"))
        self.assertTrue(registry.get("chaturbate").capabilities.can_login)
        self.assertTrue(registry.get("chaturbate").capabilities.can_sync_following)
        self.assertTrue(registry.get("cam4").capabilities.can_login)
        self.assertTrue(registry.get("cam4").capabilities.can_sync_following)
        for source_type in registry.source_types() - {"chaturbate", "cam4"}:
            self.assertFalse(registry.get(source_type).capabilities.can_login)
            self.assertFalse(registry.get(source_type).capabilities.can_sync_following)
            self.assertTrue(registry.get(source_type).capabilities.can_follow)
        self.assertTrue(registry.get("stripchat").capabilities.can_follow)
        self.assertTrue(registry.get("stripchat").capabilities.can_discover)
        self.assertTrue(registry.get("stripchat").capabilities.can_stream)
        self.assertTrue(registry.get("stripchat").capabilities.can_record)
        self.assertTrue(registry.get("bongacams").capabilities.can_follow)

    async def test_ytdlp_provider_delegates_following_to_browser_fallback(self):
        class Fallback:
            capabilities = ProviderCapabilities(
                can_login=True,
                can_follow=True,
                can_sync_following=True,
                can_discover=True,
            )

            async def sync_following(self):
                return [{"username": "alice", "source_type": "stripchat"}]

            async def import_session(
                self,
                username=None,
                cookie_header=None,
                cookies=None,
                local_storage=None,
                user_agent=None,
                x_bc=None,
            ):
                return {
                    "success": True,
                    "username": username,
                    "cookieHeader": cookie_header,
                    "cookies": cookies or [],
                    "localStorage": local_storage or [],
                    "userAgent": user_agent,
                    "xBc": x_bc,
                }

            async def follow(self, username):
                return {"success": True, "username": username, "action": "follow"}

            async def unfollow(self, username):
                return {"success": True, "username": username, "action": "unfollow"}

            async def is_following(self, username):
                return username == "alice"

        provider = YtDlpProvider(
            "stripchat",
            "Stripchat",
            "https://stripchat.com/{username}",
            ("stripchat.com",),
            browser_fallback=Fallback(),
        )

        self.assertTrue(provider.capabilities.can_follow)
        self.assertTrue(provider.capabilities.can_sync_following)
        self.assertEqual("alice", (await provider.sync_following())[0]["username"])
        self.assertEqual("follow", (await provider.follow("alice"))["action"])
        self.assertEqual("unfollow", (await provider.unfollow("alice"))["action"])
        self.assertTrue(await provider.is_following("alice"))
        imported = await provider.import_session(
            username="tester",
            cookie_header="sid=abc",
            local_storage=[{"origin": "https://stripchat.com", "localStorage": []}],
        )
        self.assertTrue(imported["success"])
        self.assertEqual("tester", imported["username"])
        self.assertEqual("sid=abc", imported["cookieHeader"])

    def test_browser_html_media_url_extraction_decodes_escaped_slashes(self):
        urls = extract_media_urls(
            'window.config={"hls":"https:\\/\\/cdn.example.test\\/live\\/room\\/playlist.m3u8?token=abc"}'
        )

        self.assertEqual(
            ["https://cdn.example.test/live/room/playlist.m3u8?token=abc"],
            urls,
        )

    def test_browser_media_url_extraction_ignores_stripchat_ping_probe(self):
        urls = extract_media_urls(
            "https://edge-hls.doppiocdn.net/ping.m3u8 "
            "https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8"
        )

        self.assertEqual(
            ["https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8"],
            urls,
        )

    def test_browser_websocket_hls_url_field_extraction(self):
        urls = extract_hls_url_fields(
            '42["setVideoData",{"protocol":{"h5live":{'
            '"hlsUrl":"https:\\/\\/edge.example.test\\/live\\/jwt-token?expires=123"}}}]'
        )

        self.assertEqual(
            ["https://edge.example.test/live/jwt-token?expires=123"],
            urls,
        )

    def test_browser_discover_parser_extracts_provider_models(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/",),
        )

        items = provider._parse_discover_models(
            '<a href="/alice" data-tags="cosplay, french">'
            '<img src="/alice.jpg" alt="Alice"> Alice <span>1.2k viewers</span> #latex</a>'
            '<a href="/login">Login</a>',
            "https://stripchat.com/",
        )

        self.assertEqual(1, len(items))
        self.assertEqual("alice", items[0]["username"])
        self.assertEqual("https://stripchat.com/alice.jpg", items[0]["thumbnail"])
        self.assertEqual(1200, items[0]["viewers"])
        self.assertEqual(["cosplay", "french", "latex"], items[0]["tags"])
        self.assertEqual("stripchat", items[0]["source_type"])

    def test_browser_page_metadata_extracts_tags_and_viewers(self):
        meta = _page_metadata(
            '<html><head><title>Alice live</title></head><body>'
            '<script>{"viewerCount":"2.5k","tags":["Cosplay",{"name":"French"}]}</script>'
            '<a href="/tags/gamer">Gamer</a> #latex'
            '<img src="/thumb.jpg">'
            '</body></html>',
            "https://stripchat.com/alice",
        )

        self.assertEqual(2500, meta["viewers"])
        self.assertEqual(["gamer", "latex", "cosplay", "french"], meta["tags"])
        self.assertEqual("https://stripchat.com/thumb.jpg", meta["thumbnail"])

    def test_cam4_rendered_cards_add_viewers_and_tags(self):
        items = _parse_broadcasts(
            '<div data-position="1" data-profile="NickiFrenchy">'
            '<a href="/nickifrenchy"><img src="https://thumb.test/n.jpg"></a>'
            '<div data-count="168" data-name="Viewers Count">168</div>'
            '<a href="/tags/female/c2c">#C2C</a>'
            '<a href="/tags/female/femdom">#femdom</a>'
            '</div>'
        )

        self.assertEqual(1, len(items))
        self.assertEqual("NickiFrenchy", items[0]["username"])
        self.assertEqual(168, items[0]["viewers"])
        self.assertIn("c2c", items[0]["tags"])
        self.assertIn("femdom", items[0]["tags"])

    def test_bongacams_cards_add_viewers_and_badge_tags(self):
        provider = BrowserCaptureProvider(
            source_type="bongacams",
            display_name="BongaCams",
            url_templates=("https://bongacams.com/{username}",),
            domains=("bongacams.com",),
            discover_templates=("https://bongacams.com/",),
        )

        items = provider._parse_discover_models(
            '<div class="lst_wrp __hd_plus __vibratoy" data-name="Dana4kabest" data-gender="female">'
            '<a href="/danabest"><img src="/d.jpg"></a>'
            '<div class="lsti_box lst_viewers">188</div>'
            '</div>',
            "https://bongacams.com/",
        )

        self.assertEqual(["danabest"], [item["username"] for item in items])
        self.assertEqual(188, items[0]["viewers"])
        self.assertIn("female", items[0]["tags"])
        self.assertIn("hd plus", items[0]["tags"])
        self.assertIn("vibratoy", items[0]["tags"])

    def test_bongacams_cookie_header_parser_ignores_cookie_attributes(self):
        provider = BrowserCaptureProvider(
            source_type="bongacams",
            display_name="BongaCams",
            url_templates=("https://bongacams.com/{username}",),
            domains=("bongacams.com",),
        )

        cookies = provider._cookie_header_to_playwright_cookies(
            "sessionid=abc; Path=/; Domain=.bongacams.com; Secure; cf_clearance=token"
        )

        by_name = {cookie["name"]: cookie for cookie in cookies}
        self.assertEqual({"sessionid", "cf_clearance"}, set(by_name))
        self.assertEqual(".bongacams.com", by_name["sessionid"]["domain"])
        self.assertTrue(by_name["sessionid"]["secure"])

    async def test_bongacams_ytdlp_respects_quality_cap(self):
        provider = YtDlpProvider(
            "bongacams",
            "BongaCams",
            "https://bongacams.com/{username}",
            ("bongacams.com",),
        )
        info = {
            "formats": [
                {"url": "https://cdn.test/480.m3u8", "height": 480, "tbr": 900, "protocol": "m3u8_native"},
                {"url": "https://cdn.test/720.m3u8", "height": 720, "tbr": 1800, "protocol": "m3u8_native"},
                {"url": "https://cdn.test/1080.m3u8", "height": 1080, "tbr": 3200, "protocol": "m3u8_native"},
            ],
        }

        url, _headers = provider._select_media_url(info, max_height=720)

        self.assertEqual("https://cdn.test/720.m3u8", url)

    def test_stripchat_json_payload_adds_viewers_and_tags(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/girls",),
        )

        items = provider._parse_discover_models(
            '<script type="application/json" data-pstreamrec-url="https://stripchat.com/api/front/v2/models">'
            '{"blocks":[{"models":[{"username":"AliceHD","status":"public","gender":"female",'
            '"broadcastGender":"female","country":"fr","viewersCount":123,"id":42,'
            '"snapshotTimestamp":"1700000000","isOnline":true,"isHd":true,"isLovense":true}]}]}'
            '</script>',
            "https://stripchat.com/girls",
        )

        self.assertEqual(["AliceHD"], [item["username"] for item in items])
        self.assertEqual(123, items[0]["viewers"])
        self.assertEqual("https://img.doppiocdn.net/snapshot/42/1700000000", items[0]["thumbnail"])
        self.assertIn("female", items[0]["tags"])
        self.assertIn("fr", items[0]["tags"])
        self.assertIn("hd", items[0]["tags"])
        self.assertIn("lovense", items[0]["tags"])

    async def test_stripchat_public_api_lists_live_models(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/girls",),
        )
        api = AsyncMock(return_value={
            "models": [
                {
                    "username": "alice",
                    "status": "public",
                    "gender": "female",
                    "viewersCount": 44,
                    "id": 42,
                    "snapshotTimestamp": "1700000000",
                }
            ],
            "totalCount": 1,
        })

        with patch.object(provider, "_stripchat_api_json", api):
            result = await provider.list_live_models(page=1, limit=10, gender="female", search="", tags=[])

        api.assert_awaited_once()
        self.assertEqual(24, api.await_args.kwargs["params"]["limit"])
        self.assertEqual(["alice"], [item["username"] for item in result["models"]])
        self.assertEqual(44, result["models"][0]["viewers"])
        self.assertEqual(1, result["total"])

    async def test_stripchat_public_api_resolves_direct_hls_manifest(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/girls",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "public",
                    "isOnline": True,
                    "isLive": True,
                    "gender": "female",
                    "viewersCount": 77,
                    "snapshotTimestamp": "1700000000",
                    "avatarUrl": "https://img.example.test/avatar-2fa9.jpg",
                }
            },
            "cam": {
                "isCamAvailable": True,
                "isCamActive": True,
                "streamName": "42",
                "streamStatus": "public",
            },
        }

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ) as api, patch.object(
            provider,
            "_stripchat_probe_hls_playlist",
            AsyncMock(return_value=True),
        ) as probe:
            stream = await provider.resolve_stream("alice")

        api.assert_awaited_once()
        self.assertEqual("/v2/models/username/alice/cam", api.await_args.args[1])
        probe.assert_awaited_once()
        self.assertEqual(
            "https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8?minHeight=240&playlistType=standard&pkey=fncnu6utiWqsDLk8",
            stream.url,
        )
        self.assertEqual("stripchat", stream.source_type)
        self.assertEqual("public", stream.room_status)
        self.assertEqual(77, stream.viewers)
        self.assertIn("Referer", stream.headers)
        self.assertIn("Origin", stream.headers)
        self.assertIn("User-Agent", stream.headers)

    def test_stripchat_avatar_url_does_not_trigger_interaction_detection(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
        )

        self.assertFalse(provider._stripchat_login_requires_interaction({
            "user": {
                "avatarUrl": "https://img.example.test/avatar-2fa9.jpg",
            },
        }))
        self.assertTrue(provider._stripchat_login_requires_interaction({
            "error": "2FA verification is required",
        }))

    async def test_stripchat_public_api_caps_hls_manifest_to_configured_height(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/girls",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "public",
                    "isOnline": True,
                    "isLive": True,
                    "viewersCount": 77,
                }
            },
            "cam": {
                "isCamAvailable": True,
                "isCamActive": True,
                "streamName": "42",
                "streamStatus": "public",
            },
        }
        master = "\n".join([
            "#EXTM3U",
            "#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=854x480",
            "480p/index.m3u8",
            "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720",
            "720p/index.m3u8",
            "#EXT-X-STREAM-INF:BANDWIDTH=4500000,RESOLUTION=1920x1080",
            "1080p/index.m3u8",
        ])

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ), patch.object(
            provider,
            "_stripchat_fetch_hls_playlist",
            AsyncMock(return_value=master),
        ) as fetch:
            stream = await provider.resolve_stream("alice", max_height=720)

        fetch.assert_awaited_once()
        self.assertEqual(
            "https://edge-hls.doppiocdn.net/hls/42/master/720p/index.m3u8",
            stream.url,
        )

    async def test_stripchat_public_api_caps_portrait_manifest_by_short_edge(self):
        playlist_url = "https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8"
        master = "\n".join([
            "#EXTM3U",
            "#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=180x240",
            "240p/index.m3u8",
            "#EXT-X-STREAM-INF:BANDWIDTH=1800000,RESOLUTION=360x480",
            "480p/index.m3u8",
            "#EXT-X-STREAM-INF:BANDWIDTH=3500000,RESOLUTION=720x960",
            "720p/index.m3u8",
        ])

        selected = BrowserCaptureProvider._stripchat_variant_url_for_height(
            playlist_url,
            master,
            720,
        )

        self.assertEqual(
            "https://edge-hls.doppiocdn.net/hls/42/master/720p/index.m3u8",
            selected,
        )

    async def test_stripchat_public_api_uses_vr_manifest_when_available(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "public",
                    "isOnline": True,
                    "isLive": True,
                    "isVr": True,
                }
            },
            "cam": {
                "isCamAvailable": True,
                "isCamActive": True,
                "streamName": "vr42",
                "streamStatus": "public",
            },
        }

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ), patch.object(
            provider,
            "_stripchat_probe_hls_playlist",
            AsyncMock(return_value=True),
        ) as probe:
            stream = await provider.resolve_stream("alice")

        probe.assert_awaited_once()
        self.assertEqual(
            "https://edge-hls.doppiocdn.net/hls/vr42_vr/master/vr42_vr.m3u8",
            stream.url,
        )
        self.assertIn("vr", stream.tags)

    async def test_stripchat_public_api_falls_back_when_vr_manifest_is_unavailable(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "public",
                    "isOnline": True,
                    "isLive": True,
                    "isVr": True,
                }
            },
            "cam": {
                "isCamAvailable": True,
                "isCamActive": True,
                "streamName": "vr42",
                "streamStatus": "public",
            },
        }

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ), patch.object(
            provider,
            "_stripchat_probe_hls_playlist",
            AsyncMock(side_effect=[False, True]),
        ) as probe:
            stream = await provider.resolve_stream("alice")

        self.assertEqual(2, probe.await_count)
        self.assertEqual(
            "https://edge-hls.doppiocdn.net/hls/vr42/master/vr42_auto.m3u8?minHeight=240&playlistType=standard&pkey=fncnu6utiWqsDLk8",
            stream.url,
        )

    async def test_stripchat_public_api_limits_catalogue_request_to_fifty(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            discover_templates=("https://stripchat.com/girls",),
        )
        api = AsyncMock(return_value={"models": [], "totalCount": 0})

        with patch.object(provider, "_stripchat_api_json", api):
            await provider.list_live_models(page=1, limit=100, gender=None, search="", tags=[])

        self.assertEqual(50, api.await_args.kwargs["params"]["limit"])

    async def test_stripchat_public_resolver_rejects_offline_payload_without_hls_probe(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "offline",
                    "isOnline": False,
                }
            },
            "cam": {
                "isCamAvailable": False,
                "streamName": "42",
                "streamStatus": "offline",
            },
        }

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ), patch.object(
            provider,
            "_stripchat_probe_hls_playlist",
            AsyncMock(return_value=True),
        ) as probe:
            with self.assertRaises(ProviderOfflineError):
                await provider.resolve_stream("alice")

        probe.assert_not_awaited()

    async def test_stripchat_public_resolver_rejects_private_payload_without_hls_probe(self):
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
        )
        payload = {
            "user": {
                "user": {
                    "id": 42,
                    "username": "alice",
                    "status": "public",
                    "isOnline": True,
                    "isLive": True,
                }
            },
            "cam": {
                "isCamAvailable": True,
                "streamName": "42",
                "streamStatus": "public",
                "show": {"type": "private"},
            },
        }

        with patch.object(
            provider,
            "_stripchat_api_json",
            AsyncMock(return_value=payload),
        ), patch.object(
            provider,
            "_stripchat_probe_hls_playlist",
            AsyncMock(return_value=True),
        ) as probe:
            with self.assertRaises(ProviderPrivateError):
                await provider.resolve_stream("alice")

        probe.assert_not_awaited()

    async def test_stripchat_ytdlp_private_error_uses_guarded_public_fallback(self):
        class Fallback:
            capabilities = ProviderCapabilities(can_stream=True)

            def __init__(self):
                self.resolve_stream = AsyncMock(return_value=ResolvedStream(
                    url="https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8",
                    headers={"Referer": "https://stripchat.com/alice"},
                    source_type="stripchat",
                    room_status="public",
                    is_live=True,
                ))

        fallback = Fallback()
        provider = YtDlpProvider(
            "stripchat",
            "Stripchat",
            "https://stripchat.com/{username}",
            ("stripchat.com",),
            browser_fallback=fallback,
        )

        with patch.object(provider, "_extract_info", side_effect=Exception("Model is in a private show")):
            stream = await provider.resolve_stream("alice")

        self.assertEqual("https://edge-hls.doppiocdn.net/hls/42/master/42_auto.m3u8", stream.url)
        fallback.resolve_stream.assert_awaited_once_with("alice", max_height=None)

    async def test_stripchat_ytdlp_private_error_keeps_fallback_private_terminal(self):
        class Fallback:
            capabilities = ProviderCapabilities(can_stream=True)

            def __init__(self):
                self.resolve_stream = AsyncMock(side_effect=ProviderPrivateError("private show"))

        fallback = Fallback()
        provider = YtDlpProvider(
            "stripchat",
            "Stripchat",
            "https://stripchat.com/{username}",
            ("stripchat.com",),
            browser_fallback=fallback,
        )

        with patch.object(provider, "_extract_info", side_effect=Exception("Model is in a private show")):
            with self.assertRaises(ProviderPrivateError):
                await provider.resolve_stream("alice")

        fallback.resolve_stream.assert_awaited_once_with("alice", max_height=None)

    async def test_stripchat_sync_follow_and_unfollow_use_front_api(self):
        class SessionStore:
            async def get(self, source_type):
                return {
                    "cookies": [{"name": "sid", "value": "abc"}],
                    "localStorage": [
                        {
                            "origin": "https://stripchat.com",
                            "localStorage": [
                                {"name": "currentUser", "value": '{"currentUser":{"id":99,"username":"tester"}}'},
                                {"name": "jwtToken", "value": "token-value"},
                            ],
                        }
                    ],
                    "username": "tester",
                    "is_logged_in": 1,
                }

            async def cookie_header(self, source_type):
                return "sid=abc"

        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=SessionStore(),
            discover_templates=("https://stripchat.com/girls",),
        )
        calls = []

        async def fake_api(method, path, params=None, body=None, auth_required=False, referer=None):
            calls.append({
                "method": method,
                "path": path,
                "params": params,
                "body": body,
                "auth_required": auth_required,
                "referer": referer,
            })
            if path == "/models/favorites":
                return {
                    "models": [
                        {
                            "username": "alice",
                            "status": "public",
                            "viewersCount": 12,
                            "id": 42,
                        }
                    ],
                    "totalCount": 1,
                }
            if path == "/models/favorites/offline":
                return {"models": [], "totalCount": 0}
            if path.startswith("/v2/models/username/"):
                return {
                    "user": {
                        "isInFavorites": True,
                        "user": {
                            "id": 42,
                            "username": "alice",
                            "status": "public",
                            "viewersCount": 12,
                        },
                    },
                    "cam": {"isCamAvailable": True, "streamName": "42"},
                }
            return {}

        with patch.object(provider, "_stripchat_api_json", AsyncMock(side_effect=fake_api)):
            synced = await provider.sync_following()
            followed = await provider.follow("alice")
            unfollowed = await provider.unfollow("alice")
            is_following = await provider.is_following("alice")

        self.assertEqual(["alice"], [item["username"] for item in synced])
        self.assertTrue(followed["success"])
        self.assertTrue(unfollowed["success"])
        self.assertTrue(is_following)
        put_call = next(call for call in calls if call["method"] == "PUT")
        delete_call = next(call for call in calls if call["method"] == "DELETE")
        self.assertEqual("/users/99/favorites/42", put_call["path"])
        self.assertEqual("/users/99/favorites", delete_call["path"])
        self.assertEqual([42], delete_call["body"]["favoriteIds"])
        self.assertIn("uniq", delete_call["body"])

    async def test_stripchat_login_http_saves_verified_session(self):
        store = _MemorySessionStore()
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=store,
        )
        calls = []

        async def fake_http(session, method, path, params=None, body=None, referer=None, include_stored_auth=False, front_version=None):
            calls.append({
                "method": method,
                "path": path,
                "body": body,
                "referer": referer,
                "include_stored_auth": include_stored_auth,
                "front_version": front_version,
            })
            return {
                "user": {"id": 99, "username": "tester"},
                "jwtToken": "token-value",
                "_http_status": 200,
            }

        with patch.object(
            provider,
            "_stripchat_seed_http_session",
            AsyncMock(return_value={"front_version": "11.7.28", "csrfToken": "csrf"}),
        ), patch.object(
            provider,
            "_stripchat_http_json",
            AsyncMock(side_effect=fake_http),
        ), patch.object(
            provider,
            "_stripchat_cookie_jar_to_playwright",
            return_value=[{"name": "sid", "value": "abc", "domain": ".stripchat.com", "path": "/"}],
        ):
            result = await provider.login("tester", "secret")

        self.assertTrue(result["success"])
        self.assertEqual("tester", result["username"])
        self.assertTrue(store.saved[-1]["is_logged_in"])
        self.assertEqual([{"name": "sid", "value": "abc", "domain": ".stripchat.com", "path": "/"}], store.saved[-1]["cookies"])
        storage_entries = store.saved[-1]["localStorage"][0]["localStorage"]
        self.assertEqual("currentUser", storage_entries[0]["name"])
        self.assertIn('"username":"tester"', storage_entries[0]["value"])
        self.assertEqual({"name": "jwtToken", "value": "token-value"}, storage_entries[1])
        self.assertEqual("POST", calls[0]["method"])
        self.assertEqual("/auth/login", calls[0]["path"])
        self.assertEqual("tester", calls[0]["body"]["loginOrEmail"])
        self.assertEqual("csrf", calls[0]["body"]["csrfToken"])
        self.assertFalse(calls[0]["include_stored_auth"])

    async def test_stripchat_login_http_returns_clear_bad_credentials_error(self):
        store = _MemorySessionStore()
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=store,
        )

        with patch.object(
            provider,
            "_stripchat_seed_http_session",
            AsyncMock(return_value={"front_version": "11.7.28"}),
        ), patch.object(
            provider,
            "_stripchat_http_json",
            AsyncMock(return_value={"message": "invalid password", "_http_status": 401}),
        ), patch.object(
            provider,
            "_browser_login",
            AsyncMock(return_value={"success": False, "error": "Login failed. Check username and password."}),
        ):
            result = await provider.login("tester", "wrong")

        self.assertFalse(result["success"])
        self.assertEqual("Login failed. Check username and password.", result["error"])
        self.assertFalse(store.saved[-1]["is_logged_in"])
        self.assertEqual("login_failed", store.saved[-1]["last_error"])

    async def test_stripchat_login_http_failure_can_use_browser_fallback(self):
        store = _MemorySessionStore()
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=store,
        )

        with patch.object(
            provider,
            "_stripchat_seed_http_session",
            AsyncMock(return_value={"front_version": "11.7.28"}),
        ), patch.object(
            provider,
            "_stripchat_http_json",
            AsyncMock(return_value={"message": "invalid password", "_http_status": 401}),
        ), patch.object(
            provider,
            "_browser_login",
            AsyncMock(return_value={"success": True, "username": "tester"}),
        ) as browser_login:
            result = await provider.login("tester", "secret")

        self.assertTrue(result["success"])
        self.assertEqual("tester", result["username"])
        browser_login.assert_awaited_once_with("tester", "secret")

    async def test_stripchat_login_http_maps_challenge_to_interaction_required(self):
        store = _MemorySessionStore()
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=store,
        )

        with patch.object(
            provider,
            "_stripchat_seed_http_session",
            AsyncMock(return_value={"front_version": "11.7.28"}),
        ), patch.object(
            provider,
            "_stripchat_http_json",
            AsyncMock(return_value={"needCodeConfirmation": True, "_http_status": 409}),
        ):
            with self.assertRaises(ProviderInteractionRequired):
                await provider.login("tester", "secret")

        self.assertFalse(store.saved[-1]["is_logged_in"])
        self.assertEqual("interaction_required", store.saved[-1]["last_error"])

    async def test_stripchat_sync_requires_verified_session(self):
        store = _MemorySessionStore({
            "cookies": [{"name": "sid", "value": "abc"}],
            "localStorage": [],
            "username": "tester",
            "is_logged_in": 0,
        })
        provider = BrowserCaptureProvider(
            source_type="stripchat",
            display_name="Stripchat",
            url_templates=("https://stripchat.com/{username}",),
            domains=("stripchat.com",),
            session_store=store,
        )

        with self.assertRaises(ProviderAuthError):
            await provider.sync_following()
        with self.assertRaises(ProviderAuthError):
            await provider.follow("alice")
        with self.assertRaises(ProviderAuthError):
            await provider.unfollow("alice")

    async def test_bongacams_following_uses_local_state_when_remote_session_unavailable(self):
        class DB:
            rows = [
                {
                    "username": "alice",
                    "display_name": "Alice",
                    "is_online": True,
                    "viewers": 9,
                    "thumbnail_url": "https://thumb.test/a.jpg",
                    "source_type": "bongacams",
                    "room_status": "public",
                },
                {
                    "username": "bob",
                    "display_name": "Bob",
                    "is_online": False,
                    "viewers": 0,
                    "source_type": "stripchat",
                    "room_status": "public",
                },
            ]

            async def get_all_followed(self):
                return [dict(row) for row in self.rows]

            async def get_followed_model(self, username):
                for row in self.rows:
                    if row["username"] == username:
                        return dict(row)
                return None

        class SessionStore:
            db = DB()

            async def get(self, source_type):
                return {}

        provider = BrowserCaptureProvider(
            source_type="bongacams",
            display_name="BongaCams",
            url_templates=("https://bongacams.com/{username}",),
            domains=("bongacams.com",),
            session_store=SessionStore(),
            discover_templates=("https://bongacams.com/",),
        )

        synced = await provider.sync_following()
        followed = await provider.follow("alice")
        unfollowed = await provider.unfollow("alice")

        self.assertEqual(["alice"], [item["username"] for item in synced])
        self.assertEqual("https://thumb.test/a.jpg", synced[0]["thumbnail"])
        self.assertTrue(followed["success"])
        self.assertTrue(followed["localOnly"])
        self.assertEqual("follow", followed["action"])
        self.assertTrue(unfollowed["success"])
        self.assertTrue(unfollowed["localOnly"])
        self.assertEqual("unfollow", unfollowed["action"])
        self.assertTrue(await provider.is_following("alice"))
        self.assertFalse(await provider.is_following("missing"))

    def test_livejasmin_embedded_performer_tags_are_parsed(self):
        provider = BrowserCaptureProvider(
            source_type="livejasmin",
            display_name="LiveJasmin",
            url_templates=("https://www.livejasmin.com/en/girls/{username}",),
            domains=("livejasmin.com",),
            discover_templates=("https://www.livejasmin.com/en/girls",),
        )

        items = provider._parse_discover_models(
            '<script>window._JSMConfig={}; listPagePerformers = ['
            '{"display_name":"LessieLean","status":1,"profilePictureUrl":"https://img.test/l.jpg",'
            '"willingnesses":{"cosplay":"Cosplay","live_orgasm":"Live orgasm"},'
            '"language":"lng_en","region":"EU","main_category":"girl"}];</script>',
            "https://www.livejasmin.com/en/girls",
        )

        self.assertEqual("LessieLean", items[0]["username"])
        self.assertEqual(["cosplay", "live orgasm", "en", "eu"], items[0]["tags"])

    def test_myfreecams_model_boxes_are_parsed_with_global_tags(self):
        provider = BrowserCaptureProvider(
            source_type="myfreecams",
            display_name="MyFreeCams",
            url_templates=("https://www.myfreecams.com/#{username}",),
            domains=("myfreecams.com",),
            discover_templates=("https://www.myfreecams.com/",),
        )

        items = provider._parse_discover_models(
            '<a href="/?tag=ebony">ebony</a><a href="#">\u00d7</a>'
            '<div class="model_online homepage_online_pattern2 modelbox_3765510" id="model_box_3765510" data-list-pos="0">'
            '<a title="Enter Chat Room of BeaClips">Chat</a><img src="https://img.test/b.jpg"></div>',
            "https://www.myfreecams.com/",
        )

        self.assertEqual(["BeaClips"], [item["username"] for item in items])
        self.assertIn("ebony", items[0]["tags"])

class BuiltinProviderDiscoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_chaturbate_resolve_stream_carries_llhls_video_index(self):
        provider = ChaturbateProvider()

        with (
            patch(
                "app.resolvers.chaturbate.resolve_m3u8_async",
                AsyncMock(return_value="https://edge.example.test/live/llhls.m3u8"),
            ) as resolve,
            patch(
                "app.resolvers.chaturbate.resolve_llhls_master_playlist",
                AsyncMock(return_value={
                    "video_stream_index": 3,
                    "text": "#EXTM3U\n",
                    "base_url": "https://edge.example.test/live/llhls.m3u8",
                    "content_type": "application/vnd.apple.mpegurl",
                }),
            ) as pick_index,
        ):
            stream = await provider.resolve_stream("alice", max_height=None)

        self.assertEqual("https://edge.example.test/live/llhls.m3u8", stream.url)
        self.assertEqual(3, stream.ffmpeg_video_stream_index)
        self.assertEqual("#EXTM3U\n", stream.hls_playlist_text)
        resolve.assert_awaited_once_with("alice", max_height=None)
        pick_index.assert_awaited_once()

    async def test_chaturbate_discover_filters_generic_kwargs(self):
        class FakeAPI:
            def __init__(self):
                self.kwargs = None

            async def get_live_models(self, **kwargs):
                self.kwargs = kwargs
                return {"models": [{"username": "alice"}]}

        api = FakeAPI()
        provider = ChaturbateProvider(api=api)

        result = await provider.list_live_models(
            page=2,
            limit=7,
            gender="female",
            search="ali",
            tags=["french"],
            allow_browser=True,
        )

        self.assertEqual({"page": 2, "limit": 7, "gender": "female", "search": "ali", "tag": "french"}, api.kwargs)
        self.assertEqual("chaturbate", result["models"][0]["source_type"])

    async def test_chaturbate_status_supplements_tags_and_viewers_from_discover(self):
        class FakeAPI:
            async def check_status(self, username):
                return {
                    "is_online": True,
                    "viewers": 0,
                    "room_status": "public",
                    "hls_source": "https://cdn.example/live.m3u8",
                    "tags": [],
                }

            async def get_live_models(self, **kwargs):
                return {
                    "models": [
                        {
                            "username": kwargs["search"],
                            "viewers": 321,
                            "tags": ["French", "Cosplay"],
                            "thumbnail": "https://example.test/thumb.jpg",
                            "room_status": "public",
                        }
                    ]
                }

        provider = ChaturbateProvider(api=FakeAPI())

        status = await provider.check_status("alice")

        self.assertTrue(status.is_online)
        self.assertEqual(321, status.viewers)
        self.assertEqual(["French", "Cosplay"], status.tags)
        self.assertEqual("https://example.test/thumb.jpg", status.thumbnail)

    async def test_chaturbate_account_actions_require_verified_session(self):
        class FakeAuth:
            def get_status(self):
                return {"isLoggedIn": False, "username": "tester"}

            def get_cookies(self):
                return {"sessionid": "expired"}

        class FakeAPI:
            def __init__(self):
                self.get_followed_models = AsyncMock(return_value=[])
                self.follow_model = AsyncMock(return_value=True)
                self.unfollow_model = AsyncMock(return_value=True)
                self.is_following = AsyncMock(return_value=True)

        api = FakeAPI()
        provider = ChaturbateProvider(api=api, auth=FakeAuth())

        with self.assertRaises(ProviderAuthError):
            await provider.sync_following()
        with self.assertRaises(ProviderAuthError):
            await provider.follow("alice")
        with self.assertRaises(ProviderAuthError):
            await provider.unfollow("alice")

        self.assertFalse(await provider.is_following("alice"))
        api.get_followed_models.assert_not_awaited()
        api.follow_model.assert_not_awaited()
        api.unfollow_model.assert_not_awaited()
        api.is_following.assert_not_awaited()

    async def test_chaturbate_import_session_requires_sessionid_cookie(self):
        class FakeAuth:
            pass

        provider = ChaturbateProvider(auth=FakeAuth())

        result = await provider.import_session(cookie_header="csrftoken=csrf")

        self.assertFalse(result["success"])
        self.assertIn("sessionid", result["error"])

    async def test_cam4_discover_filters_generic_kwargs(self):
        provider = CAM4Provider()
        mocked = AsyncMock(return_value={"models": [{"username": "bob"}]})

        with patch("app.services.cam4_source.list_live_models", mocked):
            result = await provider.list_live_models(page=3, limit=5, tags=["tag"], allow_browser=True)

        mocked.assert_awaited_once_with(page=3, limit=5, gender=None, search=None, tags=["tag"])
        self.assertEqual("cam4", result["models"][0]["source_type"])

    async def test_cam4_list_followed_requires_cookies(self):
        with self.assertRaises(CAM4FollowingError):
            await list_followed({})

    async def test_cam4_list_followed_accepts_valid_empty_favorites_page(self):
        html = '<link data-chunk="pages-friendsFavorites" href="/favorites.js">'

        with patch("app.services.cam4_source._fetch_followed_html", AsyncMock(return_value=html)):
            self.assertEqual([], await list_followed({"JSESSIONID": "test"}))

    async def test_cam4_sync_following_maps_expired_session_to_auth_error(self):
        class Auth:
            def get_cookies(self):
                return {"JSESSIONID": "test"}

        provider = CAM4Provider(auth=Auth())
        mocked = AsyncMock(side_effect=CAM4FollowingError("CAM4 session expirée"))

        with patch("app.services.cam4_source.list_followed", mocked):
            with self.assertRaises(ProviderAuthError):
                await provider.sync_following()


class CAM4FollowingPageTests(unittest.TestCase):
    def test_followed_page_detector_accepts_empty_favorites_page(self):
        html = '<link data-chunk="pages-friendsFavorites" href="/favorites.js">'

        self.assertTrue(
            _is_followed_page_html(
                html,
                "https://www.cam4.com/friends_favorites?showOfflineBroadcasters=true",
            )
        )

    def test_followed_page_detector_rejects_login_or_error_pages(self):
        self.assertFalse(_is_followed_page_html('<form id="loginForm"></form>', "https://www.cam4.com/login"))
        self.assertFalse(_is_followed_page_html("<html>error-no-profile</html>", "https://www.cam4.com/error-no-profile"))


if __name__ == "__main__":
    unittest.main()
