import re
import html
import time
import requests
from .base import ResolveError
from ..logger import logger

# Rate limiting pour éviter HTTP 429
_last_request_time = 0
_min_delay_between_requests = 2.0  # 2 secondes entre chaque requête


def resolve_m3u8(username: str) -> str:
    """
    Résolveur Chaturbate ultra-simplifié et fiable.
    Extrait directement le M3U8 depuis la page HTML.
    """
    logger.subsection(f"🔍 Résolution M3U8 - {username}")
    
    username = username.strip().lower()
    if not username or not re.match(r'^[a-z0-9_]+$', username):
        logger.error("Nom d'utilisateur invalide", username=username)
        raise ResolveError("Nom d'utilisateur invalide")
    
    logger.debug("Username validé", username=username)
    
    try:
        # Récupérer la page HTML
        url = f"https://chaturbate.com/{username}/"
        logger.progress("Récupération page Chaturbate", username=username, url=url)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        logger.debug("Réponse HTTP reçue", username=username, status_code=resp.status_code)
        
        if resp.status_code != 200:
            logger.error("Erreur HTTP", username=username, status_code=resp.status_code)
            raise ResolveError(f"Impossible d'accéder à la page (HTTP {resp.status_code})")
        
        html_content = resp.text
        logger.debug("Page HTML récupérée", username=username, size_chars=len(html_content))
        
        # Chercher le M3U8 avec patterns multiples et variés
        m3u8_patterns = [
            # URLs directes entre guillemets
            r'"(https?://[^"]*\.m3u8[^"]*)"',
            r"'(https?://[^']*\.m3u8[^']*)'",
            # Dans variables JavaScript
            r'hls_source["\s:=]+(["\'])(https?://[^"\']+\.m3u8[^"\']*)\1',
            r'hlsSource["\s:=]+(["\'])(https?://[^"\']+\.m3u8[^"\']*)\1',
            r'm3u8["\s:=]+(["\'])(https?://[^"\']+\.m3u8[^"\']*)\1',
            # URL encodée (avec antislash)
            r'(https?:\\?/\\?/[^"\'\\s]+\.m3u8[^"\'\\s]*)',
            # Dans JSON
            r'"url"["\s:]+(["\'])(https?://[^"\']+\.m3u8[^"\']*)\1',
            # Pattern large pour tout .m3u8
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        ]
        
        logger.debug("Recherche M3U8 avec patterns", 
                    username=username, 
                    pattern_count=len(m3u8_patterns))
        
        for i, pattern in enumerate(m3u8_patterns, 1):
            logger.debug(f"Test pattern {i}/{len(m3u8_patterns)}", 
                        username=username,
                        pattern_preview=pattern[:60])
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            
            if matches:
                logger.debug("Pattern match trouvé", 
                           username=username,
                           pattern_index=i,
                           match_count=len(matches))
                # Prendre le premier match (ou le groupe capturé)
                if isinstance(matches[0], tuple):
                    # Si c'est un tuple (groupes capturés), prendre le dernier élément non vide
                    m3u8_url = [g for g in matches[0] if g and 'http' in g][0] if matches[0] else matches[0][-1]
                else:
                    m3u8_url = matches[0]
                
                # Nettoyer l'URL
                m3u8_url = m3u8_url.replace("\\/", "/").replace("\\", "")
                
                # Décoder les entités Unicode (u002D = -, u0022 = ", etc.)
                m3u8_url = html.unescape(m3u8_url)
                
                # Remplacer les codes Unicode hexadécimaux
                def decode_unicode(match):
                    return chr(int(match.group(1), 16))
                m3u8_url = re.sub(r'u([0-9a-fA-F]{4})', decode_unicode, m3u8_url)
                
                # Supprimer les caractères parasites à la fin
                m3u8_url = m3u8_url.rstrip('",;: \t\n\r')
                
                logger.debug("M3U8 candidat trouvé", 
                           username=username,
                           url_preview=m3u8_url[:80])
                
                if m3u8_url.startswith("http") and ".m3u8" in m3u8_url:
                    logger.success("M3U8 résolu avec succès", 
                                 username=username,
                                 m3u8_url=m3u8_url,
                                 pattern_used=i)
                    return m3u8_url
                else:
                    logger.debug("URL candidat invalide", 
                               username=username,
                               url=m3u8_url)
        
        # Si pas trouvé, vérifier si hors ligne
        logger.warning("Aucun M3U8 trouvé, vérification statut", username=username)
        
        html_lower = html_content.lower()
        if "offline" in html_lower:
            logger.info("Utilisateur détecté hors ligne", username=username)
            raise ResolveError(f"{username} est hors ligne")
        
        # Debug: rechercher 'hls' et 'm3u8' dans le HTML
        hls_count = html_lower.count('hls')
        m3u8_count = html_lower.count('m3u8')
        
        logger.debug("Analyse HTML", 
                    username=username,
                    html_size=len(html_content),
                    hls_occurrences=hls_count,
                    m3u8_occurrences=m3u8_count,
                    html_preview=html_content[:500])
        
        logger.error("M3U8 non trouvé", username=username)
        raise ResolveError(f"Impossible de trouver le flux M3U8 pour {username}")
        
    except requests.RequestException as e:
        logger.error("Erreur réseau lors de la résolution", 
                    username=username,
                    exc_info=True,
                    error=str(e))
        raise ResolveError(f"Erreur réseau: {str(e)}")
    except ResolveError:
        raise
    except Exception as e:
        logger.critical("Erreur inattendue dans le resolver", 
                       username=username,
                       exc_info=True,
                       error=str(e))
        raise ResolveError(f"Erreur inattendue: {str(e)}")
