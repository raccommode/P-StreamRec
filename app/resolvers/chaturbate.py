import re
import requests
from .base import ResolveError


def resolve_m3u8(username: str) -> str:
    """
    Résolveur Chaturbate ultra-simplifié et fiable.
    Extrait directement le M3U8 depuis la page HTML.
    """
    print(f"\n{'='*60}")
    print(f"🔍 DÉBUT RÉSOLUTION M3U8 pour: {username}")
    print(f"{'='*60}")
    
    username = username.strip().lower()
    if not username or not re.match(r'^[a-z0-9_]+$', username):
        print(f"❌ Nom d'utilisateur invalide: {username}")
        raise ResolveError("Nom d'utilisateur invalide")
    
    print(f"✅ Username validé: {username}")
    
    try:
        # Récupérer la page HTML
        url = f"https://chaturbate.com/{username}/"
        print(f"📡 Récupération de la page: {url}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"📥 Réponse HTTP: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ Erreur HTTP {resp.status_code}")
            raise ResolveError(f"Impossible d'accéder à la page (HTTP {resp.status_code})")
        
        html = resp.text
        print(f"📄 Page HTML récupérée ({len(html)} caractères)")
        
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
        
        print(f"🔎 Recherche du M3U8 avec {len(m3u8_patterns)} patterns...")
        
        for i, pattern in enumerate(m3u8_patterns, 1):
            print(f"   Pattern {i}/{len(m3u8_patterns)}: {pattern[:60]}...")
            matches = re.findall(pattern, html, re.IGNORECASE)
            
            if matches:
                print(f"   ✅ {len(matches)} match(es) trouvé(s) avec pattern {i}")
                # Prendre le premier match (ou le groupe capturé)
                if isinstance(matches[0], tuple):
                    # Si c'est un tuple (groupes capturés), prendre le dernier élément non vide
                    m3u8_url = [g for g in matches[0] if g and 'http' in g][0] if matches[0] else matches[0][-1]
                else:
                    m3u8_url = matches[0]
                
                # Nettoyer l'URL
                m3u8_url = m3u8_url.replace("\\/", "/").replace("\\", "")
                
                # Décoder les entités Unicode (u002D = -, u0022 = ", etc.)
                import html
                m3u8_url = html.unescape(m3u8_url)
                
                # Remplacer les codes Unicode hexadécimaux
                import re as regex_module
                def decode_unicode(match):
                    return chr(int(match.group(1), 16))
                m3u8_url = regex_module.sub(r'u([0-9a-fA-F]{4})', decode_unicode, m3u8_url)
                
                # Supprimer les caractères parasites à la fin
                m3u8_url = m3u8_url.rstrip('",;: \t\n\r')
                
                print(f"   🎯 M3U8 candidat: {m3u8_url}")
                
                if m3u8_url.startswith("http") and ".m3u8" in m3u8_url:
                    print(f"\n{'='*60}")
                    print(f"✅ M3U8 TROUVÉ: {m3u8_url}")
                    print(f"{'='*60}\n")
                    return m3u8_url
                else:
                    print(f"   ⚠️ URL invalide, continue...")
            else:
                print(f"   ❌ Aucun match avec pattern {i}")
        
        # Si pas trouvé, vérifier si hors ligne
        print(f"\n⚠️ Aucun M3U8 trouvé, vérification du statut...")
        
        if "offline" in html.lower():
            print(f"❌ Utilisateur hors ligne (détecté dans HTML)")
            raise ResolveError(f"{username} est hors ligne")
        
        # Debug: afficher un extrait du HTML
        print(f"\n📋 Extrait HTML (premiers 500 chars):")
        print(html[:500])
        print(f"\n📋 Recherche 'hls' dans HTML (case-insensitive):")
        html_lower = html.lower()
        hls_occurrences = [i for i in range(len(html_lower)) if html_lower.startswith('hls', i)][:10]
        if hls_occurrences:
            for idx in hls_occurrences:
                print(f"   Position {idx}: ...{html[max(0,idx-20):idx+150]}...")
        else:
            print(f"   ❌ Aucune occurrence de 'hls' trouvée")
        
        # Chercher aussi 'm3u8' directement
        print(f"\n📋 Recherche 'm3u8' dans HTML:")
        m3u8_occurrences = [i for i in range(len(html_lower)) if html_lower.startswith('m3u8', i)][:5]
        if m3u8_occurrences:
            for idx in m3u8_occurrences:
                print(f"   Position {idx}: ...{html[max(0,idx-50):idx+100]}...")
        else:
            print(f"   ❌ Aucune occurrence de 'm3u8' trouvée")
        
        print(f"\n❌ M3U8 non trouvé")
        raise ResolveError(f"Impossible de trouver le flux M3U8 pour {username}")
        
    except requests.RequestException as e:
        print(f"❌ Erreur réseau: {e}")
        raise ResolveError(f"Erreur réseau: {str(e)}")
    except ResolveError:
        raise
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()
        raise ResolveError(f"Erreur inattendue: {str(e)}")
