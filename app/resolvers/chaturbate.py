import os
import re
import json
import requests
from typing import Optional, Dict, Any
from .base import ResolveError

# Multiple API endpoints for fallback
API_TEMPLATE = "https://chaturbate.com/api/chatvideocontext/{username}/"
ROOM_STATUS_API = "https://roomlister.stream/api/rooms/{username}"
ROOM_PAGE_URL = "https://chaturbate.com/{username}/"


def extract_m3u8_from_page(username: str) -> Optional[str]:
    """Extrait le M3U8 directement depuis la page HTML (méthode la plus fiable)."""
    try:
        url = ROOM_PAGE_URL.format(username=username)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://chaturbate.com/",
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            html = resp.text
            
            # Méthode 1: Chercher dans les variables JavaScript
            patterns = [
                r'hls_source["\']?\s*:\s*["\']([^"\']+)["\']',
                r'hlsSource["\']?\s*:\s*["\']([^"\']+)["\']',
                r'm3u8["\']?\s*:\s*["\']([^"\']+)["\']',
                r'stream_url["\']?\s*:\s*["\']([^"\']+)["\']',
                r'playlist\.m3u8[?"]',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    if match.groups():
                        m3u8_url = match.group(1)
                    else:
                        # Extraire l'URL complète autour du match
                        context = html[max(0, match.start()-100):match.end()+100]
                        url_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', context)
                        if url_match:
                            m3u8_url = url_match.group(0)
                        else:
                            continue
                    
                    # Nettoyer l'URL
                    m3u8_url = m3u8_url.replace("\\/", "/").replace("\\", "")
                    if m3u8_url.startswith("//"):
                        m3u8_url = "https:" + m3u8_url
                    
                    # Vérifier que c'est une URL valide
                    if m3u8_url.startswith("http") and ".m3u8" in m3u8_url:
                        return m3u8_url
            
            # Méthode 2: Chercher toutes les URLs .m3u8 dans la page
            all_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
            if all_m3u8:
                # Prendre la première URL trouvée
                return all_m3u8[0].replace("\\/", "/")
                
    except Exception as e:
        print(f"Erreur extraction page HTML: {e}")
    
    return None


def get_room_info(username: str) -> Optional[Dict[str, Any]]:
    """Récupère les informations de la room via API alternative."""
    try:
        url = ROOM_STATUS_API.format(username=username)
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def resolve_m3u8(username: str) -> str:
    """
    Resolver amélioré pour Chaturbate avec fallback.
    - Utilise plusieurs méthodes pour récupérer le flux HLS
    - May require a valid session cookie depending on availability and ToS.
    - Set CB_COOKIE env var if needed (e.g., "session=...; other=...").
    """
    # Nettoyer le username
    username = username.strip().lower()
    if not username or not re.match(r'^[a-z0-9_]+$', username):
        raise ResolveError("Nom d'utilisateur invalide. Utilisez uniquement des lettres, chiffres et underscores.")

    # MÉTHODE 1 (LA PLUS FIABLE): Extraire directement depuis la page HTML
    print(f"🔍 Tentative d'extraction M3U8 depuis la page pour {username}...")
    m3u8_from_page = extract_m3u8_from_page(username)
    if m3u8_from_page:
        print(f"✅ M3U8 trouvé via page HTML: {m3u8_from_page}")
        return m3u8_from_page
    
    # MÉTHODE 2: Essayer l'API JSON
    print(f"🔍 Tentative via API JSON pour {username}...")
    # Configuration des headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": f"https://chaturbate.com/{username}/",
        "Origin": "https://chaturbate.com",
    }
    
    cookie = os.getenv("CB_COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie

    # Essayer l'API principale
    url = API_TEMPLATE.format(username=username)

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                # Essayer de parser le contenu HTML si ce n'est pas du JSON
                match = re.search(r'"hls_source"\s*:\s*"([^"]+)"', resp.text)
                if match:
                    m3u8_url = match.group(1).replace("\\/", "/")
                    if m3u8_url:
                        return m3u8_url
                raise ResolveError("Impossible de parser la réponse du serveur.")
            
            # Chercher le flux HLS dans différents champs possibles
            # Priorité: source_cdn > source > autres (pour avoir la meilleure qualité)
            m3u8 = (data.get("hls_source_cdn") or  # CDN souvent meilleure qualité
                   data.get("hls_source") or 
                   data.get("edge_hls_url") or
                   data.get("hls_src") or 
                   data.get("url") or 
                   data.get("hls_url"))
            
            if m3u8:
                # Nettoyer l'URL si nécessaire
                m3u8 = m3u8.replace("\\/", "/")
                if m3u8.startswith("//"):
                    m3u8 = "https:" + m3u8
                
                # Si c'est une playlist master, FFmpeg sélectionnera automatiquement la meilleure qualité
                return m3u8
            
            # Vérifier si l'utilisateur est en ligne
            if data.get("room_status") == "offline" or data.get("is_offline"):
                raise ResolveError(f"L'utilisateur {username} est hors ligne.")
                
        elif resp.status_code == 401:
            raise ResolveError("Authentification requise. Configurez CB_COOKIE avec un cookie de session valide.")
        elif resp.status_code == 404:
            raise ResolveError(f"L'utilisateur {username} n'existe pas.")
            
    except requests.RequestException as e:
        # Essayer l'API alternative
        room_info = get_room_info(username)
        if room_info and room_info.get("hls_url"):
            return room_info["hls_url"]
        raise ResolveError(f"Erreur réseau: {e}")
    
    # Si on arrive ici, aucune méthode n'a fonctionné
    raise ResolveError(f"Impossible de récupérer le flux pour {username}. L'utilisateur peut être hors ligne ou privé.")
