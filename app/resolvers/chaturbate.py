import os
import requests
from typing import Optional
from .base import ResolveError

API_TEMPLATE = "https://chaturbate.com/api/chatvideocontext/{username}/"


def resolve_m3u8(username: str) -> str:
    """
    Best-effort resolver for Chaturbate.
    - May require a valid session cookie depending on availability and ToS.
    - Set CB_COOKIE env var if needed (e.g., "session=...; other=...").
    """
    if not username or "/" in username:
        raise ResolveError("Nom d'utilisateur invalide.")

    url = API_TEMPLATE.format(username=username.strip())
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
        "Accept": "application/json",
    }
    cookie = os.getenv("CB_COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        raise ResolveError(f"Erreur réseau: {e}")

    if resp.status_code != 200:
        raise ResolveError(f"Statut HTTP {resp.status_code} lors de la récupération des métadonnées.")

    try:
        data = resp.json()
    except ValueError:
        raise ResolveError("Réponse JSON invalide du serveur.")

    m3u8 = data.get("hls_source") or data.get("hls_src") or data.get("url") or data.get("hls_url")
    if not m3u8:
        raise ResolveError("Flux HLS non disponible (peut nécessiter authentification ou l'utilisateur est hors ligne).")

    return m3u8
