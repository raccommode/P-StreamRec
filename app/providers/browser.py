from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote_plus, unquote, urlencode, urljoin, urlparse

import aiohttp
from yarl import URL

from ..core.http_client import aiohttp_client_session, aiohttp_request_kwargs
from ..logger import logger
from ..services.flaresolverr import DEFAULT_FLARE_SERVICE_URL, DEFAULT_FLARE_TIMEOUT_MS
from .base import (
    BaseProvider,
    ProviderCapabilities,
    ProviderAuthError,
    ProviderError,
    ProviderInteractionRequired,
    ProviderOfflineError,
    ProviderPrivateError,
    ResolvedStream,
)
from .sessions import ProviderSessionStore


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
STRIPCHAT_BASE_URL = "https://stripchat.com"
STRIPCHAT_API_BASE = f"{STRIPCHAT_BASE_URL}/api/front"
STRIPCHAT_FRONT_VERSION = os.getenv("PSTREAMREC_STRIPCHAT_FRONT_VERSION", "11.7.28")
STRIPCHAT_LOGIN_PATHS = (
    "/auth/login",
    "/v3/auth/login",
    "/v2/auth/login",
    "/login",
)
STRIPCHAT_HLS_HOSTS = (
    "doppiocdn.net",
    "doppiocdn.com",
    "doppiocdn.org",
    "doppiocdn.live",
    "doppiocdn.media",
)
STRIPCHAT_PLAYBACK_KEY = os.getenv("PSTREAMREC_STRIPCHAT_PLAYBACK_KEY", "fncnu6utiWqsDLk8")
BONGACAMS_BASE_URL = "https://bongacams.com"
_MEDIA_URL_RE = re.compile(
    r"https?:\\?/\\?/[^\s\"'<>]+?\.(?:m3u8|mpd)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)
_HLS_URL_FIELD_RE = re.compile(
    r"""["']hlsUrl["']\s*:\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_INTERACTION_RE = re.compile(
    r"captcha|hcaptcha|recaptcha|turnstile|2fa|two-factor|cloudflare|cloudfront|request blocked|verify you are human",
    re.IGNORECASE,
)
_AUTH_REQUIRED_RE = re.compile(
    r"\b(log\s*in|login|sign\s*in|signin)\b|please\s+log\s+in|auth(?:entication)?\s+required",
    re.IGNORECASE,
)
_LOGIN_FAILED_RE = re.compile(
    r"invalid|incorrect|wrong|failed|try again|not recognized|not recognised|"
    r"could not log|unable to log|password.*required|username.*required",
    re.IGNORECASE,
)
_OFFLINE_RE = re.compile(r"offline|not currently online|not live|away", re.IGNORECASE)
_PRIVATE_RE = re.compile(r"private|ticket show|group show|premium", re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
_IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r"""([:\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_VIEWER_RE = re.compile(
    r"(?:(\d[\d,.\s]*(?:[kKmM])?)\s*(?:viewers?|watching|users?)|(?:viewers?|watching|users?)\D{0,24}(\d[\d,.\s]*(?:[kKmM])?))",
    re.IGNORECASE,
)
_VIEWER_KEY_RE = re.compile(
    r"""(?:
        ["']?(?:viewers?|viewerCount|viewer_count|numUsers|num_users|numViewers|watching)["']?\s*[:=]\s*["']?(\d[\d,.\s]*(?:[kKmM])?)["']?
        |
        data-(?:viewers?|viewer-count|num-users|watching)\s*=\s*["']?(\d[\d,.\s]*(?:[kKmM])?)["']?
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_VIEWER_DATA_COUNT_RE = re.compile(
    r"""data-count\s*=\s*["']?(\d[\d,.\s]*(?:[kKmM])?)["']?[^>]{0,160}(?:viewers?|watching|users?|connection)""",
    re.IGNORECASE,
)
_VIEWER_CLASS_RE = re.compile(
    r"""(?:viewers?|watching|connection)[^<]{0,120}>\s*(\d[\d,.\s]*(?:[kKmM])?)\s*<""",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"(?<![\w/])#([A-Za-z0-9][A-Za-z0-9_-]{1,47})")
_TAG_LINK_RE = re.compile(
    r"""href\s*=\s*["'][^"']*/(?:tag|tags|category|categories|hashtag|hashtags)/([^"'?#]+)""",
    re.IGNORECASE,
)
_TAG_FIELD_RE = re.compile(
    r"""["'](?:tags|hashtags|categories|keywords|interests)["']\s*:\s*(\[[^\]]{0,2500}\])""",
    re.IGNORECASE,
)
_TAG_ATTR_HINT_RE = re.compile(r"(?:^|[-_:])(tag|tags|category|categories|hashtag|hashtags|keyword|keywords|interest|interests)(?:$|[-_:])", re.IGNORECASE)
_TAG_SPLIT_RE = re.compile(r"[,;|]")
_GENERIC_TAG_STOPWORDS = {
    "account",
    "all",
    "chat",
    "free",
    "girl",
    "girls",
    "home",
    "html",
    "img",
    "live",
    "login",
    "medium",
    "model",
    "models",
    "online",
    "percent",
    "profile",
    "root",
    "search",
    "settings",
    "show",
    "shows",
    "signup",
    "standard",
    "store",
    "stream",
    "streams",
    "subscriptions",
    "video",
    "videos",
    "viewer",
    "viewers",
    "watching",
    "wrp",
    "cs_root",
    "livesnap",
    "livesnap parent",
    "livesnap1",
    "livesnap2",
}
_RESERVED_PROFILE_SEGMENTS = {
    "",
    "about",
    "account",
    "accounts",
    "2257",
    "all-models",
    "api",
    "become-a-model",
    "blog",
    "cams",
    "cam",
    "chat",
    "contact",
    "cookies-policy",
    "couple",
    "couples",
    "de",
    "dmca",
    "en",
    "es",
    "female",
    "fr",
    "girls",
    "help",
    "home",
    "hc",
    "it",
    "live",
    "login",
    "logout",
    "male",
    "members",
    "models",
    "my",
    "new",
    "online",
    "performers",
    "parental-control",
    "privacy",
    "privacy.php",
    "profile",
    "search",
    "settings",
    "sex-cam",
    "signup",
    "store",
    "subscriptions",
    "support",
    "terms",
    "tos",
    "trans",
    "transgender",
    "videos",
}


def _clean_media_url(value: str) -> str:
    cleaned = html.unescape(value)
    cleaned = cleaned.replace("\\/", "/").replace("\\u002F", "/").replace("\\u003D", "=")
    return cleaned.strip()


def extract_media_urls(text: str) -> list[str]:
    seen = set()
    out = []
    for match in _MEDIA_URL_RE.finditer(text or ""):
        url = _clean_media_url(match.group(0))
        if not _is_probable_media_url(url):
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def extract_hls_url_fields(text: str) -> list[str]:
    seen = set()
    out = []
    for match in _HLS_URL_FIELD_RE.finditer(text or ""):
        url = _clean_media_url(match.group(1))
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw or ""):
        key = (match.group(1) or "").lower()
        value = next((g for g in match.groups()[1:] if g is not None), "")
        if key:
            attrs[key] = html.unescape(value or "")
    return attrs


def _strip_html(value: str) -> str:
    text = _TAG_RE.sub(" ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _first_src(attrs: dict[str, str], base_url: str) -> Optional[str]:
    for key in ("data-src", "data-original", "data-lazy-src", "data-thumb", "src"):
        value = (attrs.get(key) or "").strip()
        if value:
            return urljoin(base_url, value)
    srcset = (attrs.get("srcset") or attrs.get("data-srcset") or "").strip()
    if srcset:
        first = srcset.split(",", 1)[0].strip().split(" ", 1)[0]
        if first:
            return urljoin(base_url, first)
    return None


def _first_image(fragment: str, base_url: str) -> Optional[str]:
    match = _IMG_RE.search(fragment or "")
    if not match:
        return None
    return _first_src(_parse_attrs(match.group("attrs")), base_url)


def _viewer_count(fragment: str) -> int:
    raw_fragment = html.unescape(fragment or "")
    data_count_match = _VIEWER_DATA_COUNT_RE.search(raw_fragment)
    if data_count_match:
        return _parse_count(data_count_match.group(1))
    key_match = _VIEWER_KEY_RE.search(raw_fragment)
    if key_match:
        return _parse_count(next((g for g in key_match.groups() if g), "0"))
    class_match = _VIEWER_CLASS_RE.search(raw_fragment)
    if class_match:
        return _parse_count(class_match.group(1))
    match = _VIEWER_RE.search(_strip_html(raw_fragment))
    if not match:
        return 0
    raw = next((g for g in match.groups() if g), "")
    return _parse_count(raw)


def _parse_count(raw: str) -> int:
    value = (raw or "").strip().lower().replace("\xa0", " ")
    match = re.search(r"(\d[\d,.\s]*)([km])?", value)
    if not match:
        return 0
    number = match.group(1).strip()
    suffix = match.group(2) or ""
    if suffix:
        number = number.replace(" ", "").replace(",", ".")
        try:
            parsed = float(number)
        except ValueError:
            return 0
        return int(parsed * (1000 if suffix == "k" else 1000000))
    digits = re.sub(r"[^\d]", "", number)
    return int(digits or 0)


def _normalize_tag(value: str) -> Optional[str]:
    tag = html.unescape(str(value or "")).strip().strip("#").strip()
    tag = re.sub(r"\s+", " ", tag)
    tag = tag.strip(".,;:!?()[]{}\"'")
    if not tag:
        return None
    lower = tag.lower()
    if lower in _GENERIC_TAG_STOPWORDS:
        return None
    if len(lower) < 2 or len(lower) > 48:
        return None
    if re.search(r"https?://|@|[<>/\\]", lower):
        return None
    if re.fullmatch(r"\d+", lower):
        return None
    return lower


def _normalize_tags(values: Iterable[object]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        tag = _normalize_tag(str(value or ""))
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= 12:
            break
    return out


def _extract_json_tags(text: str) -> list[str]:
    values: list[object] = []
    for match in _TAG_FIELD_RE.finditer(text or ""):
        raw = html.unescape(match.group(1))
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        for item in parsed:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                for key in ("name", "slug", "label", "title", "value"):
                    if item.get(key):
                        values.append(item[key])
                        break
    return _normalize_tags(values)


def _extract_tags(fragment: str, attrs: Optional[dict[str, str]] = None) -> list[str]:
    values: list[object] = []
    text = fragment or ""
    attrs = attrs or {}
    for key, value in attrs.items():
        if _TAG_ATTR_HINT_RE.search(key):
            values.extend(part.strip() for part in _TAG_SPLIT_RE.split(value or "") if part.strip())
        if key in {"data-gender", "gender", "data-type", "data-category", "category"} and value:
            values.append(value)
        if key == "class" and value:
            values.extend(_tag_values_from_classes(value))
    for attr_match in re.finditer(
        r"""(data-gender|gender|data-type|data-category|category|class)\s*=\s*["']([^"']+)["']""",
        text,
        re.IGNORECASE,
    ):
        key = attr_match.group(1).lower()
        value = attr_match.group(2)
        if key == "class":
            values.extend(_tag_values_from_classes(value))
        else:
            values.extend(part.strip() for part in _TAG_SPLIT_RE.split(value) if part.strip())
    for match in _TAG_LINK_RE.finditer(text):
        path = unquote(match.group(1)).strip("/")
        segment = next((part for part in reversed(path.split("/")) if part), "")
        if segment:
            values.append(segment.replace("-cams", "").replace("-", " "))
    values.extend(match.group(1) for match in _HASHTAG_RE.finditer(_strip_html(text)))
    values.extend(_extract_json_tags(text))
    return _normalize_tags(values)


def _tag_values_from_classes(value: str) -> list[str]:
    values: list[str] = []
    for token in re.split(r"\s+", value or ""):
        token = token.strip("_ ")
        if not token:
            continue
        flag_match = re.search(r"flag[_-]?([A-Z][A-Za-z]+)", token)
        if flag_match:
            token = flag_match.group(1)
        elif token.startswith("flag"):
            token = token.removeprefix("flag").strip("_- ")
            if not token or re.fullmatch(r"[\d_\-\s]+", token):
                continue
        elif token.startswith("badge"):
            token = re.sub(r"(?<!^)([A-Z])", r" \1", token)
        elif not token.startswith(("hd", "new", "live", "vibra", "private", "voyeur", "exclusive")):
            continue
        if token.startswith("livesnap"):
            continue
        token = token.replace("_", " ").replace("-", " ")
        values.append(token)
    return values


_SUBJECT_KEYWORDS = {
    "anal": ("anal",),
    "asian": ("asian",),
    "bbw": ("bbw",),
    "big ass": ("big ass", "big butt"),
    "big tits": ("big tits", "big boobs"),
    "blonde": ("blonde",),
    "blowjob": ("blowjob",),
    "bondage": ("bondage",),
    "brunette": ("brunette",),
    "c2c": ("c2c", "cam2cam", "cam to cam"),
    "cosplay": ("cosplay",),
    "cum": ("cum",),
    "curvy": ("curvy",),
    "dance": ("dance", "dancing"),
    "dildo": ("dildo",),
    "ebony": ("ebony",),
    "exclusive": ("exclusive",),
    "feet": ("feet", "foot fetish"),
    "femdom": ("femdom",),
    "fetish": ("fetish",),
    "gamer": ("gamer", "gaming"),
    "goth": ("goth",),
    "hd": (" hd ", "high definition"),
    "joi": ("joi",),
    "latina": ("latina",),
    "latex": ("latex",),
    "lesbian": ("lesbian",),
    "lovense": ("lovense",),
    "milf": ("milf",),
    "pvt": ("pvt", "private"),
    "redhead": ("redhead",),
    "roleplay": ("roleplay", "role play"),
    "snapchat": ("snapchat",),
    "squirt": ("squirt",),
    "striptease": ("striptease",),
    "tattoos": ("tattoo",),
    "teen": ("teen", "18+"),
    "toy": ("toy", "toys"),
    "trans": ("trans",),
    "vibrator": ("vibrator",),
    "voyeur": ("voyeur",),
}


def _subject_keyword_tags(value: str) -> list[str]:
    text = f" {_strip_html(value).lower()} "
    found: list[str] = []
    for tag, needles in _SUBJECT_KEYWORDS.items():
        if any(needle in text for needle in needles):
            found.append(tag)
    return _normalize_tags(found)


def _page_metadata(text: str, page_url: str = "") -> dict[str, object]:
    thumb = _first_image(text or "", page_url) if page_url else None
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.IGNORECASE | re.DOTALL)
    title = _strip_html(title_match.group(1)) if title_match else None
    return {
        "viewers": _viewer_count(text or ""),
        "tags": _extract_tags(text or ""),
        "thumbnail": thumb,
        "title": title,
    }


def _anchor_context(html_text: str, match: re.Match) -> str:
    start = match.start()
    end = match.end()
    before_markers = [
        r'<div\b[^>]*(?:data-position|data-profile|data-username|data-name|data-gender|class="[^"]*(?:ls_thumb|lst_wrp|ModelCard|model_online|result-module__item))',
        r"<article\b",
        r"<li\b",
    ]
    context_start = start
    prefix = html_text[max(0, start - 5000):start]
    for pattern in before_markers:
        found = list(re.finditer(pattern, prefix, re.IGNORECASE | re.DOTALL))
        if found:
            context_start = max(context_start - len(prefix) + found[-1].start(), 0)
            break

    suffix = html_text[end:end + 5000]
    context_end = end + len(suffix)
    for pattern in (
        r'<div\b[^>]*(?:data-position|data-profile|data-username|class="[^"]*(?:ls_thumb|ModelCard|model_online|result-module__item))',
        r'<div\b[^>]*(?:data-name|data-gender|class="[^"]*(?:lst_wrp))',
        r"<article\b",
        r"<li\b",
    ):
        next_match = re.search(pattern, suffix, re.IGNORECASE | re.DOTALL)
        if next_match and next_match.start() > 80:
            context_end = end + next_match.start()
            break

    return html_text[context_start:context_end]


def _best_thumbnail(fragment: str, attrs: dict[str, str], base_url: str) -> Optional[str]:
    for key in ("data-thumb-image", "data-thumbnail", "data-preview", "data-image"):
        value = (attrs.get(key) or "").strip()
        if value:
            return urljoin(base_url, value)
    thumb = _first_image(fragment, base_url)
    if thumb and not thumb.startswith("data:image/svg+xml"):
        return thumb
    return thumb


def _subject_from_context(context: str) -> str:
    for pattern in (
        r"""class\s*=\s*["'][^"']*(?:subject|headline|topic)[^"']*["'][^>]*>(.*?)<""",
        r"""headlineMessage["']?\s*[:=]\s*["']([^"']+)["']""",
    ):
        match = re.search(pattern, context or "", re.IGNORECASE | re.DOTALL)
        if match:
            return _strip_html(match.group(1))[:240]
    return ""


def _is_probable_media_url(value: str) -> bool:
    lower = (value or "").lower()
    if "/ping.m3u8" in lower:
        return False
    return ".m3u8" in lower or ".mpd" in lower


class BrowserCaptureProvider(BaseProvider):
    capabilities = ProviderCapabilities(can_follow=True, uses_browser=True)

    def __init__(
        self,
        source_type: str,
        display_name: str,
        url_templates: Iterable[str],
        domains: Iterable[str],
        session_store: Optional[ProviderSessionStore] = None,
        browser_root: Optional[Path] = None,
        login_templates: Optional[Iterable[str]] = None,
        discover_templates: Optional[Iterable[str]] = None,
        can_login: bool = False,
        can_remote_follow: Optional[bool] = None,
        can_stream: bool = True,
        can_record: bool = True,
    ):
        super().__init__(session_store=session_store)
        self.source_type = source_type
        self.display_name = display_name
        self.url_templates = tuple(url_templates)
        self.domains = tuple(domains)
        self.browser_root = Path(browser_root or "data/provider-browser")
        self.login_templates = tuple(login_templates or self.url_templates)
        self.discover_templates = tuple(discover_templates or ())
        self.capabilities = ProviderCapabilities(
            can_login=can_login,
            can_follow=True,
            can_sync_following=False,
            can_discover=bool(self.discover_templates),
            can_stream=can_stream,
            can_record=can_record,
            uses_browser=True,
        )
        self._discover_cache: dict[tuple, tuple[float, dict]] = {}

    def _browser_args(self) -> list[str]:
        return [
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-setuid-sandbox",
            "--lang=en-US,en",
            "--no-sandbox",
        ]

    def canonical_url(self, target: str) -> str:
        target = (target or "").strip()
        if target.startswith("http://") or target.startswith("https://"):
            return target
        if not self.url_templates:
            return target
        return self.url_templates[0].format(username=quote_plus(target))

    def candidate_urls(self, target: str) -> list[str]:
        target = (target or "").strip()
        if target.startswith("http://") or target.startswith("https://"):
            return [target]
        encoded = quote_plus(target)
        return [template.format(username=encoded) for template in self.url_templates]

    def discover_urls(
        self,
        page: int,
        search: Optional[str],
        gender: Optional[str],
        tags: Optional[list[str]],
    ) -> list[str]:
        search = (search or "").strip()
        gender = (gender or "").strip().lower()
        first_tag = (tags or [""])[0] if tags else ""
        values = {
            "query": quote_plus(search),
            "username": quote_plus(search),
            "gender": quote_plus(gender),
            "tag": quote_plus(first_tag),
            "page": max(1, int(page or 1)),
        }
        urls: list[str] = []
        for template in self.discover_templates:
            if "{query}" in template and not search:
                continue
            try:
                url = template.format(**values)
            except KeyError:
                continue
            if url not in urls:
                urls.append(url)
        if search:
            for url in self.candidate_urls(search):
                if url not in urls:
                    urls.append(url)
        return urls

    async def list_live_models(self, **kwargs) -> dict[str, object]:
        if not self.discover_templates:
            return await super().list_live_models(**kwargs)

        page = max(1, int(kwargs.get("page") or 1))
        limit = max(1, int(kwargs.get("limit") or 24))
        gender = kwargs.get("gender") or None
        search = (kwargs.get("search") or "").strip()
        tags = kwargs.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        tags = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
        allow_browser = bool(kwargs.get("allow_browser", False))
        exact_search_fallback = bool(kwargs.get("exact_search_fallback", False))
        cache_key = (page, limit, gender or "", search, tuple(tags), allow_browser)
        ttl = int(os.getenv("PSTREAMREC_DISCOVER_CACHE_TTL", "90") or "90")
        cached = self._discover_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < ttl:
            return dict(cached[1])

        if self.source_type == "stripchat":
            api_result = await self._stripchat_list_live_models_api(
                page=page,
                limit=limit,
                search=search,
                gender=gender,
                tags=tags,
            )
            if api_result is not None:
                self._discover_cache[cache_key] = (time.monotonic(), api_result)
                return dict(api_result)

        urls = self.discover_urls(page, search, gender, tags)
        items: list[dict[str, object]] = []
        for page_url in urls:
            html_text = await self._fetch_discover_html(page_url)
            if html_text:
                items.extend(self._parse_discover_models(html_text, page_url))

        if not items and allow_browser and urls:
            for page_url in urls[:2]:
                html_text = await self._fetch_discover_html_browser(page_url, search)
                if html_text:
                    items.extend(self._parse_discover_models(html_text, page_url))
                if items:
                    break

        if not items and search and exact_search_fallback:
            try:
                status = await self.check_status(search)
                if status.is_online:
                    items.append({
                        "username": search,
                        "display_name": search,
                        "thumbnail": status.thumbnail,
                        "viewers": status.viewers,
                        "subject": "",
                        "age": None,
                        "gender": "",
                        "is_online": True,
                        "tags": list(status.tags or []),
                        "room_status": status.room_status or "public",
                        "source_type": self.source_type,
                    })
            except Exception:
                pass

        items = self._dedupe_discover_models(items)
        if search:
            s = search.lower()
            items = [
                item for item in items
                if s in str(item.get("username") or "").lower()
                or s in str(item.get("display_name") or "").lower()
            ]
        if tags:
            items = [
                item for item in items
                if all(t in [str(x).lower() for x in (item.get("tags") or [])] for t in tags)
            ]

        items.sort(key=lambda item: int(item.get("viewers") or 0), reverse=True)
        total = len(items)
        total_pages = max(1, (total + limit - 1) // limit)
        start = (page - 1) * limit
        result = {
            "models": items[start:start + limit],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
        self._discover_cache[cache_key] = (time.monotonic(), result)
        return dict(result)

    async def resolve_stream(
        self, target: str, max_height: Optional[int] = None
    ) -> ResolvedStream:
        if self.source_type == "stripchat":
            stream = await self._resolve_stripchat_public_hls(target, max_height=max_height)
            if stream:
                return stream
        urls = self.candidate_urls(target)
        stream = await self._resolve_from_http(urls)
        if stream:
            return stream
        return await self._resolve_from_browser(urls, target)

    async def _resolve_from_http(self, urls: list[str]) -> Optional[ResolvedStream]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self.session_store:
            cookie_header = await self.session_store.cookie_header(self.source_type)
            if cookie_header:
                headers["Cookie"] = cookie_header

        timeout = aiohttp.ClientTimeout(total=20)
        for page_url in urls:
            try:
                async with aiohttp_client_session(timeout=timeout) as session:
                    async with session.get(
                        page_url,
                        headers=headers,
                        allow_redirects=True,
                        **aiohttp_request_kwargs(),
                    ) as resp:
                        text = await resp.text(errors="ignore")
                        if resp.status >= 500:
                            continue
                        meta = _page_metadata(text, str(resp.url))
                        media_urls = extract_media_urls(text)
                        if media_urls:
                            stream_url = media_urls[0]
                            return ResolvedStream(
                                url=stream_url,
                                headers=self._stream_headers(str(resp.url), headers.get("Cookie")),
                                source_type=self.source_type,
                                is_live=True,
                                room_status="public",
                                viewers=int(meta.get("viewers") or 0),
                                tags=list(meta.get("tags") or []),
                                thumbnail=meta.get("thumbnail") or None,
                                title=meta.get("title") or None,
                            )
                        if resp.status in (401, 403):
                            continue
            except Exception as exc:
                logger.debug(
                    "Provider HTTP probe failed",
                    source_type=self.source_type,
                    url=page_url,
                    error=str(exc),
                )
        return None

    async def _fetch_discover_html(self, page_url: str) -> str:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": page_url,
        }
        if self.session_store:
            cookie_header = await self.session_store.cookie_header(self.source_type)
            if cookie_header:
                headers["Cookie"] = cookie_header
        try:
            timeout = aiohttp.ClientTimeout(total=int(os.getenv("PSTREAMREC_DISCOVER_HTTP_TIMEOUT", "12") or "12"))
            async with aiohttp_client_session(timeout=timeout) as session:
                async with session.get(
                    page_url,
                    headers=headers,
                    allow_redirects=True,
                    **aiohttp_request_kwargs(),
                ) as resp:
                    if resp.status >= 500 or resp.status in (401, 403):
                        return ""
                    return await resp.text(errors="ignore")
        except Exception as exc:
            logger.debug(
                "Provider discover HTTP failed",
                source_type=self.source_type,
                url=page_url,
                error=str(exc),
            )
            return ""

    async def _fetch_discover_html_browser(self, page_url: str, search: str = "") -> str:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception:
            return ""

        timeout_seconds = int(os.getenv("PSTREAMREC_DISCOVER_BROWSER_TIMEOUT", "10") or "10")
        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        browser_user_agent = await self._stored_browser_user_agent()

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=browser_user_agent,
                viewport={"width": 1280, "height": 900},
                args=self._browser_args(),
            )
            try:
                await self._restore_cookies(context)
                page = context.pages[0] if context.pages else await context.new_page()
                json_payloads: list[str] = []
                capture_tasks: list[asyncio.Task] = []

                async def capture_json(response) -> None:
                    try:
                        headers = {k.lower(): v for k, v in response.headers.items()}
                        content_type = headers.get("content-type", "")
                        url = response.url
                        if "json" not in content_type and not re.search(
                            r"/(?:api|v\d+|ajax|models?|performers?|search|fallback)(?:[/?#]|$)",
                            url,
                            re.IGNORECASE,
                        ):
                            return
                        text = await response.text()
                        if not text or len(text) > 1500000:
                            return
                        stripped = text.lstrip()
                        if not stripped.startswith(("{", "[")):
                            return
                        json_payloads.append(
                            '<script type="application/json" data-pstreamrec-url="{}">{}</script>'.format(
                                html.escape(url, quote=True),
                                html.escape(text),
                            )
                        )
                    except Exception:
                        return

                def schedule_capture(response) -> None:
                    capture_tasks.append(asyncio.create_task(capture_json(response)))

                page.on("response", schedule_capture)
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                except PlaywrightTimeoutError:
                    pass
                except Exception as exc:
                    logger.debug(
                        "Provider discover browser navigation failed",
                        source_type=self.source_type,
                        url=page_url,
                        error=str(exc),
                    )
                    return ""
                await self._dismiss_common_prompts(page)
                if search:
                    await self._try_search(page, search)
                wait_ms = 5000 if self.source_type in {"myfreecams", "stripchat", "xcams"} else 1800
                await page.wait_for_timeout(wait_ms)
                if capture_tasks:
                    await asyncio.gather(*capture_tasks, return_exceptions=True)
                content = await page.content()
                if json_payloads:
                    content += "\n" + "\n".join(json_payloads)
                return content
            finally:
                await context.close()

    def _parse_discover_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        specialized_parser = {
            "camsoda": self._parse_camsoda_models,
            "cams": self._parse_cams_models,
            "livejasmin": self._parse_livejasmin_models,
            "myfreecams": self._parse_myfreecams_models,
            "stripchat": self._parse_stripchat_models,
            "xcams": self._parse_xcams_models,
        }.get(self.source_type)
        if specialized_parser:
            items.extend(specialized_parser(html_text, page_url))
            if items or self.source_type in {"camsoda", "cams", "livejasmin", "myfreecams", "xcams"}:
                return items
        for match in _ANCHOR_RE.finditer(html_text or ""):
            attrs = _parse_attrs(match.group("attrs"))
            href = attrs.get("href") or ""
            username = self._username_from_url(urljoin(page_url, href))
            if not username:
                continue
            body = match.group("body") or ""
            context = _anchor_context(html_text or "", match)
            context_attrs = {**_parse_attrs(context[:1200]), **attrs}
            display_name = (
                context_attrs.get("data-username")
                or context_attrs.get("data-profile")
                or context_attrs.get("data-name")
                or attrs.get("title")
                or attrs.get("aria-label")
                or _strip_html(body)
                or username
            )
            display_name = re.sub(r"\s+", " ", display_name).strip()
            if len(display_name) > 80 or display_name.lower() in _RESERVED_PROFILE_SEGMENTS:
                display_name = username
            thumbnail = _best_thumbnail(context or body, context_attrs, page_url)
            viewers = max(_viewer_count(body), _viewer_count(context))
            tags = _extract_tags(context or body, context_attrs)
            if not thumbnail and viewers <= 0:
                continue
            items.append({
                "username": username,
                "display_name": display_name,
                "thumbnail": thumbnail,
                "viewers": viewers,
                "subject": _subject_from_context(context),
                "age": None,
                "gender": "",
                "is_online": True,
                "tags": tags,
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    def _parse_stripchat_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        payloads = self._embedded_json_payloads(html_text)
        models: list[dict[str, object]] = []
        for payload in payloads:
            models.extend(self._stripchat_models_from_payload(payload))
        items = [item for model in models if (item := self._stripchat_model_item(model))]
        return self._dedupe_discover_models(items)

    def _stripchat_models_from_payload(self, payload: object) -> list[dict[str, object]]:
        models: list[dict[str, object]] = []
        if isinstance(payload, dict):
            profile_model = self._stripchat_profile_model(payload)
            if profile_model:
                models.append(profile_model)
            direct_models = payload.get("models")
            if isinstance(direct_models, list):
                models.extend(model for model in direct_models if isinstance(model, dict))
            for block in self._find_dicts_with_key(payload, "models"):
                block_models = block.get("models")
                if isinstance(block_models, list):
                    models.extend(model for model in block_models if isinstance(model, dict))
        elif isinstance(payload, list):
            models.extend(model for model in payload if isinstance(model, dict))
        return self._dedupe_stripchat_models(models)

    def _stripchat_profile_model(self, payload: dict[str, object]) -> Optional[dict[str, object]]:
        item = payload.get("item")
        if isinstance(item, dict) and item.get("username"):
            return dict(item)
        user_block = payload.get("user")
        if isinstance(user_block, dict):
            inner = user_block.get("user")
            if isinstance(inner, dict) and inner.get("username"):
                model = dict(inner)
                for key in ("isInFavorites", "tags", "lastTagsAliases", "tagGroups"):
                    if key in user_block:
                        model[key] = user_block[key]
                cam = payload.get("cam")
                if isinstance(cam, dict):
                    if cam.get("streamName"):
                        model["streamName"] = cam.get("streamName")
                    if cam.get("isCamAvailable") is not None:
                        model["isOnline"] = bool(cam.get("isCamAvailable"))
                return model
        return None

    def _dedupe_stripchat_models(self, models: list[dict[str, object]]) -> list[dict[str, object]]:
        by_key: dict[str, dict[str, object]] = {}
        for model in models:
            username = str(model.get("username") or model.get("login") or "").strip().lower()
            model_id = str(model.get("id") or model.get("streamName") or "").strip()
            key = username or model_id
            if not key:
                continue
            existing = by_key.get(key)
            if existing:
                for field, value in model.items():
                    if value not in (None, "", [], {}):
                        existing.setdefault(field, value)
                continue
            by_key[key] = dict(model)
        return list(by_key.values())

    def _stripchat_model_item(self, model: dict[str, object]) -> Optional[dict[str, object]]:
        username = str(model.get("username") or model.get("login") or "").strip()
        if not username:
            return None
        status = str(model.get("status") or "").lower()
        room_status = status if status and status != "public" else "public"
        try:
            viewers = int(model.get("viewersCount") or model.get("viewers") or model.get("usersCount") or 0)
        except (TypeError, ValueError):
            viewers = 0
        return {
            "username": username,
            "display_name": str(model.get("name") or username),
            "thumbnail": self._stripchat_thumbnail(model),
            "viewers": viewers,
            "subject": str(model.get("groupShowTopic") or model.get("offlineStatus") or ""),
            "age": model.get("age") if isinstance(model.get("age"), int) else None,
            "gender": str(model.get("genderGroup") or model.get("gender") or "").lower(),
            "is_online": bool(model.get("isOnline", model.get("isLive", status == "public"))),
            "tags": self._stripchat_tags(model),
            "room_status": room_status,
            "source_type": self.source_type,
        }

    def _stripchat_tags(self, model: dict[str, object]) -> list[str]:
        gender = str(model.get("gender") or model.get("broadcastGender") or model.get("genderGroup") or "").strip()
        gender_map = {
            "f": "female",
            "female": "female",
            "females": "female",
            "m": "male",
            "male": "male",
            "males": "male",
            "t": "trans",
            "trans": "trans",
            "femaleTranny": "trans",
            "tranny": "trans",
            "maleFemale": "couple",
            "group": "group",
        }
        values: list[object] = [gender_map.get(gender, gender)]
        broadcast_gender = str(model.get("broadcastGender") or "").strip()
        if broadcast_gender and broadcast_gender != gender:
            values.append(gender_map.get(broadcast_gender, broadcast_gender))
        country = str(model.get("country") or "").strip()
        if country:
            values.append(country)
        if model.get("isHd"):
            values.append("hd")
        if model.get("isVr"):
            values.append("vr")
        if model.get("isMobile"):
            values.append("mobile")
        if model.get("isNew"):
            values.append("new")
        if model.get("isLovense"):
            values.append("lovense")
        if model.get("isKiiroo"):
            values.append("kiiroo")
        if model.get("isNonNude"):
            values.append("non nude")
        if str(model.get("status") or "").lower() == "public":
            values.append("public")
        values.extend(_subject_keyword_tags(str(model.get("groupShowTopic") or "")))
        return _normalize_tags(values)

    def _stripchat_thumbnail(self, model: dict[str, object]) -> Optional[str]:
        model_id = str(model.get("id") or model.get("streamName") or "").strip()
        timestamp = str(model.get("snapshotTimestamp") or model.get("verifiedSnapshotTimestamp") or "").strip()
        if model_id and timestamp:
            return f"https://img.doppiocdn.net/snapshot/{model_id}/{timestamp}"
        for key in ("previewUrlThumbSmall", "previewUrlThumbBig", "previewUrl", "avatarUrl", "avatarUrlThumb"):
            value = str(model.get(key) or "").strip()
            if not value:
                continue
            if value.startswith(("http://", "https://")):
                return value
            if value.startswith("/"):
                return f"https://img.doppiocdn.net{value}"
        return None

    async def _stripchat_list_live_models_api(
        self,
        page: int,
        limit: int,
        gender: Optional[str],
        search: str,
        tags: list[str],
    ) -> Optional[dict[str, object]]:
        try:
            if search:
                profile = await self._stripchat_model_by_username(search)
                item = self._stripchat_model_item(profile)
                items = [item] if item and item.get("is_online") else []
                items = self._stripchat_filter_items(items, search="", tags=tags)
                return {
                    "models": items[:limit],
                    "total": len(items),
                    "page": page,
                    "limit": limit,
                    "total_pages": 1,
                }

            # Stripchat currently rejects values above 50 even though callers
            # may request larger catalogue pages.
            request_limit = min(max(limit, 24), 50)
            payload = await self._stripchat_api_json(
                "GET",
                "/v2/models",
                params={
                    "primaryTag": self._stripchat_primary_tag(gender, tags),
                    "limit": request_limit,
                    "offset": max(0, (page - 1) * limit),
                },
                referer=f"{STRIPCHAT_BASE_URL}/girls",
            )
        except Exception as exc:
            logger.debug("Stripchat public model API failed", error=str(exc))
            return None

        items = [item for model in self._stripchat_models_from_payload(payload) if (item := self._stripchat_model_item(model))]
        items = self._stripchat_filter_items(items, search=search, tags=tags)
        items.sort(key=lambda item: int(item.get("viewers") or 0), reverse=True)
        total = len(items)
        if isinstance(payload, dict) and not search and not tags:
            try:
                total = max(total, int(payload.get("totalCount") or 0))
            except (TypeError, ValueError):
                pass
        total_pages = max(1, (total + limit - 1) // limit)
        if search or tags:
            start = (page - 1) * limit
            page_items = items[start:start + limit]
        else:
            page_items = items[:limit]
        return {
            "models": page_items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }

    def _stripchat_filter_items(
        self,
        items: list[dict[str, object]],
        search: str = "",
        tags: Optional[list[str]] = None,
    ) -> list[dict[str, object]]:
        tags = [str(tag).lower() for tag in (tags or []) if str(tag).strip()]
        if search:
            lowered = search.lower()
            items = [
                item for item in items
                if lowered in str(item.get("username") or "").lower()
                or lowered in str(item.get("display_name") or "").lower()
            ]
        if tags:
            items = [
                item for item in items
                if all(tag in [str(value).lower() for value in (item.get("tags") or [])] for tag in tags)
            ]
        return items

    def _stripchat_primary_tag(self, gender: Optional[str], tags: list[str]) -> str:
        values = {str(gender or "").lower(), *(tag.lower() for tag in tags or [])}
        if values & {"male", "men", "man"}:
            return "men"
        if values & {"trans", "transgender", "tranny"}:
            return "trans"
        if values & {"couple", "couples", "group"}:
            return "couples"
        return "girls"

    def _parse_camsoda_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for match in re.finditer(
            r'<a\b(?P<attrs>[^>]*data-username\s*=\s*["\'][^"\']+["\'][^>]*)>(?P<body>.*?)(?=<a\b[^>]*data-username\s*=|</main>|<footer|\Z)',
            html_text or "",
            re.IGNORECASE | re.DOTALL,
        ):
            attrs = _parse_attrs(match.group("attrs"))
            username = (attrs.get("data-username") or "").strip()
            if not username:
                continue
            body = match.group("body") or ""
            subject = _subject_from_context(body)
            display_name_match = re.search(r"displayName[^>]*>(.*?)<", body, re.IGNORECASE | re.DOTALL)
            display_name = _strip_html(display_name_match.group(1)) if display_name_match else username
            tags = _normalize_tags(_extract_tags(match.group(0), attrs) + _subject_keyword_tags(subject) + ["female"])
            items.append({
                "username": username,
                "display_name": display_name or username,
                "thumbnail": _best_thumbnail(body, attrs, page_url),
                "viewers": _viewer_count(body),
                "subject": subject,
                "age": None,
                "gender": "female",
                "is_online": True,
                "tags": tags,
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    async def _provider_cookie_header(self) -> str:
        if not self.session_store:
            return ""
        try:
            return await self.session_store.cookie_header(self.source_type)
        except Exception:
            return ""

    async def _provider_session_state(self) -> dict[str, Any]:
        if not self.session_store:
            return {}
        try:
            return await self.session_store.get(self.source_type)
        except Exception:
            return {}

    async def _provider_session_username(self) -> Optional[str]:
        state = await self._provider_session_state()
        username = str(state.get("username") or state.get("credential_username") or "").strip()
        return username or None

    async def _provider_has_session(self) -> bool:
        state = await self._provider_session_state()
        return bool(state.get("cookies") or state.get("localStorage") or state.get("is_logged_in"))

    async def sync_following(self) -> list[dict[str, object]]:
        if self.source_type == "stripchat":
            return await self._stripchat_sync_following_http()
        if self.source_type == "bongacams":
            return await self._bongacams_sync_following()
        return await super().sync_following()

    async def follow(self, username: str) -> dict[str, object]:
        if self.source_type == "stripchat":
            try:
                return await self._stripchat_follow_http(username, follow=True)
            except ProviderAuthError:
                raise
            except ProviderError as exc:
                logger.debug("Stripchat HTTP follow failed", username=username, error=str(exc))
                try:
                    return await self._stripchat_browser_follow_action(username, follow=True)
                except ProviderAuthError:
                    raise
                except ProviderError as browser_exc:
                    return {"success": False, "error": str(browser_exc)}
        if self.source_type == "bongacams":
            return await self._bongacams_follow_action(username, follow=True)
        return await super().follow(username)

    async def unfollow(self, username: str) -> dict[str, object]:
        if self.source_type == "stripchat":
            try:
                return await self._stripchat_follow_http(username, follow=False)
            except ProviderAuthError:
                raise
            except ProviderError as exc:
                logger.debug("Stripchat HTTP unfollow failed", username=username, error=str(exc))
                try:
                    return await self._stripchat_browser_follow_action(username, follow=False)
                except ProviderAuthError:
                    raise
                except ProviderError as browser_exc:
                    return {"success": False, "error": str(browser_exc)}
        if self.source_type == "bongacams":
            return await self._bongacams_follow_action(username, follow=False)
        return await super().unfollow(username)

    async def is_following(self, username: str) -> bool:
        if self.source_type == "stripchat":
            try:
                payload = await self._stripchat_api_json(
                    "GET",
                    f"/v2/models/username/{quote_plus(username)}/cam",
                    auth_required=False,
                    referer=self.canonical_url(username),
                )
                value = self._stripchat_find_value(payload, {"isinfavorites"})
                if value is not None:
                    return bool(value)
            except Exception:
                pass
            try:
                items = await self.sync_following()
            except Exception:
                return False
            needle = username.strip().lower()
            return any(str(item.get("username") or "").lower() == needle for item in items)
        if self.source_type == "bongacams":
            if await self._local_provider_is_following(username):
                return True
            return await self._bongacams_is_following_browser(username)
        return await super().is_following(username)

    async def _local_provider_following(self) -> list[dict[str, object]]:
        db = getattr(self.session_store, "db", None) if self.session_store else None
        if not db or not hasattr(db, "get_all_followed"):
            return []
        rows = await db.get_all_followed()
        items: list[dict[str, object]] = []
        for row in rows or []:
            source_type = str(row.get("source_type") or "chaturbate").strip().lower()
            if source_type != self.source_type:
                continue
            username = str(row.get("username") or "").strip()
            if not username:
                continue
            items.append({
                "username": username,
                "display_name": row.get("display_name") or username,
                "thumbnail": row.get("thumbnail_url") or row.get("thumbnail"),
                "viewers": int(row.get("viewers") or 0),
                "is_online": bool(row.get("is_online")),
                "room_status": row.get("room_status"),
                "source_type": self.source_type,
            })
        return items

    async def _local_provider_is_following(self, username: str) -> bool:
        db = getattr(self.session_store, "db", None) if self.session_store else None
        if not db or not hasattr(db, "get_followed_model"):
            return False
        try:
            row = await db.get_followed_model(username, source_type=self.source_type)
        except TypeError:
            row = await db.get_followed_model(username)
        source_type = str((row or {}).get("source_type") or "chaturbate").strip().lower()
        return bool(row and source_type == self.source_type)

    async def _bongacams_sync_following(self) -> list[dict[str, object]]:
        return await self._local_provider_following()

    async def _bongacams_follow_action(self, username: str, follow: bool) -> dict[str, object]:
        username = (username or "").strip()
        if not username:
            return {"success": False, "error": "Username is required"}

        remote_required = os.getenv("PSTREAMREC_BONGACAMS_REMOTE_FOLLOW_REQUIRED", "").lower() in {"1", "true", "yes"}
        if await self._provider_has_session():
            try:
                return await self._bongacams_browser_follow_action(username, follow=follow)
            except ProviderError as exc:
                logger.debug(
                    "BongaCams remote follow action failed; keeping local follow state",
                    username=username,
                    follow=follow,
                    error=str(exc),
                )
                if remote_required:
                    return {"success": False, "error": str(exc)}
            except Exception as exc:
                logger.debug(
                    "BongaCams remote follow action crashed; keeping local follow state",
                    username=username,
                    follow=follow,
                    error=str(exc),
                )
                if remote_required:
                    return {"success": False, "error": str(exc)}

        return {
            "success": True,
            "localOnly": True,
            "provider": "bongacams",
            "username": username,
            "action": "follow" if follow else "unfollow",
        }

    async def _bongacams_is_following_browser(self, username: str) -> bool:
        if not await self._provider_has_session():
            return False
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception:
            return False

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        browser_user_agent = await self._stored_browser_user_agent()
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=browser_user_agent,
                viewport={"width": 1280, "height": 720},
                args=self._browser_args(),
            )
            try:
                await self._restore_cookies(context)
                page = context.pages[0] if context.pages else await context.new_page()
                try:
                    await page.goto(self.canonical_url(username), wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                await self._dismiss_common_prompts(page)
                if not await self._looks_logged_in(page, username=await self._provider_session_username()):
                    return False
                state = await self._bongacams_page_follow_state(page)
                return state is True
            finally:
                await context.close()

    async def _bongacams_browser_follow_action(self, username: str, follow: bool) -> dict[str, object]:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        session_username = await self._provider_session_username()

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 720},
                args=self._browser_args(),
            )
            try:
                await self._restore_cookies(context)
                page = context.pages[0] if context.pages else await context.new_page()
                try:
                    await page.goto(self.canonical_url(username), wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                await self._dismiss_common_prompts(page)
                if not await self._looks_logged_in(page, username=session_username):
                    raise ProviderAuthError("Connexion BongaCams requise")

                current_state = await self._bongacams_page_follow_state(page)
                if current_state is follow:
                    await self._save_browser_state(context, session_username, is_logged_in=True)
                    return {"success": True, "remote": True, "provider": "bongacams", "username": username}

                clicked = await self._bongacams_click_follow_button(page, follow=follow)
                if not clicked:
                    raise ProviderError("Bouton follow BongaCams introuvable")

                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    await page.wait_for_timeout(500)
                    state = await self._bongacams_page_follow_state(page)
                    if state is follow:
                        await self._save_browser_state(context, session_username, is_logged_in=True)
                        return {"success": True, "remote": True, "provider": "bongacams", "username": username}

                await self._save_browser_state(context, session_username, is_logged_in=True)
                return {"success": True, "remote": True, "provider": "bongacams", "username": username}
            finally:
                await context.close()

    async def _bongacams_page_follow_state(self, page) -> Optional[bool]:
        try:
            return await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    };
                    const controls = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]'))
                        .filter((el) => visible(el) && !el.disabled);
                    for (const el of controls) {
                        const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim().toLowerCase();
                        if (!text) continue;
                        if (/\\b(unfollow|following|favorited|remove from favorites?)\\b/.test(text)) return true;
                        if (/\\b(follow|favorite|add to favorites?)\\b/.test(text)) return false;
                    }
                    return null;
                }
                """
            )
        except Exception:
            return None

    async def _bongacams_click_follow_button(self, page, follow: bool) -> bool:
        pattern = (
            re.compile(r"^(follow|favorite|add to favorites?)$", re.IGNORECASE)
            if follow
            else re.compile(r"^(unfollow|following|favorited|remove from favorites?)$", re.IGNORECASE)
        )
        for role in ("button", "link"):
            try:
                locator = page.get_by_role(role, name=pattern)
                count = min(await locator.count(), 3)
                for idx in range(count):
                    try:
                        await locator.nth(idx).click(timeout=1500)
                        return True
                    except Exception:
                        pass
            except Exception:
                pass
        return False

    def _normalize_playwright_cookie(self, cookie: dict[str, Any], default_url: Optional[str] = None) -> Optional[dict[str, Any]]:
        name = str(cookie.get("name") or "").strip()
        if not name:
            return None
        normalized: dict[str, Any] = {
            "name": name,
            "value": str(cookie.get("value") or ""),
            "path": str(cookie.get("path") or "/"),
        }
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            normalized["domain"] = domain
        else:
            url = str(cookie.get("url") or default_url or "").strip()
            if url:
                normalized["url"] = url
            else:
                return None
        expires = cookie.get("expires", cookie.get("expiry"))
        if isinstance(expires, (int, float)) and expires > 0:
            normalized["expires"] = int(expires)
        for key in ("httpOnly", "secure"):
            if key in cookie:
                normalized[key] = bool(cookie.get(key))
        same_site = str(cookie.get("sameSite") or "").strip()
        same_site_map = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
            "no_restriction": "None",
            "unspecified": "Lax",
        }
        if same_site.lower() in same_site_map:
            normalized["sameSite"] = same_site_map[same_site.lower()]
        return normalized

    def _merge_cookies(self, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for cookie in existing + incoming:
            if not isinstance(cookie, dict):
                continue
            normalized = self._normalize_playwright_cookie(cookie)
            if not normalized:
                continue
            key = (
                str(normalized.get("name") or ""),
                str(normalized.get("domain") or normalized.get("url") or ""),
                str(normalized.get("path") or "/"),
            )
            merged[key] = normalized
        return list(merged.values())

    def _default_cookie_url(self) -> str:
        if self.source_type == "bongacams":
            return BONGACAMS_BASE_URL
        if self.url_templates:
            template = self.url_templates[0]
            return template.format(username="")
        return "https://" + (self.domains[0] if self.domains else "localhost")

    def _default_cookie_domain(self) -> str:
        host = urlparse(self._default_cookie_url()).netloc.lower()
        return f".{host.removeprefix('www.')}" if host else ""

    def _cookie_header_to_playwright_cookies(self, cookie_header: str) -> list[dict[str, Any]]:
        cookie_header = self._header_value(cookie_header, "cookie") or (cookie_header or "")
        domain = self._default_cookie_domain()
        if not domain:
            return []
        ignored_names = {
            "domain",
            "path",
            "expires",
            "max-age",
            "samesite",
            "secure",
            "httponly",
        }
        cookies: list[dict[str, Any]] = []
        for part in (cookie_header or "").split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name = name.strip()
            if not name or name.lower() in ignored_names:
                continue
            normalized = self._normalize_playwright_cookie({
                "name": name,
                "value": value.strip(),
                "domain": domain,
                "path": "/",
                "sameSite": "Lax",
                "secure": True,
            })
            if normalized:
                cookies.append(normalized)
        return cookies

    def _header_value(self, raw: str, name: str) -> str:
        wanted = (name or "").strip().lower()
        for line in (raw or "").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip().lower() == wanted:
                return value.strip()
        return ""

    def _cookie_value(self, cookies: list[dict[str, Any]], name: str) -> str:
        wanted = (name or "").strip().lower()
        for cookie in cookies or []:
            if not isinstance(cookie, dict):
                continue
            if str(cookie.get("name") or "").strip().lower() == wanted:
                return str(cookie.get("value") or "").strip()
        return ""

    def _provider_metadata_from_storage(self, local_storage: list[dict[str, Any]]) -> dict[str, str]:
        for entry in local_storage or []:
            if not isinstance(entry, dict) or entry.get("origin") != "pstreamrec://provider":
                continue
            metadata: dict[str, str] = {}
            for item in entry.get("localStorage") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "").strip()
                if name and value:
                    metadata[name] = value
            return metadata
        return {}

    def _merge_provider_metadata_storage(
        self,
        local_storage: list[dict[str, Any]],
        metadata: dict[str, str],
    ) -> list[dict[str, Any]]:
        cleaned = [
            entry
            for entry in (local_storage or [])
            if not (isinstance(entry, dict) and entry.get("origin") == "pstreamrec://provider")
        ]
        values = [
            {"name": name, "value": value}
            for name, value in metadata.items()
            if value
        ]
        if values:
            cleaned.append({"origin": "pstreamrec://provider", "localStorage": values})
        return cleaned

    async def _stored_browser_user_agent(self) -> str:
        state = await self._provider_session_state()
        metadata = self._provider_metadata_from_storage(list(state.get("localStorage") or []))
        return metadata.get("userAgent") or DEFAULT_USER_AGENT

    def _session_check_url(self, username: Optional[str] = None) -> str:
        if username:
            return self.canonical_url(username)
        if self.source_type == "bongacams":
            return BONGACAMS_BASE_URL
        return self._default_cookie_url()

    async def import_session(
        self,
        username: Optional[str] = None,
        cookie_header: Optional[str] = None,
        cookies: Optional[list[dict[str, Any]]] = None,
        local_storage: Optional[list[dict[str, Any]]] = None,
        user_agent: Optional[str] = None,
        x_bc: Optional[str] = None,
    ) -> dict[str, object]:
        username = (username or "").strip() or await self._provider_session_username()
        raw_cookie_header = cookie_header or ""
        check_url = self._session_check_url(username)
        incoming = self._cookie_header_to_playwright_cookies(raw_cookie_header)
        incoming.extend(
            normalized
            for cookie in (cookies or [])
            if isinstance(cookie, dict)
            for normalized in [self._normalize_playwright_cookie(cookie, default_url=check_url)]
            if normalized
        )
        state = await self._provider_session_state()
        merged = self._merge_cookies(list(state.get("cookies") or []), incoming)
        storage = local_storage if local_storage is not None else list(state.get("localStorage") or [])
        if not incoming:
            return {"success": False, "error": "No session cookies provided"}
        logged_in = await self._verify_imported_session(
            username=username,
            cookies=merged,
            local_storage=storage,
            check_url=check_url,
        )
        if logged_in:
            return {"success": True, "username": username, "importedSession": True}
        return {
            "success": False,
            "error": "Session cookies were saved but did not authenticate the provider",
            "importedSession": True,
        }

    async def _verify_imported_session(
        self,
        username: Optional[str],
        cookies: list[dict[str, Any]],
        local_storage: list[dict[str, Any]],
        check_url: str,
    ) -> bool:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 720},
                args=self._browser_args(),
            )
            try:
                await self._apply_browser_stealth(context)
                try:
                    await context.add_cookies(cookies)
                except Exception as exc:
                    raise ProviderError("Session cookies invalides") from exc
                if local_storage:
                    try:
                        await context.add_init_script(
                            """
                            (() => {
                                const origins = __PSTREAMREC_ORIGINS__;
                                const originState = origins.find((entry) => entry && entry.origin === window.location.origin);
                                if (!originState || !Array.isArray(originState.localStorage)) return;
                                for (const item of originState.localStorage) {
                                    if (!item || !item.name || typeof item.value !== 'string') continue;
                                    try { window.localStorage.setItem(item.name, item.value); } catch {}
                                }
                            })();
                            """.replace("__PSTREAMREC_ORIGINS__", json.dumps(local_storage))
                        )
                    except Exception:
                        pass
                page = context.pages[0] if context.pages else await context.new_page()
                try:
                    await page.goto(check_url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                await self._dismiss_common_prompts(page)
                await page.wait_for_timeout(1500)
                logged_in = await self._looks_logged_in(page, username=username)
                await self._save_browser_state(
                    context,
                    username,
                    is_logged_in=logged_in,
                    last_error=None if logged_in else "auth_required",
                )
                return logged_in
            finally:
                await context.close()

    async def _refresh_flaresolverr_cookies(
        self,
        page_url: str,
        username: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        flaresolverr_url = DEFAULT_FLARE_SERVICE_URL
        if self.session_store:
            try:
                saved_url = await self.session_store.db.get_setting("flaresolverr_url")
                if saved_url:
                    parsed = urlparse(saved_url)
                    if parsed.scheme in {"http", "https"} and parsed.netloc:
                        flaresolverr_url = saved_url.strip().rstrip("/")
            except Exception:
                flaresolverr_url = DEFAULT_FLARE_SERVICE_URL
        if not flaresolverr_url:
            return [], None

        payload = {
            "cmd": "request.get",
            "url": page_url,
            "maxTimeout": DEFAULT_FLARE_TIMEOUT_MS,
        }
        endpoint = flaresolverr_url.rstrip("/") + "/v1"
        try:
            timeout = aiohttp.ClientTimeout(total=max(10, payload["maxTimeout"] / 1000 + 5))
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.post(endpoint, json=payload) as resp:
                    data = await resp.json(content_type=None)
        except Exception as exc:
            logger.debug("FlareSolverr cookie refresh failed", source_type=self.source_type, url=page_url, error=str(exc))
            return [], None

        if data.get("status") != "ok":
            logger.debug("FlareSolverr cookie refresh rejected", source_type=self.source_type, response=data.get("message"))
            return [], None

        solution = data.get("solution") or {}
        raw_cookies = solution.get("cookies") or []
        cookies = [
            normalized
            for cookie in raw_cookies
            if isinstance(cookie, dict)
            for normalized in [self._normalize_playwright_cookie(cookie, default_url=page_url)]
            if normalized
        ]
        user_agent = str(solution.get("userAgent") or "").strip() or None
        if not cookies:
            return [], user_agent

        if self.session_store:
            state = await self._provider_session_state()
            merged = self._merge_cookies(list(state.get("cookies") or []), cookies)
            await self.session_store.save(
                self.source_type,
                username=username or state.get("username") or state.get("credential_username"),
                is_logged_in=bool(state.get("is_logged_in")),
                cookies=merged,
                local_storage=state.get("localStorage") or [],
                last_error=state.get("last_error"),
            )
        return cookies, user_agent

    async def _stripchat_sync_following_http(self) -> list[dict[str, object]]:
        if not await self._stripchat_has_session():
            raise ProviderAuthError("Connexion Stripchat requise pour synchroniser les favoris")

        models: list[dict[str, object]] = []
        page_limit = max(1, min(100, int(os.getenv("PSTREAMREC_STRIPCHAT_FAVORITES_LIMIT", "50") or "50")))
        max_pages = max(1, int(os.getenv("PSTREAMREC_STRIPCHAT_FAVORITES_MAX_PAGES", "20") or "20"))
        for path in ("/models/favorites", "/models/favorites/offline"):
            offset = 0
            for _ in range(max_pages):
                payload = await self._stripchat_api_json(
                    "GET",
                    path,
                    params={"limit": page_limit, "offset": offset},
                    auth_required=True,
                    referer=f"{STRIPCHAT_BASE_URL}/favorites",
                )
                page_models = self._stripchat_models_from_payload(payload)
                models.extend(page_models)
                total = int(payload.get("totalCount") or len(page_models)) if isinstance(payload, dict) else len(page_models)
                if len(page_models) < page_limit or offset + page_limit >= total:
                    break
                offset += page_limit

        items = [
            item
            for item in (self._stripchat_model_item(model) for model in self._dedupe_stripchat_models(models))
            if item
        ]
        items.sort(key=lambda item: (not bool(item.get("is_online")), -int(item.get("viewers") or 0), str(item.get("username") or "").lower()))
        return items

    async def _stripchat_follow_http(self, username: str, follow: bool) -> dict[str, object]:
        if not await self._stripchat_has_session():
            raise ProviderAuthError("Connexion Stripchat requise")
        model = await self._stripchat_model_by_username(username)
        model_id = self._stripchat_model_id(model)
        if not model_id:
            raise ProviderError(f"Modele Stripchat introuvable: {username}")
        current_user_id = await self._stripchat_current_user_id()
        if not current_user_id:
            raise ProviderAuthError("Utilisateur Stripchat connecte introuvable")

        if follow:
            await self._stripchat_api_json(
                "PUT",
                f"/users/{current_user_id}/favorites/{model_id}",
                body={"uniq": int(time.time() * 1000)},
                auth_required=True,
                referer=self.canonical_url(username),
            )
        else:
            await self._stripchat_api_json(
                "DELETE",
                f"/users/{current_user_id}/favorites",
                body={"favoriteIds": [int(model_id)], "uniq": int(time.time() * 1000)},
                auth_required=True,
                referer=self.canonical_url(username),
            )
        return {"success": True, "remote": True, "provider": "stripchat", "username": username}

    async def _stripchat_model_by_username(self, username: str) -> dict[str, object]:
        payload = await self._stripchat_api_json(
            "GET",
            f"/v2/models/username/{quote_plus(username)}/cam",
            auth_required=False,
            referer=self.canonical_url(username),
        )
        model = self._stripchat_profile_model(payload)
        if model:
            return model
        payload = await self._stripchat_api_json(
            "GET",
            f"/v2/users/username/{quote_plus(username)}",
            auth_required=False,
            referer=self.canonical_url(username),
        )
        model = self._stripchat_profile_model(payload)
        if model:
            return model
        raise ProviderError(f"Modele Stripchat introuvable: {username}")

    async def _resolve_stripchat_public_hls(
        self,
        target: str,
        max_height: Optional[int] = None,
    ) -> Optional[ResolvedStream]:
        username = self._stripchat_username_from_target(target)
        if not username:
            return None

        page_url = self.canonical_url(username)
        payload = await self._stripchat_api_json(
            "GET",
            f"/v2/models/username/{quote_plus(username)}/cam",
            auth_required=False,
            referer=page_url,
        )
        model = self._stripchat_profile_model(payload) if isinstance(payload, dict) else None
        if not model:
            raise ProviderOfflineError(f"Modele Stripchat introuvable ou hors ligne: {username}")

        self._validate_stripchat_public_stream(payload, model, username)
        stream_name = self._stripchat_stream_name(payload, model)
        if not stream_name:
            raise ProviderOfflineError(f"Flux Stripchat introuvable: {username}")

        headers = self._stream_headers(page_url, await self._provider_cookie_header())
        hosts = self._stripchat_hls_hosts_from_payload(payload) or list(STRIPCHAT_HLS_HOSTS)
        is_vr = self._stripchat_is_vr(payload, model)
        for host in hosts:
            playlist_urls = []
            if is_vr:
                playlist_urls.append(self._stripchat_master_playlist_url(host, stream_name, vr=True))
            playlist_urls.append(self._stripchat_master_playlist_url(host, stream_name))
            for playlist_url in playlist_urls:
                stream_url = await self._stripchat_validated_hls_url(playlist_url, headers, max_height)
                if stream_url:
                    item = self._stripchat_model_item(model) or {}
                    tags = list(item.get("tags") or [])
                    if is_vr and "vr" not in tags:
                        tags.append("vr")
                    return ResolvedStream(
                        url=stream_url,
                        headers=headers,
                        source_type=self.source_type,
                        is_live=True,
                        room_status="public",
                        viewers=int(item.get("viewers") or 0),
                        tags=tags,
                        thumbnail=item.get("thumbnail") or None,
                        title=str(item.get("display_name") or username),
                    )

        raise ProviderOfflineError(f"Aucun HLS Stripchat public valide pour {username}")

    async def _stripchat_validated_hls_url(
        self,
        playlist_url: str,
        headers: dict[str, str],
        max_height: Optional[int],
    ) -> Optional[str]:
        if not max_height or max_height <= 0:
            return playlist_url if await self._stripchat_probe_hls_playlist(playlist_url, headers) else None

        playlist_text = await self._stripchat_fetch_hls_playlist(playlist_url, headers)
        if not playlist_text:
            return None
        return self._stripchat_variant_url_for_height(playlist_url, playlist_text, max_height) or playlist_url

    @staticmethod
    def _stripchat_variant_url_for_height(
        playlist_url: str,
        playlist_text: str,
        max_height: Optional[int],
    ) -> Optional[str]:
        if not max_height or max_height <= 0:
            return None

        variants: list[dict[str, object]] = []
        pending_quality_height = 0
        for raw_line in (playlist_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#EXT-X-STREAM-INF"):
                match = re.search(r"RESOLUTION=(\d+)x(\d+)", line, re.IGNORECASE)
                pending_quality_height = min(int(match.group(1)), int(match.group(2))) if match else 0
                continue
            if line.startswith("#"):
                continue
            if pending_quality_height:
                variants.append({
                    # Quality settings refer to the shorter picture dimension:
                    # 720p is 1280x720 in landscape and 720x960 in portrait.
                    "height": pending_quality_height,
                    "url": urljoin(playlist_url, line),
                })
            pending_quality_height = 0

        if not variants:
            return None

        eligible = [item for item in variants if int(item["height"]) <= max_height]
        if eligible:
            selected = max(eligible, key=lambda item: int(item["height"]))
        else:
            selected = min(variants, key=lambda item: int(item["height"]))
        return str(selected["url"])

    def _stripchat_master_playlist_query(self) -> str:
        params = {
            "minHeight": os.getenv("PSTREAMREC_STRIPCHAT_MIN_HEIGHT", "240"),
            "playlistType": os.getenv("PSTREAMREC_STRIPCHAT_PLAYLIST_TYPE", "standard"),
        }
        playback_key = (os.getenv("PSTREAMREC_STRIPCHAT_PLAYBACK_KEY", STRIPCHAT_PLAYBACK_KEY) or "").strip()
        if playback_key:
            params["pkey"] = playback_key
        return "?" + urlencode(params)

    def _stripchat_username_from_target(self, target: str) -> Optional[str]:
        target = (target or "").strip().strip("@/ ")
        if target.startswith(("http://", "https://")):
            return self._username_from_url(target)
        if not re.match(r"^[A-Za-z0-9_.-]{2,64}$", target):
            return None
        if target.lower() in _RESERVED_PROFILE_SEGMENTS:
            return None
        return target

    def _validate_stripchat_public_stream(
        self,
        payload: object,
        model: dict[str, object],
        username: str,
    ) -> None:
        if self._stripchat_login_requires_interaction(payload):
            raise ProviderInteractionRequired("Stripchat demande une verification interactive")

        cam = payload.get("cam") if isinstance(payload, dict) and isinstance(payload.get("cam"), dict) else {}
        private_indicators = (
            cam.get("show"),
            cam.get("privateMode"),
            cam.get("groupShowAnnouncement"),
            cam.get("ticketShow"),
            cam.get("ticketShowAnnouncement"),
            cam.get("privateShow"),
        )
        if any(self._stripchat_truthy_indicator(value) for value in private_indicators):
            raise ProviderPrivateError(f"Stripchat/{username}: show prive, groupe ou ticket")

        for value in (model.get("status"), cam.get("streamStatus"), cam.get("status")):
            status = str(value or "").strip().lower()
            if not status:
                continue
            if any(marker in status for marker in ("private", "group", "ticket", "premium", "spy", "p2p")):
                raise ProviderPrivateError(f"Stripchat/{username}: show prive, groupe ou ticket")
            if status in {"offline", "away", "idle", "inactive", "not_live", "not live"}:
                raise ProviderOfflineError(f"Stripchat/{username}: modele hors ligne")

        if cam.get("isCamAvailable") is False or cam.get("isCamActive") is False:
            raise ProviderOfflineError(f"Stripchat/{username}: modele hors ligne")
        if model.get("isOnline") is False or model.get("isLive") is False:
            raise ProviderOfflineError(f"Stripchat/{username}: modele hors ligne")

    def _stripchat_truthy_indicator(self, value: object) -> bool:
        if value in (None, False, "", [], {}):
            return False
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "none", "null", "no", "off"}
        return bool(value)

    def _stripchat_hls_hosts_from_payload(self, payload: object) -> list[str]:
        values: list[str] = []

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    key_lower = str(key).lower()
                    if key_lower == "hlsstreamhost" and child:
                        values.append(str(child))
                    elif key_lower == "fallbackdomains" and isinstance(child, list):
                        values.extend(str(item) for item in child if item)
                    else:
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        hosts: list[str] = []
        seen = set()
        for value in values:
            host = str(value or "").strip().strip("/")
            if not host or host in seen:
                continue
            seen.add(host)
            hosts.append(host)
        return hosts

    async def _stripchat_fetch_hls_playlist(self, playlist_url: str, headers: dict[str, str]) -> Optional[str]:
        try:
            timeout = aiohttp.ClientTimeout(total=int(os.getenv("PSTREAMREC_STRIPCHAT_HLS_PROBE_TIMEOUT", "12") or "12"))
            async with aiohttp_client_session(timeout=timeout) as session:
                async with session.get(
                    playlist_url,
                    headers=headers,
                    allow_redirects=True,
                    **aiohttp_request_kwargs(),
                ) as resp:
                    if resp.status in (401, 403):
                        raise ProviderAuthError("Flux Stripchat refuse ou session requise")
                    if resp.status >= 400:
                        return None
                    text = await resp.text(errors="ignore")
        except ProviderError:
            raise
        except Exception as exc:
            logger.debug("Stripchat HLS probe failed", url=playlist_url, error=str(exc))
            return None
        return text if text.lstrip().startswith("#EXTM3U") else None

    async def _stripchat_probe_hls_playlist(self, playlist_url: str, headers: dict[str, str]) -> bool:
        return bool(await self._stripchat_fetch_hls_playlist(playlist_url, headers))

    async def _stripchat_user_by_username(self, username: str) -> dict[str, object]:
        payload = await self._stripchat_api_json(
            "GET",
            f"/v2/users/username/{quote_plus(username)}",
            auth_required=True,
            referer=STRIPCHAT_BASE_URL,
        )
        model = self._stripchat_profile_model(payload)
        if model:
            return model
        raise ProviderAuthError("Utilisateur Stripchat connecte introuvable")

    async def _stripchat_current_user_id(self) -> Optional[int]:
        state = await self._stripchat_session_state()
        saved_username = self._stripchat_saved_username(state)
        local_id = self._stripchat_find_user_id(state.get("localStorage"), saved_username)
        if local_id:
            return local_id
        if saved_username:
            user = await self._stripchat_user_by_username(saved_username)
            model_id = self._stripchat_model_id(user)
            if model_id:
                try:
                    return int(model_id)
                except (TypeError, ValueError):
                    return None
        return None

    def _stripchat_model_id(self, model: dict[str, object]) -> str:
        return str(model.get("id") or model.get("streamName") or "").strip()

    def _stripchat_stream_name(
        self,
        payload: object,
        model: dict[str, object],
    ) -> str:
        cam = payload.get("cam") if isinstance(payload, dict) and isinstance(payload.get("cam"), dict) else {}
        return str(cam.get("streamName") or model.get("streamName") or self._stripchat_model_id(model)).strip()

    def _stripchat_is_vr(
        self,
        payload: object,
        model: dict[str, object],
    ) -> bool:
        cam = payload.get("cam") if isinstance(payload, dict) and isinstance(payload.get("cam"), dict) else {}
        broadcast_settings = cam.get("broadcastSettings") if isinstance(cam.get("broadcastSettings"), dict) else {}
        payload_settings = payload.get("broadcastSettings") if isinstance(payload, dict) and isinstance(payload.get("broadcastSettings"), dict) else {}
        indicators = (
            model.get("isVr"),
            model.get("vr"),
            cam.get("isVr"),
            cam.get("vr"),
            cam.get("vrCameraSettings"),
            broadcast_settings.get("vrCameraSettings"),
            payload_settings.get("vrCameraSettings"),
        )
        return any(self._stripchat_truthy_indicator(value) for value in indicators)

    def _stripchat_master_playlist_url(self, host: str, stream_name: str, vr: bool = False) -> str:
        if vr:
            vr_name = f"{stream_name}_vr"
            return f"https://edge-hls.{host}/hls/{vr_name}/master/{vr_name}.m3u8"
        return (
            f"https://edge-hls.{host}/hls/{stream_name}/master/{stream_name}_auto.m3u8"
            f"{self._stripchat_master_playlist_query()}"
        )

    def _stripchat_front_version(self) -> str:
        return (os.getenv("PSTREAMREC_STRIPCHAT_FRONT_VERSION") or STRIPCHAT_FRONT_VERSION).strip() or STRIPCHAT_FRONT_VERSION

    def _stripchat_login_paths(self) -> tuple[str, ...]:
        raw = (os.getenv("PSTREAMREC_STRIPCHAT_LOGIN_PATHS") or "").strip()
        if not raw:
            return STRIPCHAT_LOGIN_PATHS
        paths = tuple(part.strip() for part in raw.split(",") if part.strip())
        return paths or STRIPCHAT_LOGIN_PATHS

    def _stripchat_login_payloads(
        self,
        username: str,
        password: str,
        seed: dict[str, object],
    ) -> list[dict[str, object]]:
        uniq = int(time.time() * 1000)
        base: dict[str, object] = {
            "loginOrEmail": username,
            "password": password,
            "uniq": uniq,
        }
        csrf_token = str(seed.get("csrfToken") or seed.get("csrf_token") or "").strip()
        if csrf_token:
            base["csrfToken"] = csrf_token

        payloads = [base]
        fingerprint = str(seed.get("fingerprint") or "").strip()
        fingerprint_v2 = seed.get("fingerprintV2")
        if fingerprint or fingerprint_v2:
            payloads.insert(0, {
                **base,
                **({"fingerprint": fingerprint} if fingerprint else {}),
                **({"fingerprintV2": fingerprint_v2} if fingerprint_v2 else {}),
            })
        if "@" in username:
            payloads.append({"email": username, "password": password, "uniq": uniq})
        else:
            payloads.append({"username": username, "password": password, "uniq": uniq})
        return payloads

    async def _stripchat_seed_http_session(self, session, username: str) -> dict[str, object]:
        seed: dict[str, object] = {"front_version": self._stripchat_front_version()}
        login_url = f"{STRIPCHAT_BASE_URL}/login"

        flaresolverr_cookies, _ = await self._refresh_flaresolverr_cookies(login_url, username=username)
        if flaresolverr_cookies:
            cookie_values = {
                str(cookie.get("name")): str(cookie.get("value") or "")
                for cookie in flaresolverr_cookies
                if cookie.get("name")
            }
            try:
                session.cookie_jar.update_cookies(cookie_values, response_url=URL(STRIPCHAT_BASE_URL))
            except Exception:
                pass

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": STRIPCHAT_BASE_URL,
        }
        try:
            async with session.get(login_url, headers=headers, allow_redirects=True, **aiohttp_request_kwargs()) as resp:
                text = await resp.text(errors="ignore")
        except Exception:
            text = ""

        release_match = re.search(r'"releaseVersion"\s*:\s*"([^"]+)"', text)
        if release_match:
            seed["front_version"] = release_match.group(1)
        csrf_match = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', text)
        if csrf_match:
            seed["csrfToken"] = csrf_match.group(1)

        try:
            payload = await self._stripchat_http_json(
                session,
                "GET",
                "/v3/config/initial-dynamic",
                params={"requestPath": "/login"},
                referer=login_url,
                include_stored_auth=False,
                front_version=str(seed.get("front_version") or ""),
            )
            version = self._stripchat_find_value(payload, {"releaseversion", "frontversion"})
            if version:
                seed["front_version"] = str(version)
            csrf_token = self._stripchat_find_value(payload, {"csrftoken", "csrf"})
            if csrf_token:
                seed["csrfToken"] = str(csrf_token)
        except ProviderError:
            pass
        return seed

    async def _stripchat_http_json(
        self,
        session,
        method: str,
        path: str,
        params: Optional[dict[str, object]] = None,
        body: Optional[dict[str, object]] = None,
        referer: Optional[str] = None,
        include_stored_auth: bool = False,
        front_version: Optional[str] = None,
    ) -> object:
        headers = await self._stripchat_api_headers(
            referer=referer,
            has_body=body is not None,
            include_stored_auth=include_stored_auth,
            front_version=front_version,
        )
        url = f"{STRIPCHAT_API_BASE}{path if path.startswith('/') else '/' + path}"
        try:
            async with session.request(
                method.upper(),
                url,
                params=params or None,
                json=body if body is not None else None,
                headers=headers,
                allow_redirects=True,
                **aiohttp_request_kwargs(),
            ) as resp:
                text = await resp.text(errors="ignore")
                stripped = text.lstrip()
                if stripped.startswith(("{", "[")):
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("Reponse Stripchat JSON invalide") from exc
                    if isinstance(payload, dict):
                        payload.setdefault("_http_status", resp.status)
                    return payload
                if _INTERACTION_RE.search(text):
                    raise ProviderInteractionRequired("Stripchat demande une verification interactive")
                return {"_http_status": resp.status, "_raw": text[:1000]}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Stripchat API indisponible: {exc}") from exc

    def _stripchat_login_requires_interaction(self, value: object) -> bool:
        challenge_keys = {
            "captcha",
            "recaptcha",
            "hcaptcha",
            "turnstile",
            "needcodeconfirmation",
            "needemailconfirmation",
            "needxhconfirmation",
            "twofa",
            "twofactor",
            "twofadata",
            "isrequired",
            "isaptcharequired",
            "iscaptcharequired",
        }
        message_keys = {
            "_raw",
            "description",
            "detail",
            "error",
            "errors",
            "message",
            "messages",
            "reason",
            "title",
        }

        def walk(child: object, inspect_text: bool = False) -> bool:
            if isinstance(child, dict):
                for key, nested in child.items():
                    key_lower = str(key).lower()
                    if key_lower in challenge_keys and nested not in (None, False, "", [], {}):
                        return True
                    if key_lower in message_keys and walk(nested, inspect_text=True):
                        return True
                    if isinstance(nested, (dict, list)) and walk(nested):
                        return True
                return False
            if isinstance(child, list):
                return any(walk(nested, inspect_text=inspect_text) for nested in child)
            if isinstance(child, str):
                return inspect_text and bool(_INTERACTION_RE.search(child))
            return False

        return walk(value, inspect_text=isinstance(value, str))

    def _stripchat_text_values(self, value: object) -> list[str]:
        values: list[str] = []
        if isinstance(value, dict):
            for child in value.values():
                values.extend(self._stripchat_text_values(child))
        elif isinstance(value, list):
            for child in value:
                values.extend(self._stripchat_text_values(child))
        elif isinstance(value, str):
            text = value.strip()
            if text:
                values.append(text)
        return values

    def _stripchat_login_error(self, payload: object) -> Optional[str]:
        status = int(payload.get("_http_status") or 0) if isinstance(payload, dict) else 0
        if status in (404, 405):
            return None
        text = " ".join(self._stripchat_text_values(payload))
        if _LOGIN_FAILED_RE.search(text) or status in (400, 401):
            return "Login failed. Check username and password."
        if status == 429:
            return "Stripchat login rate limited. Retry later."
        if status >= 400:
            return f"Stripchat login refused (HTTP {status})"
        return None

    def _stripchat_user_matches(self, user: dict[str, object], username: str) -> bool:
        if not user.get("id"):
            return False
        needle = username.lower().strip()
        if not needle:
            return True
        candidates = [
            str(user.get("username") or "").lower().strip(),
            str(user.get("login") or "").lower().strip(),
            str(user.get("email") or "").lower().strip(),
        ]
        return needle in {candidate for candidate in candidates if candidate}

    def _stripchat_current_user_from_payload(self, value: object, username: str = "") -> Optional[dict[str, object]]:
        if isinstance(value, dict):
            for key in ("currentUser", "current_user"):
                child = value.get(key)
                if isinstance(child, dict) and child.get("id"):
                    return child
            for key in ("user", "account", "viewer"):
                child = value.get(key)
                if isinstance(child, dict) and self._stripchat_user_matches(child, username):
                    return child
            if self._stripchat_user_matches(value, username):
                return value
            for child in value.values():
                found = self._stripchat_current_user_from_payload(child, username)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._stripchat_current_user_from_payload(child, username)
                if found:
                    return found
        elif isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return self._stripchat_current_user_from_payload(json.loads(value), username)
            except Exception:
                return None
        return None

    def _stripchat_login_state_from_payload(
        self,
        payload: object,
        username: str,
    ) -> Optional[tuple[str, dict[str, object], str]]:
        user = self._stripchat_current_user_from_payload(payload, username)
        if not user:
            return None
        resolved_username = str(user.get("username") or user.get("login") or username or "").strip()
        jwt_token = self._stripchat_find_value(payload, {"jwttoken", "jwt", "authjwt", "accesstoken"})
        return resolved_username or username, user, str(jwt_token or "").strip()

    def _stripchat_local_storage_state(
        self,
        user: dict[str, object],
        jwt_token: str = "",
    ) -> list[dict[str, object]]:
        entries = [
            {"name": "currentUser", "value": json.dumps({"currentUser": user}, separators=(",", ":"))},
        ]
        if jwt_token:
            entries.append({"name": "jwtToken", "value": jwt_token})
        return [{"origin": STRIPCHAT_BASE_URL, "localStorage": entries}]

    def _stripchat_cookie_jar_to_playwright(self, session) -> list[dict[str, Any]]:
        cookies: list[dict[str, Any]] = []
        try:
            morsels = session.cookie_jar.filter_cookies(URL(STRIPCHAT_BASE_URL)).values()
        except Exception:
            morsels = []
        for morsel in morsels:
            normalized = self._normalize_playwright_cookie({
                "name": morsel.key,
                "value": morsel.value,
                "domain": ".stripchat.com",
                "path": morsel["path"] or "/",
                "secure": True,
                "httpOnly": bool(morsel["httponly"]),
                "sameSite": "Lax",
            })
            if normalized:
                cookies.append(normalized)
        return cookies

    async def _stripchat_save_login_failure(self, username: str, last_error: str) -> None:
        if self.session_store:
            await self.session_store.save(
                self.source_type,
                username=username,
                is_logged_in=False,
                last_error=last_error,
            )

    async def _stripchat_login_http(self, username: str, password: str) -> dict[str, object]:
        username = (username or "").strip()
        if not username or not password:
            return {"success": False, "error": "Username and password are required"}

        timeout = aiohttp.ClientTimeout(total=int(os.getenv("PSTREAMREC_STRIPCHAT_LOGIN_TIMEOUT", "30") or "30"))
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp_client_session(timeout=timeout, cookie_jar=cookie_jar) as session:
            seed = await self._stripchat_seed_http_session(session, username)
            last_error: Optional[str] = None
            for path in self._stripchat_login_paths():
                for body in self._stripchat_login_payloads(username, password, seed):
                    try:
                        payload = await self._stripchat_http_json(
                            session,
                            "POST",
                            path,
                            body=body,
                            referer=f"{STRIPCHAT_BASE_URL}/login",
                            include_stored_auth=False,
                            front_version=str(seed.get("front_version") or ""),
                        )
                    except ProviderInteractionRequired:
                        await self._stripchat_save_login_failure(username, "interaction_required")
                        raise
                    except ProviderError as exc:
                        last_error = str(exc)
                        continue

                    if self._stripchat_login_requires_interaction(payload):
                        await self._stripchat_save_login_failure(username, "interaction_required")
                        raise ProviderInteractionRequired(
                            "Stripchat demande un CAPTCHA/2FA; importez une session navigateur verifiee"
                        )

                    error = self._stripchat_login_error(payload)
                    if error:
                        status = int(payload.get("_http_status") or 0) if isinstance(payload, dict) else 0
                        if status in (404, 405):
                            continue
                        if status == 403:
                            await self._stripchat_save_login_failure(username, "interaction_required")
                            raise ProviderInteractionRequired(
                                "Stripchat refuse le login automatique; importez une session navigateur verifiee"
                            )
                        await self._stripchat_save_login_failure(username, "login_failed")
                        return {"success": False, "error": error}

                    state = self._stripchat_login_state_from_payload(payload, username)
                    if state:
                        resolved_username, user, jwt_token = state
                        if self.session_store:
                            await self.session_store.save(
                                self.source_type,
                                username=resolved_username,
                                is_logged_in=True,
                                cookies=self._stripchat_cookie_jar_to_playwright(session),
                                local_storage=self._stripchat_local_storage_state(user, jwt_token),
                                last_error=None,
                            )
                        return {"success": True, "username": resolved_username}

            for path in ("/v3/config/initial-dynamic", "/v3/config/dynamic"):
                try:
                    payload = await self._stripchat_http_json(
                        session,
                        "GET",
                        path,
                        params={"requestPath": "/"},
                        referer=STRIPCHAT_BASE_URL,
                        include_stored_auth=False,
                        front_version=str(seed.get("front_version") or ""),
                    )
                except ProviderInteractionRequired:
                    await self._stripchat_save_login_failure(username, "interaction_required")
                    raise
                except ProviderError as exc:
                    last_error = str(exc)
                    continue
                state = self._stripchat_login_state_from_payload(payload, username)
                if state:
                    resolved_username, user, jwt_token = state
                    if self.session_store:
                        await self.session_store.save(
                            self.source_type,
                            username=resolved_username,
                            is_logged_in=True,
                            cookies=self._stripchat_cookie_jar_to_playwright(session),
                            local_storage=self._stripchat_local_storage_state(user, jwt_token),
                            last_error=None,
                        )
                    return {"success": True, "username": resolved_username}

        await self._stripchat_save_login_failure(username, "interaction_required")
        if last_error:
            logger.debug("Stripchat HTTP login did not produce a verified session", error=last_error)
        raise ProviderInteractionRequired(
            "Stripchat demande un CAPTCHA/2FA ou refuse le login automatique; importez une session navigateur verifiee"
        )

    async def _stripchat_api_json(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, object]] = None,
        body: Optional[dict[str, object]] = None,
        auth_required: bool = False,
        referer: Optional[str] = None,
    ) -> object:
        if auth_required and not await self._stripchat_has_session():
            raise ProviderAuthError("Connexion Stripchat requise")
        headers = await self._stripchat_api_headers(referer=referer, has_body=body is not None)
        url = f"{STRIPCHAT_API_BASE}{path if path.startswith('/') else '/' + path}"
        timeout = aiohttp.ClientTimeout(total=int(os.getenv("PSTREAMREC_STRIPCHAT_API_TIMEOUT", "20") or "20"))
        try:
            async with aiohttp_client_session(timeout=timeout) as session:
                async with session.request(
                    method.upper(),
                    url,
                    params=params or None,
                    json=body if body is not None else None,
                    headers=headers,
                    allow_redirects=True,
                    **aiohttp_request_kwargs(),
                ) as resp:
                    text = await resp.text(errors="ignore")
                    if resp.status in (401, 403):
                        raise ProviderAuthError("Session Stripchat expiree ou refusee")
                    if resp.status >= 400:
                        raise ProviderError(f"Stripchat API HTTP {resp.status}")
                    stripped = text.lstrip()
                    if not stripped:
                        return {}
                    if not stripped.startswith(("{", "[")):
                        if auth_required and _INTERACTION_RE.search(text):
                            raise ProviderInteractionRequired("Interaction Stripchat requise")
                        raise ProviderError("Reponse Stripchat non JSON")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("Reponse Stripchat JSON invalide") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Stripchat API indisponible: {exc}") from exc

    async def _stripchat_api_headers(
        self,
        referer: Optional[str],
        has_body: bool,
        include_stored_auth: bool = True,
        front_version: Optional[str] = None,
    ) -> dict[str, str]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": STRIPCHAT_BASE_URL,
            "Referer": referer or f"{STRIPCHAT_BASE_URL}/",
            "Front-Version": (front_version or self._stripchat_front_version()).strip(),
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if include_stored_auth:
            cookie_header = await self._provider_cookie_header()
            if cookie_header:
                headers["Cookie"] = cookie_header
            jwt_token = await self._stripchat_jwt_token()
            if jwt_token:
                headers["Authorization"] = jwt_token
        return headers

    async def _stripchat_session_state(self) -> dict[str, Any]:
        if not self.session_store:
            return {}
        try:
            return await self.session_store.get(self.source_type)
        except Exception:
            return {}

    async def _stripchat_has_session(self) -> bool:
        state = await self._stripchat_session_state()
        return bool(state.get("is_logged_in") and (state.get("cookies") or state.get("localStorage")))

    def _stripchat_saved_username(self, state: dict[str, Any]) -> str:
        return str(state.get("username") or state.get("credential_username") or "").strip()

    async def _stripchat_jwt_token(self) -> str:
        state = await self._stripchat_session_state()
        token = self._stripchat_find_value(state.get("localStorage"), {"jwttoken", "jwt"})
        return str(token or "").strip()

    def _stripchat_find_user_id(self, value: object, username: str = "") -> Optional[int]:
        username = username.lower().strip()
        def to_int(raw: object) -> Optional[int]:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        if isinstance(value, dict):
            current = value.get("currentUser")
            if isinstance(current, dict) and current.get("id"):
                return to_int(current.get("id"))
            user = value.get("user")
            if isinstance(user, dict) and user.get("id") and (not username or str(user.get("username") or "").lower() == username):
                return to_int(user.get("id"))
            if value.get("id") and value.get("username") and (not username or str(value.get("username") or "").lower() == username):
                return to_int(value.get("id"))
            for child in value.values():
                found = self._stripchat_find_user_id(child, username)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._stripchat_find_user_id(child, username)
                if found:
                    return found
        elif isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return self._stripchat_find_user_id(json.loads(value), username)
            except Exception:
                return None
        return None

    def _stripchat_find_value(self, value: object, keys: set[str]) -> object:
        keys = {str(key).lower() for key in keys}
        if isinstance(value, dict):
            storage_name = str(value.get("name") or "").lower()
            storage_value = value.get("value")
            if storage_name in keys and storage_value not in (None, "", [], {}):
                return storage_value
            for key, child in value.items():
                if str(key).lower() in keys:
                    return child
                found = self._stripchat_find_value(child, keys)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._stripchat_find_value(child, keys)
                if found is not None:
                    return found
        elif isinstance(value, str):
            if value.strip().startswith(("{", "[")):
                try:
                    return self._stripchat_find_value(json.loads(value), keys)
                except Exception:
                    return None
        return None

    async def _stripchat_browser_follow_action(self, username: str, follow: bool) -> dict[str, object]:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 720},
                args=self._browser_args(),
            )
            try:
                await self._restore_cookies(context)
                page = context.pages[0] if context.pages else await context.new_page()
                try:
                    await page.goto(self.canonical_url(username), wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                await self._dismiss_common_prompts(page)
                result = await page.evaluate(
                    """
                    async ({ username, follow }) => {
                        const frontVersion = window.DEPLOY_CONFIG && window.DEPLOY_CONFIG.releaseVersion;
                        const headers = {
                            Accept: "application/json",
                            "Content-Type": "application/json",
                            ...(frontVersion ? { "Front-Version": frontVersion } : {})
                        };
                        const currentUser = (() => {
                            const candidates = [];
                            try {
                                const state = window.getState && window.getState();
                                candidates.push(state && state.userSession && state.userSession.currentUser);
                            } catch {}
                            try {
                                candidates.push(window.__PRELOADED_STATE__ &&
                                    window.__PRELOADED_STATE__.userSession &&
                                    window.__PRELOADED_STATE__.userSession.currentUser);
                            } catch {}
                            try {
                                if (window.StripChat && typeof window.StripChat.getCurrentUser === "function") {
                                    candidates.push(window.StripChat.getCurrentUser());
                                }
                            } catch {}
                            return candidates.find((item) => item && item.id) || null;
                        })();
                        if (!currentUser || !currentUser.id) return { authError: true, error: "not_logged_in" };
                        const profile = await fetch(`/api/front/v2/models/username/${encodeURIComponent(username)}/cam`, {
                            credentials: "include",
                            headers: { Accept: "application/json", ...(frontVersion ? { "Front-Version": frontVersion } : {}) }
                        });
                        if (profile.status === 401 || profile.status === 403) return { authError: true, error: "auth_required" };
                        if (!profile.ok) return { success: false, error: `profile_http_${profile.status}` };
                        const payload = await profile.json();
                        const model = (payload.user && payload.user.user) || payload.item || {};
                        const modelId = model.id || (payload.cam && payload.cam.streamName);
                        if (!modelId) return { success: false, error: "model_id_missing" };
                        const response = follow
                            ? await fetch(`/api/front/users/${currentUser.id}/favorites/${modelId}`, {
                                method: "PUT",
                                credentials: "include",
                                headers,
                                body: JSON.stringify({ uniq: Date.now() })
                            })
                            : await fetch(`/api/front/users/${currentUser.id}/favorites`, {
                                method: "DELETE",
                                credentials: "include",
                                headers,
                                body: JSON.stringify({ favoriteIds: [Number(modelId)], uniq: Date.now() })
                            });
                        if (response.status === 401 || response.status === 403) return { authError: true, error: "auth_required" };
                        return { success: response.ok, status: response.status };
                    }
                    """,
                    {"username": username, "follow": follow},
                )
                if result.get("authError"):
                    raise ProviderAuthError("Connexion Stripchat requise")
                if not result.get("success"):
                    raise ProviderError(f"Action favoris Stripchat refusee ({result.get('error') or result.get('status')})")
                await self._save_browser_state(context, username, is_logged_in=True)
                return {"success": True, "remote": True, "provider": "stripchat", "username": username}
            finally:
                await context.close()

    def _parse_xcams_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for match in re.finditer(
            r'<li\b(?P<attrs>[^>]*data-testid\s*=\s*["\']model-card["\'][^>]*)>(?P<body>.*?)(?=<li\b[^>]*data-testid\s*=\s*["\']model-card["\']|</ul>|\Z)',
            html_text or "",
            re.IGNORECASE | re.DOTALL,
        ):
            attrs = _parse_attrs(match.group("attrs"))
            body = match.group("body") or ""
            username = (attrs.get("data-cammer-nickname") or "").strip()
            if not username:
                profile_match = re.search(r'href\s*=\s*["\']/profile/([^/"\']+)/', body, re.IGNORECASE)
                username = unquote(profile_match.group(1)).strip() if profile_match else ""
            if not username:
                continue
            tags = ["female"]
            if "models__features--toy" in body or "toy--icon" in body:
                tags.append("toy")
            if "models__labels__item--new" in body:
                tags.append("new")
            if "chat-mode models__labels__item--free" in body or re.search(r">\s*FREE\s*<", body, re.IGNORECASE):
                tags.append("free")
            thumbnail = _first_image(body, page_url)
            items.append({
                "username": username,
                "display_name": username,
                "thumbnail": thumbnail,
                "viewers": _viewer_count(body),
                "subject": "",
                "age": None,
                "gender": "female",
                "is_online": True,
                "tags": _normalize_tags(tags),
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    def _parse_cams_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        data = self._next_data_json(html_text)
        compressed = self._find_first_dict(data, "compressedWonResponse") if data else None
        if not compressed:
            return []
        mapping = compressed.get("mapping") or []
        rows = compressed.get("models") or []
        items: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            model = {key: row[idx] if idx < len(row) else None for idx, key in enumerate(mapping)}
            username = str(model.get("screen_name") or model.get("stream_name") or "").strip()
            if not username:
                continue
            gender = str(model.get("gender") or "").upper()
            tags: list[str] = []
            if gender == "F":
                tags.append("female")
            elif gender == "M":
                tags.append("male")
            elif gender == "TS":
                tags.append("trans")
            try:
                age = int(model.get("public_age") or 0)
            except (TypeError, ValueError):
                age = 0
            if 18 <= age <= 29:
                tags.append("18-29")
            elif 30 <= age <= 39:
                tags.append("30-39")
            elif 40 <= age <= 49:
                tags.append("40-49")
            elif age >= 50:
                tags.append("50+")
            if str(model.get("hq_enabled") or "") == "2":
                tags.append("hd")
            if str(model.get("vr") or "") == "1":
                tags.append("vr")
            image_id = str(model.get("image_pg") or "").strip()
            thumbnail = ""
            if image_id:
                thumbnail = f"https://images4.streamray.com/images/streamray/streams/{username.lower()}_640.gif"
            items.append({
                "username": username,
                "display_name": username,
                "thumbnail": thumbnail or None,
                "viewers": int(model.get("viewer_count") or model.get("viewers") or 0),
                "subject": "",
                "age": age or None,
                "gender": gender.lower(),
                "is_online": True,
                "tags": _normalize_tags(tags),
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    def _embedded_json_payloads(self, html_text: str) -> list[object]:
        payloads: list[object] = []
        for match in re.finditer(r'<script\b[^>]*type\s*=\s*["\']application/json["\'][^>]*>(.*?)</script>', html_text or "", re.IGNORECASE | re.DOTALL):
            raw = html.unescape(match.group(1) or "").strip()
            if not raw:
                continue
            try:
                payloads.append(json.loads(raw))
            except Exception:
                continue
        return payloads

    def _next_data_json(self, html_text: str) -> Optional[dict]:
        match = re.search(r'<script\b[^>]*id\s*=\s*["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html_text or "", re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(html.unescape(match.group(1)))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _find_first_dict(self, value: object, key: str) -> Optional[dict]:
        if isinstance(value, dict):
            if key in value and isinstance(value[key], dict):
                return value[key]
            for child in value.values():
                found = self._find_first_dict(child, key)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._find_first_dict(child, key)
                if found:
                    return found
        return None

    def _find_dicts_with_key(self, value: object, key: str) -> list[dict[str, object]]:
        found: list[dict[str, object]] = []
        if isinstance(value, dict):
            if key in value:
                found.append(value)
            for child in value.values():
                found.extend(self._find_dicts_with_key(child, key))
        elif isinstance(value, list):
            for child in value:
                found.extend(self._find_dicts_with_key(child, key))
        return found

    def _dedupe_discover_models(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        by_username: dict[str, dict[str, object]] = {}
        for item in items:
            username = str(item.get("username") or "").strip().lower()
            if not username:
                continue
            existing = by_username.get(username)
            if not existing:
                by_username[username] = item
                continue
            if not existing.get("thumbnail") and item.get("thumbnail"):
                existing["thumbnail"] = item["thumbnail"]
            existing["viewers"] = max(int(existing.get("viewers") or 0), int(item.get("viewers") or 0))
            existing["tags"] = _normalize_tags(list(existing.get("tags") or []) + list(item.get("tags") or []))
        return list(by_username.values())

    def _parse_myfreecams_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        global_tags = _normalize_tags(re.findall(r">([A-Za-z0-9][A-Za-z0-9_-]{1,47})</a>\s*<a[^>]*>\s*×", html_text or ""))
        items: list[dict[str, object]] = []
        for match in re.finditer(
            r'<div\b(?P<attrs>[^>]*(?:model_online|modelbox_)[^>]*)>(?P<body>.*?)(?=<div\b[^>]*(?:model_online|modelbox_)|</body>|\Z)',
            html_text or "",
            re.IGNORECASE | re.DOTALL,
        ):
            attrs = _parse_attrs(match.group("attrs"))
            body = match.group("body") or ""
            title_match = re.search(r"""title\s*=\s*["']Enter Chat Room of ([^"']+)["']""", body, re.IGNORECASE)
            username = title_match.group(1).strip() if title_match else ""
            if not username:
                text_lines = [line.strip() for line in _strip_html(body).split(" ") if line.strip()]
                username = next((line for line in text_lines if re.match(r"^[A-Za-z0-9_.-]{2,64}$", line)), "")
            if not username:
                continue
            if "%" in username or username.lower() in {"var", "username", "model"}:
                continue
            uid_match = re.search(r"""modelbox_(\d+)|data-uid\s*=\s*["']?(\d+)""", match.group(0), re.IGNORECASE)
            uid = next((g for g in (uid_match.groups() if uid_match else ()) if g), "")
            thumbnail = _best_thumbnail(body, attrs, page_url)
            if thumbnail and "%" in thumbnail:
                thumbnail = None
            if not thumbnail and uid:
                thumbnail = f"https://img.mfcimg.com/photos2/{uid[:3]}/{uid}/avatar.300x300.jpg"
            tags = _normalize_tags(global_tags + _extract_tags(body, attrs))
            items.append({
                "username": username,
                "display_name": username,
                "thumbnail": thumbnail,
                "viewers": _viewer_count(body),
                "subject": "",
                "age": None,
                "gender": "",
                "is_online": True,
                "tags": tags,
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    def _parse_livejasmin_models(self, html_text: str, page_url: str) -> list[dict[str, object]]:
        match = re.search(
            r"listPagePerformers\s*=\s*(\[[\s\S]*?\]);",
            html_text or "",
            re.IGNORECASE,
        )
        if not match:
            return []
        try:
            performers = json.loads(match.group(1))
        except Exception:
            return []
        items = []
        for performer in performers:
            username = str(performer.get("display_name") or "").strip()
            if not username:
                continue
            willingnesses = performer.get("willingnesses") or {}
            tags = list(willingnesses.values()) if isinstance(willingnesses, dict) else []
            if performer.get("language"):
                tags.append(str(performer.get("language")).replace("lng_", ""))
            if performer.get("region"):
                tags.append(performer.get("region"))
            items.append({
                "username": username,
                "display_name": username,
                "thumbnail": performer.get("profilePictureUrl"),
                "viewers": int(performer.get("viewers") or performer.get("num_users") or 0),
                "subject": "",
                "age": None,
                "gender": performer.get("main_category") or "",
                "is_online": int(performer.get("status") or 0) == 1,
                "tags": _normalize_tags(tags),
                "room_status": "public",
                "source_type": self.source_type,
            })
        return items

    def _username_from_url(self, value: str) -> Optional[str]:
        parsed = urlparse(value or "")
        host = parsed.netloc.lower().removeprefix("www.")
        if self.domains and not any(host == d or host.endswith("." + d) for d in self.domains):
            return None
        path_parts = [unquote(p).strip() for p in parsed.path.split("/") if p.strip()]
        candidate = ""
        if self.source_type == "myfreecams":
            hash_parts = [unquote(p).strip() for p in parsed.fragment.split("/") if p.strip()]
            if hash_parts:
                candidate = hash_parts[0]
            elif path_parts and len(path_parts) >= 2 and path_parts[1] == "chat":
                candidate = path_parts[0]
            elif path_parts:
                candidate = path_parts[-1]
        elif self.source_type == "livejasmin":
            for marker in ("girls", "chat"):
                if marker in path_parts:
                    idx = path_parts.index(marker)
                    if len(path_parts) > idx + 1:
                        candidate = path_parts[idx + 1]
                        break
            if not candidate and path_parts:
                candidate = path_parts[-1]
        elif self.source_type == "xcams":
            for marker in ("chat", "profile"):
                if marker in path_parts:
                    idx = path_parts.index(marker)
                    if len(path_parts) > idx + 1:
                        candidate = path_parts[idx + 1]
                        break
            if not candidate and path_parts:
                candidate = path_parts[-1]
        else:
            if "model" in path_parts:
                idx = path_parts.index("model")
                if len(path_parts) > idx + 1:
                    candidate = path_parts[idx + 1]
            elif "models" in path_parts:
                idx = path_parts.index("models")
                if len(path_parts) > idx + 1:
                    candidate = path_parts[idx + 1]
            elif path_parts:
                candidate = path_parts[0]

        candidate = candidate.strip("@/ ").split("?", 1)[0].split("#", 1)[0]
        candidate = re.sub(r"\.html?$", "", candidate)
        if not re.match(r"^[A-Za-z0-9_.-]{2,64}$", candidate or ""):
            return None
        if candidate.lower() in _RESERVED_PROFILE_SEGMENTS:
            return None
        return candidate

    async def _resolve_from_browser(self, urls: list[str], target: str) -> ResolvedStream:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        timeout_seconds = int(os.getenv("PSTREAMREC_BROWSER_CAPTURE_TIMEOUT", "25") or "25")
        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        captured: list[str] = []
        session_username = await self._provider_session_username()
        browser_user_agent = await self._stored_browser_user_agent()

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                user_agent=browser_user_agent,
                viewport={"width": 1280, "height": 720},
                args=self._browser_args(),
            )
            try:
                await self._restore_cookies(context)
                page = context.pages[0] if context.pages else await context.new_page()

                def remember(url: str) -> None:
                    if self._is_media_url(url) and url not in captured:
                        captured.append(url)

                def remember_hls_field_urls(text: str) -> None:
                    for url in extract_hls_url_fields(text):
                        if url not in captured:
                            captured.append(url)

                try:
                    cdp_session = await context.new_cdp_session(page)
                    await cdp_session.send("Network.enable")

                    def remember_ws_frame(event) -> None:
                        payload = ((event.get("response") or {}).get("payloadData") or "")
                        remember_hls_field_urls(payload)
                        for url in extract_media_urls(payload):
                            remember(url)

                    cdp_session.on("Network.webSocketFrameReceived", remember_ws_frame)
                except Exception as exc:
                    logger.debug(
                        "Provider browser CDP capture unavailable",
                        source_type=self.source_type,
                        error=str(exc),
                    )

                page.on("request", lambda request: remember(request.url))
                page.on("response", lambda response: remember(response.url))

                last_html = ""
                for page_url in urls:
                    try:
                        await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                    except PlaywrightTimeoutError:
                        pass
                    except Exception as exc:
                        logger.debug(
                            "Provider browser navigation failed",
                            source_type=self.source_type,
                            url=page_url,
                            error=str(exc),
                        )
                        continue

                    await self._dismiss_common_prompts(page)

                    deadline = time.monotonic() + max(5, timeout_seconds)
                    while time.monotonic() < deadline:
                        if captured:
                            await self._save_browser_state(context, session_username, is_logged_in=True)
                            stream_url = captured[0]
                            try:
                                last_html = await page.content()
                            except Exception:
                                pass
                            meta = _page_metadata(last_html, page.url)
                            return ResolvedStream(
                                url=stream_url,
                                headers=self._stream_headers(page.url, await self._cookie_header(context)),
                                source_type=self.source_type,
                                is_live=True,
                                room_status="public",
                                viewers=int(meta.get("viewers") or 0),
                                tags=list(meta.get("tags") or []),
                                thumbnail=meta.get("thumbnail") or None,
                                title=meta.get("title") or None,
                            )
                        try:
                            last_html = await page.content()
                            remember_hls_field_urls(last_html)
                            media_urls = extract_media_urls(last_html)
                            if media_urls:
                                await self._save_browser_state(context, session_username, is_logged_in=True)
                                meta = _page_metadata(last_html, page.url)
                                return ResolvedStream(
                                    url=media_urls[0],
                                    headers=self._stream_headers(page.url, await self._cookie_header(context)),
                                    source_type=self.source_type,
                                    is_live=True,
                                    room_status="public",
                                    viewers=int(meta.get("viewers") or 0),
                                    tags=list(meta.get("tags") or []),
                                    thumbnail=meta.get("thumbnail") or None,
                                    title=meta.get("title") or None,
                                )
                        except Exception:
                            pass
                        await page.wait_for_timeout(500)

                logged_in = await self._looks_logged_in(page, username=session_username)
                await self._save_browser_state(context, session_username, is_logged_in=logged_in)
                self._raise_page_state(last_html)
                raise ProviderOfflineError(f"Aucun flux public trouve pour {self.display_name}/{target}")
            finally:
                await context.close()

    def _bongacams_interaction_required_message(self, page_url: str, visible_text: str) -> str:
        lower = f"{page_url or ''}\n{visible_text or ''}".lower()
        if "suspect-login" in lower or "unfamiliar device" in lower or "new ip address" in lower:
            return "BongaCams demande un captcha pour ce nouvel appareil ou cette nouvelle IP"
        return "Automatic login blocked by the provider challenge"

    async def _bongacams_login(self, username: str, password: str) -> dict[str, object]:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        login_urls = [
            template.format(username=quote_plus(username))
            for template in self.login_templates
        ] or [f"{BONGACAMS_BASE_URL}/login"]

        flaresolverr_cookies: list[dict[str, Any]] = []
        flaresolverr_user_agent: Optional[str] = None
        for login_url in login_urls:
            flaresolverr_cookies, flaresolverr_user_agent = await self._refresh_flaresolverr_cookies(login_url, username=username)
            if flaresolverr_cookies:
                break

        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                args=self._browser_args(),
                user_agent=flaresolverr_user_agent or DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 720},
            )
            try:
                await self._restore_cookies(context)
                if flaresolverr_cookies:
                    try:
                        await context.add_cookies(flaresolverr_cookies)
                    except Exception:
                        pass
                page = await context.new_page()
                for login_url in login_urls:
                    try:
                        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                    except PlaywrightTimeoutError:
                        pass
                    except Exception:
                        continue
                    await self._dismiss_common_prompts(page)
                    await page.wait_for_timeout(2000)

                    visible_text = await self._visible_page_text(page)
                    if _INTERACTION_RE.search(visible_text) or await self._has_challenge_widget(page):
                        refreshed, _ = await self._refresh_flaresolverr_cookies(login_url, username=username)
                        if refreshed:
                            try:
                                await context.add_cookies(refreshed)
                                await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                                await self._dismiss_common_prompts(page)
                                await page.wait_for_timeout(1500)
                            except Exception:
                                pass

                    cookies = await context.cookies()
                    if cookies and await self._looks_logged_in(page, username=username):
                        await self._save_browser_state(context, username, is_logged_in=True)
                        return {"success": True, "username": username, "reusedSession": True}

                    submitted = await self._fill_login_form(page, username, password)
                    if submitted:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=7000)
                        except Exception:
                            pass

                    verify_seconds = int(os.getenv("PSTREAMREC_PROVIDER_LOGIN_VERIFY_SECONDS", "25") or "25")
                    challenge_seen = False
                    for _ in range(max(5, verify_seconds)):
                        await page.wait_for_timeout(1000)
                        visible_text = await self._visible_page_text(page)
                        if _LOGIN_FAILED_RE.search(visible_text):
                            await self._save_browser_state(context, username, is_logged_in=False, last_error="login_failed")
                            return {"success": False, "error": "Login failed. Check username and password."}
                        cookies = await context.cookies()
                        if cookies and await self._looks_logged_in(page, username=username):
                            await self._save_browser_state(context, username, is_logged_in=True)
                            return {"success": True, "username": username}
                        if _INTERACTION_RE.search(visible_text) or await self._has_challenge_widget(page):
                            challenge_seen = True
                            break

                    if challenge_seen:
                        visible_text = await self._visible_page_text(page)
                        await self._save_browser_state(context, username, is_logged_in=False, last_error="interaction_required")
                        raise ProviderInteractionRequired(
                            self._bongacams_interaction_required_message(page.url, visible_text)
                        )

                await self._save_browser_state(context, username, is_logged_in=False, last_error="login_failed")
                return {"success": False, "error": "Login form introuvable ou connexion refusee"}
            finally:
                await context.close()

    async def login(self, username: str, password: str) -> dict[str, object]:
        if self.source_type == "stripchat":
            result = await self._stripchat_login_http(username, password)
            if result.get("success"):
                return result
            try:
                return await self._browser_login(username, password)
            except ProviderInteractionRequired:
                raise
            except ProviderError:
                return result
        if self.source_type == "bongacams":
            return await self._bongacams_login(username, password)
        return await self._browser_login(username, password)

    async def _browser_login(self, username: str, password: str) -> dict[str, object]:
        username = (username or "").strip()
        if not username or not password:
            return {"success": False, "error": "Username and password are required"}

        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise ProviderError("Playwright n'est pas installe") from exc

        headless = os.getenv("PSTREAMREC_BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"}
        login_urls = [
            template.format(username=quote_plus(username))
            for template in self.login_templates
        ]
        user_data_dir = self.browser_root / self.source_type
        user_data_dir.mkdir(parents=True, exist_ok=True)
        browser_user_agent = await self._stored_browser_user_agent()

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=headless,
                args=self._browser_args(),
                user_agent=browser_user_agent,
                viewport={"width": 1280, "height": 720},
            )
            try:
                await self._restore_cookies(context)
                page = await context.new_page()
                for login_url in login_urls:
                    try:
                        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                    except PlaywrightTimeoutError:
                        pass
                    except Exception:
                        continue
                    await self._dismiss_common_prompts(page)
                    await page.wait_for_timeout(2500)
                    cookies = await context.cookies()
                    if cookies and await self._looks_logged_in(page, username=username):
                        await self._save_browser_state(context, username, is_logged_in=True)
                        return {"success": True, "username": username, "reusedSession": True}
                    submitted = await self._fill_login_form(page, username, password)
                    if submitted:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception:
                            pass
                    verify_seconds = int(os.getenv("PSTREAMREC_PROVIDER_LOGIN_VERIFY_SECONDS", "25") or "25")
                    challenge_seen = False
                    for _ in range(max(5, verify_seconds)):
                        await page.wait_for_timeout(1000)
                        visible_text = await self._visible_page_text(page)
                        if _LOGIN_FAILED_RE.search(visible_text):
                            await self._save_browser_state(context, username, is_logged_in=False, last_error="login_failed")
                            return {"success": False, "error": "Login failed. Check username and password."}
                        cookies = await context.cookies()
                        if (submitted or cookies) and cookies and await self._looks_logged_in(page, username=username):
                            await self._save_browser_state(context, username, is_logged_in=True)
                            return {"success": True, "username": username}
                        if _INTERACTION_RE.search(visible_text):
                            challenge_seen = True
                            break
                        if submitted and await self._has_challenge_widget(page):
                            challenge_seen = True
                    if challenge_seen:
                        visible_text = await self._visible_page_text(page)
                        cookies = await context.cookies()
                        if not (submitted and cookies and await self._looks_logged_in(page, username=username)):
                            interactive_wait = int(os.getenv("PSTREAMREC_PROVIDER_LOGIN_INTERACTIVE_WAIT_SECONDS", "0") or "0")
                            if interactive_wait > 0 and not headless:
                                deadline = time.monotonic() + interactive_wait
                                while time.monotonic() < deadline:
                                    await page.wait_for_timeout(1000)
                                    visible_text = await self._visible_page_text(page)
                                    if _LOGIN_FAILED_RE.search(visible_text):
                                        await self._save_browser_state(context, username, is_logged_in=False, last_error="login_failed")
                                        return {"success": False, "error": "Login failed. Check username and password."}
                                    cookies = await context.cookies()
                                    if cookies and await self._looks_logged_in(page, username=username):
                                        await self._save_browser_state(context, username, is_logged_in=True)
                                        return {"success": True, "username": username, "interactiveSession": True}
                            await self._save_browser_state(context, username, is_logged_in=False, last_error="interaction_required")
                            raise ProviderInteractionRequired(
                                "Automatic login blocked by the provider challenge"
                            )
                await self._save_browser_state(context, username, is_logged_in=False, last_error="login_failed")
                return {"success": False, "error": "Login form introuvable ou connexion refusee"}
            finally:
                await context.close()

    async def logout(self) -> dict[str, object]:
        if self.session_store:
            await self.session_store.clear(self.source_type)
        return {"success": True}

    def _stream_headers(self, page_url: str, cookie_header: Optional[str] = None) -> dict[str, str]:
        parsed = urlparse(page_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": page_url,
        }
        if origin:
            headers["Origin"] = origin
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _is_media_url(self, value: str) -> bool:
        return _is_probable_media_url(value)

    def _raise_page_state(self, content: str) -> None:
        text = content or ""
        if _INTERACTION_RE.search(text):
            raise ProviderInteractionRequired("Interaction manuelle requise")
        if _AUTH_REQUIRED_RE.search(text):
            raise ProviderAuthError("Connexion requise")
        if _PRIVATE_RE.search(text):
            raise ProviderPrivateError("Le modele semble en show prive ou premium")
        if _OFFLINE_RE.search(text):
            raise ProviderOfflineError("Le modele semble hors ligne")

    async def _apply_browser_stealth(self, context) -> None:
        try:
            await context.add_init_script(
                """
                (() => {
                    try {
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    } catch {}
                    try {
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    } catch {}
                    try {
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    } catch {}
                    try {
                        window.chrome = window.chrome || { runtime: {} };
                    } catch {}
                    try {
                        const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
                        if (originalQuery) {
                            window.navigator.permissions.query = (parameters) => (
                                parameters && parameters.name === 'notifications'
                                    ? Promise.resolve({ state: Notification.permission })
                                    : originalQuery(parameters)
                            );
                        }
                    } catch {}
                })();
                """
            )
        except Exception:
            return

    async def _restore_cookies(self, context) -> None:
        await self._apply_browser_stealth(context)
        if not self.session_store:
            return
        state = await self.session_store.get(self.source_type)
        cookies = state.get("cookies") or []
        if cookies:
            try:
                await context.add_cookies(cookies)
            except Exception:
                pass
        local_storage = state.get("localStorage") or []
        if local_storage:
            try:
                await context.add_init_script(
                    """
                    (() => {
                        const origins = __PSTREAMREC_ORIGINS__;
                        const originState = origins.find((entry) => entry && entry.origin === window.location.origin);
                        if (!originState || !Array.isArray(originState.localStorage)) return;
                        for (const item of originState.localStorage) {
                            if (!item || !item.name || typeof item.value !== 'string') continue;
                            try { window.localStorage.setItem(item.name, item.value); } catch {}
                        }
                    })();
                    """.replace("__PSTREAMREC_ORIGINS__", json.dumps(local_storage))
                )
            except Exception:
                pass

    async def _save_browser_state(
        self,
        context,
        username: Optional[str],
        is_logged_in: bool,
        last_error: Optional[str] = None,
    ) -> None:
        if not self.session_store:
            return
        try:
            state = await context.storage_state()
        except Exception:
            state = {}
        await self.session_store.save(
            self.source_type,
            username=username,
            is_logged_in=is_logged_in,
            cookies=state.get("cookies") or [],
            local_storage=state.get("origins") or [],
            last_error=last_error,
        )

    async def _cookie_header(self, context) -> str:
        try:
            return ProviderSessionStore.cookies_to_header(await context.cookies())
        except Exception:
            return ""

    async def _dismiss_common_prompts(self, page) -> None:
        labels = re.compile(
            r"(^(accept|accept all|accept cookies|i agree|agree|continue|enter|yes|allow|j'accepte|accepter|tout accepter|ok)$|over 18|enter site)",
            re.IGNORECASE,
        )
        clicked = False
        for role in ("button", "link"):
            try:
                locator = page.get_by_role(role, name=labels)
                count = min(await locator.count(), 3)
                for idx in range(count):
                    try:
                        await locator.nth(idx).click(timeout=1000)
                        clicked = True
                    except Exception:
                        pass
            except Exception:
                pass
        if clicked:
            try:
                await page.wait_for_timeout(1000)
            except Exception:
                pass

    async def _try_search(self, page, target: str) -> None:
        selectors = [
            "input[type=search]",
            'input[name*="search" i]',
            'input[placeholder*="Search" i]',
            'input[placeholder*="model" i]',
        ]
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if await field.count():
                    await field.fill(target, timeout=1000)
                    await field.press("Enter", timeout=1000)
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue

    async def _visible_page_text(self, page) -> str:
        try:
            return await page.locator("body").inner_text(timeout=3000)
        except Exception:
            return ""

    async def _stripchat_page_current_user(self, page) -> bool:
        try:
            return bool(await page.evaluate(
                """
                () => {
                    const candidates = [];
                    try {
                        const state = window.getState && window.getState();
                        candidates.push(state && state.userSession && state.userSession.currentUser);
                    } catch {}
                    try {
                        candidates.push(window.__PRELOADED_STATE__ &&
                            window.__PRELOADED_STATE__.userSession &&
                            window.__PRELOADED_STATE__.userSession.currentUser);
                    } catch {}
                    try {
                        if (window.StripChat && typeof window.StripChat.getCurrentUser === 'function') {
                            candidates.push(window.StripChat.getCurrentUser());
                        }
                    } catch {}
                    return candidates.some((user) => user && (user.id || user.username || user.login));
                }
                """
            ))
        except Exception:
            return False

    async def _bongacams_page_has_account_shell(self, page) -> bool:
        try:
            return bool(await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    };
                    if (Array.from(document.querySelectorAll('input[type="password"]')).some(visible)) {
                        return false;
                    }
                    const accountText = /\\b(log\\s*out|logout|sign\\s*out|my\\s+account|account\\s+settings|my\\s+profile|tokens|credits)\\b/i;
                    const loginText = /^(log\\s*in|login|sign\\s*in|signin)$/i;
                    let sawAccount = false;
                    for (const el of document.querySelectorAll('a, button, [role="button"]')) {
                        if (!visible(el)) continue;
                        const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim();
                        const href = el.getAttribute('href') || '';
                        if (loginText.test(text)) return false;
                        if (accountText.test(`${text} ${href}`)) sawAccount = true;
                    }
                    return sawAccount;
                }
                """
            ))
        except Exception:
            return False

    async def _looks_logged_in(self, page, username: Optional[str] = None) -> bool:
        for selector in (
            "input[type=password]:visible",
            'input[autocomplete="current-password"]:visible',
            'input[name*="pass" i]:visible',
        ):
            try:
                if await page.locator(selector).count():
                    return False
            except Exception:
                pass
        if self.source_type == "stripchat" and await self._stripchat_page_current_user(page):
            return True
        if self.source_type == "bongacams" and await self._bongacams_page_has_account_shell(page):
            return True
        visible_text = await self._visible_page_text(page)
        lower_text = visible_text.lower()
        normalized_username = (username or "").strip().lower()
        if normalized_username and normalized_username in lower_text:
            return True
        if re.search(r"\b(log\s*out|logout|sign\s*out|my\s+account|account\s+settings)\b", lower_text):
            return True
        if await self._has_visible_login_action(page):
            return False
        return self.source_type not in {
            "bongacams",
            "cams",
            "camsoda",
            "livejasmin",
            "myfreecams",
            "stripchat",
            "xcams",
        }

    async def _has_visible_login_action(self, page) -> bool:
        try:
            return bool(await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    };
                    const loginText = /^(log\\s*in|login|sign\\s*in|signin|join\\s+now|join\\s+for\\s+free)$/i;
                    return Array.from(document.querySelectorAll('a, button, input[type="submit"], input[type="button"]'))
                        .some((el) => {
                            if (!visible(el) || el.disabled) return false;
                            const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim();
                            return loginText.test(text);
                        });
                }
                """
            ))
        except Exception:
            return False

    async def _has_challenge_widget(self, page) -> bool:
        try:
            return bool(await page.evaluate(
                """
                () => {
                    const selectors = [
                        'iframe[src*="captcha" i]',
                        'iframe[src*="turnstile" i]',
                        'iframe[src*="challenge" i]',
                        'input[name*="captcha" i]',
                        'input[id*="captcha" i]',
                        'input[name*="turnstile" i]',
                        'input[id*="turnstile" i]',
                        '[class*="captcha" i]',
                        '[id*="captcha" i]',
                        '[class*="turnstile" i]',
                        '[id*="turnstile" i]'
                    ];
                    return selectors.some((selector) => document.querySelector(selector));
                }
                """
            ))
        except Exception:
            return False

    async def _fill_login_form(self, page, username: str, password: str) -> bool:
        try:
            submitted = await page.evaluate(
                """
                ({ username, password }) => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    };
                    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    const setValue = (el, value) => {
                        if (!el) return;
                        valueSetter.call(el, value);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    };
                    const attrText = (el) => [
                        el.name,
                        el.id,
                        el.placeholder,
                        el.autocomplete,
                        el.getAttribute('aria-label'),
                    ].filter(Boolean).join(' ').toLowerCase();
                    const scoreUserField = (el, passwordField) => {
                        const type = (el.type || '').toLowerCase();
                        if (el === passwordField || type === 'password' || type === 'hidden' ||
                            type === 'submit' || type === 'button' || type === 'checkbox' ||
                            type === 'radio' || type === 'search') {
                            return -1000;
                        }
                        if (!visible(el) || el.disabled || el.readOnly) return -1000;
                        const text = attrText(el);
                        let score = 0;
                        if (/user|login|email|account|member/.test(text)) score += 80;
                        if (/search|model|find/.test(text)) score -= 120;
                        if (type === 'email') score += 60;
                        if (type === 'text' || !type) score += 10;
                        const passRect = passwordField.getBoundingClientRect();
                        const rect = el.getBoundingClientRect();
                        if (rect.top <= passRect.top) score += 15;
                        score -= Math.min(50, Math.abs(passRect.top - rect.top) / 20);
                        return score;
                    };
                    const submitText = /^(log\\s*in|login|sign\\s*in|signin|connect|continue|submit)$/i;
                    const passwordFields = Array.from(document.querySelectorAll('input[type="password"]'))
                        .filter((el) => visible(el) && !el.disabled && !el.readOnly);
                    for (const passwordField of passwordFields) {
                        const root = passwordField.closest('form') || passwordField.closest('[role="dialog"]') || document;
                        const fields = Array.from(root.querySelectorAll('input'))
                            .map((el) => [scoreUserField(el, passwordField), el])
                            .filter(([score]) => score > -1000)
                            .sort((a, b) => b[0] - a[0]);
                        const usernameField = fields.length ? fields[0][1] : null;
                        if (!usernameField) continue;
                        setValue(usernameField, username);
                        setValue(passwordField, password);

                        const submitCandidates = Array.from(root.querySelectorAll('button, input[type="submit"], a'))
                            .filter((el) => visible(el) && !el.disabled);
                        let submit = root.querySelector('button[type="submit"], input[type="submit"]');
                        if (!submit || !visible(submit) || submit.disabled) {
                            submit = submitCandidates.find((el) => {
                                const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim();
                                return submitText.test(text);
                            });
                        }
                        if (submit) {
                            submit.click();
                        } else {
                            passwordField.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                            passwordField.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
                        }
                        return true;
                    }
                    return false;
                }
                """,
                {"username": username, "password": password},
            )
            if submitted:
                return True
        except Exception:
            pass

        try:
            await page.keyboard.press("Enter")
            return True
        except Exception:
            return False
