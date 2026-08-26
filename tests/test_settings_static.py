import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SettingsStaticTests(unittest.TestCase):
    def test_recording_filename_format_control_is_wired(self):
        html = (ROOT / "static" / "settings.html").read_text()
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertIn("filenameFormatSelect", html)
        self.assertIn("username_timestamp", html)
        self.assertIn("Recording Filename Format", html)
        self.assertIn("filenameFormatSelect", js)
        self.assertIn("data.filename_format || 'timestamp'", js)
        self.assertIn("updateRecordingSetting('filename_format', this.value)", html)

    def test_auto_record_uses_configured_interval_and_cooldown(self):
        main = (ROOT / "app" / "main.py").read_text()

        self.assertNotIn("await asyncio.sleep(180)", main)
        self.assertIn("check_interval = await get_check_interval_seconds(db)", main)
        self.assertIn("failure_cooldowns", main)

    def test_settings_header_status_badge_is_removed(self):
        html = (ROOT / "static" / "settings.html").read_text()

        self.assertNotIn("settings-page-kicker", html)
        self.assertNotIn("Settings status", html)
        self.assertNotIn("settingsApiPill", html)
        self.assertNotIn("settingsApiDot", html)

    def test_shared_header_does_not_show_gitops_button(self):
        header = (ROOT / "static" / "header.html").read_text()
        loader = (ROOT / "static" / "loader.js").read_text()

        self.assertNotIn("GitOps", header)
        self.assertNotIn("gitStatusBtn", header)
        self.assertNotIn("gitStatusIcon", header)
        self.assertNotIn("gitStatusText", header)
        self.assertNotIn("/api/git/status", loader)
        self.assertNotIn("checkGitStatus", loader)
        self.assertIn('id="logoutBtn"', header)
        self.assertIn("data.authentication_required", loader)
        self.assertIn("fetch('/api/logout', { method: 'POST' })", loader)

    def test_shared_header_warns_that_project_was_replaced(self):
        header = (ROOT / "static" / "header.html").read_text()
        css = (ROOT / "static" / "styles.css").read_text()
        readme = (ROOT / "README.md").read_text()
        replacement_url = "https://github.com/raccommode/OpenEasyX"

        self.assertIn('class="project-status-banner"', header)
        self.assertIn("P-StreamRec is no longer maintained.", header)
        self.assertIn(replacement_url, header)
        self.assertIn(".project-status-banner", css)
        self.assertIn("P-StreamRec is no longer maintained.", readme)
        self.assertIn(replacement_url, readme)

    def test_settings_application_tab_is_removed(self):
        html = (ROOT / "static" / "settings.html").read_text()
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertNotIn('data-tab="application"', html)
        self.assertNotIn('id="tab-application"', html)
        self.assertNotIn('id="appVersionSetting"', html)
        self.assertNotIn('id="apiStatus"', html)
        self.assertNotIn("appVersionSetting", js)

    def test_flaresolverr_settings_url_can_be_edited(self):
        html = (ROOT / "static" / "settings.html").read_text()
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertIn("flareUrlInput", html)
        self.assertIn("flareSaveBtn", html)
        self.assertIn("saveFlareSolverrUrl", js)
        self.assertIn("loadFlareSolverrSettings", js)
        self.assertIn("/api/settings/flaresolverr", js)
        self.assertIn("FlareSolverr URL saved", js)
        self.assertNotIn("configured via environment variables", html)

    def test_flaresolverr_is_not_configured_by_environment_variables(self):
        files = [
            "app/main.py",
            "app/core/config.py",
            "app/providers/browser.py",
            "app/services/flaresolverr.py",
            "docker-compose.yml",
            "README.md",
            "static/wiki.html",
        ]
        text = "\n".join((ROOT / path).read_text() for path in files)

        self.assertNotIn("FLARESOLVERR_URL", text)
        self.assertNotIn("PSTREAMREC_FLARESOLVERR_URL", text)
        self.assertNotIn("FLARESOLVERR_MAX_TIMEOUT", text)
        self.assertNotIn("PSTREAMREC_FLARESOLVERR_TIMEOUT_MS", text)
        self.assertNotRegex(text, r"os\.getenv\([^)]*FLARESOLVERR")

    def test_recording_settings_exposes_check_interval_control(self):
        html = (ROOT / "static" / "settings.html").read_text()
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertIn('id="checkIntervalInput"', html)
        self.assertIn("check_interval_seconds", html)
        self.assertIn("function normalizeCheckIntervalSeconds", js)
        self.assertIn("function setCheckIntervalInput", js)
        self.assertIn("data.check_interval_seconds", js)

    def test_blacklisted_tags_use_dom_events_instead_of_inline_javascript(self):
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertIn("removeButton.addEventListener('click'", js)
        self.assertIn("chip.appendChild(document.createTextNode(String(tag)))", js)
        self.assertNotIn("onclick=\"removeBlacklistedTag", js)

    def test_dynamic_inline_handlers_use_javascript_string_escaping(self):
        for filename in ("discover.js", "following.js", "recordings.js", "settings.js"):
            js = (ROOT / "static" / filename).read_text()
            self.assertIn("function escapeInlineJs(value)", js, filename)
            self.assertIn(".replace(/'/g, '\\\\x27')", js, filename)
            self.assertIn(".replace(/</g, '\\\\x3c')", js, filename)

        discover = (ROOT / "static" / "discover.js").read_text()
        following = (ROOT / "static" / "following.js").read_text()
        recordings = (ROOT / "static" / "recordings.js").read_text()
        settings = (ROOT / "static" / "settings.js").read_text()
        self.assertIn("toggleFollowOnCard(\\'' + escapeInlineJs(model.username)", discover)
        self.assertIn("unfollowFollowingModel(\\'' + escapeInlineJs(username)", following)
        self.assertIn("playRecording(\\'' + escapeInlineJs(username)", recordings)
        self.assertIn("navigator.clipboard.writeText(\\'' + escapeInlineJs(input)", settings)

    def test_hls_player_dependency_is_version_pinned_with_integrity(self):
        expected_src = "https://cdn.jsdelivr.net/npm/hls.js@1.6.16/dist/hls.min.js"
        expected_integrity = (
            "sha384-5E8B0pTlZZJMabWpC0fyYf6OUpe15jJij34BqBAh4NXoHAlLNOjCPRrwtOXOQFAn"
        )
        for filename in ("watch.html", "recordings.html"):
            html = (ROOT / "static" / filename).read_text()
            self.assertIn(expected_src, html, filename)
            self.assertIn(expected_integrity, html, filename)
            self.assertIn('crossorigin="anonymous"', html, filename)
            self.assertNotIn("hls.js@latest", html, filename)

    def test_tests_center_covers_local_diagnostics(self):
        js = (ROOT / "static" / "settings.js").read_text()
        test_ids = set(re.findall(r"id: '([^']+)'", js))

        self.assertTrue(
            {
                "api",
                "routes",
                "providers",
                "system",
                "recording",
                "following",
                "processes",
                "flaresolverr",
                "recordings",
                "media-imports",
                "blacklist",
            }.issubset(test_ids)
        )
        self.assertNotIn("chaturbate", test_ids)
        self.assertNotIn("cam4", test_ids)
        self.assertNotRegex(js, r"id:\s*'chaturbate'")
        self.assertNotRegex(js, r"id:\s*'cam4'")
        self.assertNotRegex(js, r"name:\s*'Chaturbate account'")
        self.assertNotRegex(js, r"name:\s*'CAM4 account'")
        self.assertIn("Legacy dashboard route still exists", js)
        self.assertIn("Removed provider still registered", js)
        self.assertIn("Missing status for", js)
        self.assertIn("Chaturbate and CAM4 should expose account login", js)
        self.assertIn("Chaturbate and CAM4 should expose remote sync", js)

    def test_following_page_lists_local_follow_providers(self):
        js = (ROOT / "static" / "following.js").read_text()

        self.assertIn("function providersForFollowing(models)", js)
        self.assertIn("providerBySource[sourceType] = Object.assign({}, provider", js)
        self.assertNotIn("if (caps.can_sync_following === true) {\n      providerBySource[sourceType]", js)
        self.assertIn("No local follows saved for this provider.", js)

    def test_media_page_has_profile_filter_and_continuous_playback(self):
        html = (ROOT / "static" / "media.html").read_text()
        header = (ROOT / "static" / "header.html").read_text()
        js = (ROOT / "static" / "media.js").read_text()
        css = (ROOT / "static" / "styles.css").read_text()

        self.assertNotIn('href="/recordings"', header)
        self.assertNotIn('data-page="recordings"', header)
        self.assertNotIn("Recordings</a>", header)
        self.assertIn('href="/media" class="nav-link" data-page="media">Media</a>', header)
        self.assertNotIn('href="/stash"', header)
        self.assertIn("<title>Media - P-StreamRec</title>", html)
        self.assertIn("mediaNewProfileBtn", html)
        self.assertIn("mediaProfileFilter", html)
        self.assertIn("mediaAutoRecordFilter", html)
        self.assertIn("Auto-record enabled", html)
        self.assertIn("Auto-record disabled", html)
        self.assertNotIn("mediaProfileDetail", html)
        self.assertNotIn("mediaProfileFilterBtn", html)
        self.assertNotIn("mediaProfileClearBtn", html)
        self.assertNotIn("mediaUploadBtn", html)
        self.assertNotIn("mediaUploadForm", html)
        self.assertNotIn("/uploads", html)
        self.assertIn("Date of birth", html)
        self.assertIn("Profile image URL", html)
        self.assertIn("Babepedia page URL", html)
        self.assertIn("Fetch Babepedia image", html)
        self.assertIn("profileSourcesList", html)
        self.assertIn("profileAddSourceBtn", html)
        self.assertIn("Add source", html)
        self.assertIn("mediaUnwatchedOnlyToggle", html)
        self.assertIn("Unwatched", html)
        self.assertIn("profileImageUrl", js)
        self.assertIn("streamSources", js)
        self.assertIn("channelUsername", js)
        self.assertIn("channelUsernameFromUrl", js)
        self.assertIn("sourceTypeFromUrl", js)
        self.assertIn("{ value: 'stripchat', label: 'Stripchat'", js)
        self.assertIn("selectedProfile", js)
        self.assertIn("filterProfile", js)
        self.assertIn("formatProfileMediaCounts", js)
        self.assertIn("mediaProfileFilter", js)
        self.assertIn("autoRecordFilter: 'all'", js)
        self.assertIn("function visibleProfiles()", js)
        self.assertIn("No profiles match this filter", js)
        self.assertIn("media-profile-menu-btn", js)
        self.assertIn('data-profile-action="settings"', js)
        self.assertNotIn("renderProfileDetail", js)
        self.assertNotIn("filterSelectedProfile", js)
        self.assertNotIn("clearSelectedProfile", js)
        self.assertIn("showNextPrompt", js)
        self.assertIn("nextVideoItem", js)
        self.assertIn("data-next-action", js)
        self.assertIn("setupMediaProfileVolume", js)
        self.assertIn("video_volume_' + username", js)
        self.assertIn("/api/models/' + encodeURIComponent(username) + '/volume", js)
        self.assertIn("window.addEventListener('beforeunload', flushMediaProfileVolume)", js)
        self.assertNotIn("openUploadModal", js)
        self.assertNotIn("uploadMediaFiles", js)
        self.assertNotIn("/uploads", js)
        self.assertNotIn("<label>Channel<input", js)
        self.assertNotIn('data-source-field="channelUsername" type="text"', js)
        self.assertNotIn("profile.thumbnail", js)
        self.assertIn("unwatchedOnly", js)
        self.assertIn("params.set('watched', 'unwatched')", js)
        self.assertIn("params.set('metadata', 'lazy')", js)
        self.assertIn("toLocaleString('en-US'", js)
        self.assertIn("Unwatched videos", js)
        self.assertIn("Watched", js)
        self.assertIn(".media-unwatched-toggle", css)
        self.assertIn(".media-next-prompt", css)
        self.assertIn(".media-profile-menu-btn", css)
        self.assertNotIn(".media-profile-detail", css)
        self.assertNotIn(".media-upload-modal", css)
        self.assertNotIn("M&eacute;dia", header)
        self.assertNotIn("Non vues", html)
        self.assertNotIn("Videos non vues", js)
        self.assertNotIn("Deja vu", js)

    def test_watch_page_uses_set_recording_profile_flow(self):
        html = (ROOT / "static" / "watch.html").read_text()
        js = (ROOT / "static" / "watch.js").read_text()

        self.assertIn("Set recording", html)
        self.assertIn("recordingModal", html)
        self.assertIn("recordingProfileSearch", html)
        self.assertIn("Existing profile", html)
        self.assertIn("New profile", html)
        self.assertIn("/api/media-profiles/link-live", js)
        self.assertIn("openRecordingModal", js)
        self.assertIn("submitCreateRecordingProfile", js)
        self.assertNotIn("Auto-Record", html)
        self.assertNotIn("Auto-Record", js)
        self.assertNotIn("toggleAutoRecord", js)

    def test_recordings_page_redirects_to_media(self):
        main = (ROOT / "app" / "main.py").read_text()

        self.assertIn('@app.get("/recordings")', main)
        self.assertIn('RedirectResponse(url="/media", status_code=307)', main)
        self.assertNotIn('return FileResponse(str(STATIC_DIR / "recordings.html"))', main)

    def test_discover_preserves_filter_state_in_url(self):
        js = (ROOT / "static" / "discover.js").read_text()
        html = (ROOT / "static" / "discover.html").read_text()

        self.assertIn("function readDiscoverStateFromUrl", js)
        self.assertIn("function syncDiscoverStateToUrl", js)
        self.assertIn("applyDiscoverStateToControls", js)
        self.assertIn("window.history.replaceState", js)
        self.assertIn("window.addEventListener('popstate'", js)
        self.assertIn("discover.js?v=9", html)

    def test_provider_settings_has_account_controls_for_sync_capable_providers(self):
        js = (ROOT / "static" / "settings.js").read_text()
        css = (ROOT / "static" / "styles.css").read_text()

        self.assertIn("Import Session", js)
        self.assertIn("function importProviderSession", js)
        self.assertIn("loginProvider", js)
        self.assertIn("reconnectProvider", js)
        self.assertIn("provider-session-import", js)
        self.assertIn("provider-login", js)
        self.assertIn("supportsAccount = caps.can_login === true", js)
        self.assertIn("providerAccountControls(source, status, caps)", js)
        self.assertIn("data.trusted === false", js)
        self.assertIn("data.skippedReason || data.message || 'Following sync skipped'", js)
        self.assertIn(".provider-session-import", css)
        self.assertIn(".provider-login", css)

    def test_provider_settings_keeps_local_status_for_non_account_providers(self):
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertIn("supportsAccount ? providerStatusText(status) : 'Local'", js)
        self.assertIn("Live, recording and local follows", js)
        self.assertIn("Live, recording, remote sync and follow", js)
        self.assertIn("Credentials Saved", js)
        self.assertIn("Session Required", js)
        self.assertIn("Login Failed", js)
        self.assertIn("Saved credentials are stored", js)
        self.assertIn("automatic login was blocked", js)
        self.assertIn("Browser session data is saved", js)
        self.assertIn("function providerStatusNeedsSessionImport", js)
        self.assertIn("function providerStatusLoginFailed", js)
        self.assertIn("var canSync = connected && caps.can_sync_following === true", js)
        self.assertNotIn("function providerConnectionProviders(providers)", js)
        self.assertIn("No providers configured.", js)
        self.assertIn("Import a verified browser session", js)

    def test_provider_settings_lists_all_providers_with_capability_checks(self):
        js = (ROOT / "static" / "settings.js").read_text()
        css = (ROOT / "static" / "styles.css").read_text()
        html = (ROOT / "static" / "settings.html").read_text()

        self.assertIn("providers = providers || []", js)
        self.assertIn("function providerCapabilityChecks(caps)", js)
        self.assertIn("providerCapabilityCheck('Discover', !!caps.can_discover)", js)
        self.assertIn("providerCapabilityCheck('Record', !!caps.can_record)", js)
        self.assertIn("providerCapabilityCheck('Follow / Unfollow', !!caps.can_follow)", js)
        self.assertIn("providerCapabilityCheck('Sync', !!caps.can_sync_following)", js)
        self.assertIn("provider-capability-icon", js)
        self.assertIn("function providerEnabledControl", js)
        self.assertIn("function toggleProviderEnabled", js)
        self.assertIn("/api/providers/' + encodeURIComponent(source) + '/enabled", js)
        self.assertIn("provider-enabled-control", js)
        self.assertIn("&#10003;", js)
        self.assertIn("&#10005;", js)
        self.assertIn(".provider-capability-list", css)
        self.assertIn(".provider-capability-icon", css)
        self.assertIn(".provider-capability.is-enabled .provider-capability-icon", css)
        self.assertIn(".provider-capability.is-disabled .provider-capability-icon", css)
        self.assertIn(".provider-enabled-control", css)
        self.assertNotIn(".provider-capability:has(input:checked)", css)
        self.assertIn(".status-indicator.available", css)
        self.assertIn("<h3>Providers</h3>", html)

    def test_provider_settings_maps_login_error_codes(self):
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertNotIn("Automatic Stripchat account login failed;", js)
        self.assertIn("Automatic account login failed. Check credentials", js)
        self.assertIn("function providerStatusError", js)
        self.assertIn("providerConnectionError", js)

    def test_provider_settings_does_not_expose_removed_subscription_sources(self):
        js = (ROOT / "static" / "settings.js").read_text()

        self.assertNotIn("function headerValue", js)
        self.assertNotIn("function onlyFansPayloadFromObject", js)
        self.assertNotIn("onlyfans", js.lower())
        self.assertNotIn("manyvids", js.lower())
        self.assertNotIn("fansly", js.lower())
        self.assertIn("userAgent:", js)
        self.assertIn("providerSessionPayload", js)


if __name__ == "__main__":
    unittest.main()
