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
    Utilise l'API puis fallback sur HTML si nécessaire.
    """
    logger.subsection(f"🔍 Résolution M3U8 - {username}")
    
    username = username.strip().lower()
    if not username or not re.match(r'^[a-z0-9_]+$', username):
        logger.error("Nom d'utilisateur invalide", username=username)
        raise ResolveError("Nom d'utilisateur invalide")
    
    logger.debug("Username validé", username=username)
    
    try:
        # MÉTHODE 1: Essayer l'API Chaturbate d'abord (meilleure qualité)
        api_url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
        logger.progress("Tentative via API Chaturbate", username=username, url=api_url)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://chaturbate.com/",
        }
        
        api_resp = requests.get(api_url, headers=headers, timeout=10)
        if api_resp.status_code == 200:
            api_data = api_resp.json()
            
            # Logger TOUS les champs HLS disponibles pour debugging
            hls_fields = {k: v[:80] if isinstance(v, str) else v for k, v in api_data.items() if 'hls' in k.lower() or 'm3u8' in str(v).lower()}
            logger.debug("Champs HLS disponibles dans API", username=username, hls_fields=hls_fields)
            
            # Chercher la meilleure qualité disponible
            # Tester plusieurs noms possibles pour haute qualité
            best_m3u8 = None
            quality_source = None
            
            # Priorité des sources (de meilleure à moins bonne)
            quality_checks = [
                ('hls_source_hd', 'HD'),
                ('hls_source_high', 'High'),
                ('hls_source_720p', '720p'),
                ('hls_source_1080p', '1080p'),
                ('hls_source', 'Standard')
            ]
            
            for field_name, quality_label in quality_checks:
                if api_data.get(field_name):
                    best_m3u8 = api_data[field_name]
                    quality_source = f"{field_name} ({quality_label})"
                    logger.success("M3U8 trouvé via API", username=username, source=quality_source, url_preview=best_m3u8[:80])
                    break
            
            if best_m3u8:
                # ASTUCE: Si c'est un playlist.m3u8, charger et prendre la dernière ligne (meilleure qualité)
                if 'playlist.m3u8' in best_m3u8:
                    try:
                        logger.debug("Playlist M3U8 détecté, extraction meilleure qualité", username=username)
                        playlist_resp = requests.get(best_m3u8, headers=headers, timeout=10)
                        if playlist_resp.status_code == 200:
                            lines = playlist_resp.text.strip().split('\n')
                            # La dernière ligne non-vide qui n'est pas un commentaire est la meilleure qualité
                            for line in reversed(lines):
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    # C'est un chemin relatif, construire l'URL complète
                                    base_url = best_m3u8.rsplit('/', 1)[0]
                                    best_m3u8 = f"{base_url}/{line}"
                                    logger.success("Meilleure qualité extraite du playlist", 
                                                 username=username, 
                                                 final_url=best_m3u8[:80])
                                    break
                    except Exception as e:
                        logger.warning("Impossible d'extraire meilleure qualité du playlist, utilisation URL brute",
                                     username=username, error=str(e))
                
                logger.success("M3U8 résolu via API", username=username, m3u8_url=best_m3u8[:80])
                return best_m3u8
            
            logger.debug("Pas de HLS dans API, fallback sur HTML", username=username)
        
        # MÉTHODE 2: Fallback sur parsing HTML
        url = f"https://chaturbate.com/{username}/"
        logger.progress("Fallback: Récupération page HTML", username=username, url=url)
        
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
