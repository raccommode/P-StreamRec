import re
import requests
from .base import ResolveError


def resolve_m3u8(username: str) -> str:
    """
    Résolveur Chaturbate ultra-simplifié et fiable.
    Extrait directement le M3U8 depuis la page HTML.
    """
    username = username.strip().lower()
    if not username or not re.match(r'^[a-z0-9_]+$', username):
        raise ResolveError("Nom d'utilisateur invalide")
    
    try:
        # Récupérer la page HTML
        url = f"https://chaturbate.com/{username}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise ResolveError(f"Impossible d'accéder à la page (HTTP {resp.status_code})")
        
        html = resp.text
        
        # Chercher le M3U8 avec regex simple
        m3u8_patterns = [
            r'"(https://[^"]*\.m3u8[^"]*)"',
            r"'(https://[^']*\.m3u8[^']*)'",
            r'hls_source["\s:]+(["\'])(https://[^"\']+\.m3u8[^"\']*)\1',
        ]
        
        for pattern in m3u8_patterns:
            matches = re.findall(pattern, html)
            if matches:
                # Prendre le premier match (ou le groupe capturé)
                m3u8_url = matches[0] if isinstance(matches[0], str) else matches[0][-1]
                m3u8_url = m3u8_url.replace("\\/", "/")
                
                if m3u8_url.startswith("http") and ".m3u8" in m3u8_url:
                    return m3u8_url
        
        # Si pas trouvé, vérifier si hors ligne
        if "offline" in html.lower() or "room_status" in html and "offline" in html:
            raise ResolveError(f"{username} est hors ligne")
        
        raise ResolveError(f"Impossible de trouver le flux M3U8 pour {username}")
        
    except requests.RequestException as e:
        raise ResolveError(f"Erreur réseau: {str(e)}")
    except ResolveError:
        raise
    except Exception as e:
        raise ResolveError(f"Erreur inattendue: {str(e)}")
