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
        
        # Chercher le M3U8 avec regex simple
        m3u8_patterns = [
            r'"(https://[^"]*\.m3u8[^"]*)"',
            r"'(https://[^']*\.m3u8[^']*)'",
            r'hls_source["\s:]+(["\'])(https://[^"\']+\.m3u8[^"\']*)\1',
        ]
        
        print(f"🔎 Recherche du M3U8 avec {len(m3u8_patterns)} patterns...")
        
        for i, pattern in enumerate(m3u8_patterns, 1):
            print(f"   Pattern {i}/{len(m3u8_patterns)}: {pattern[:50]}...")
            matches = re.findall(pattern, html)
            
            if matches:
                print(f"   ✅ {len(matches)} match(es) trouvé(s) avec pattern {i}")
                # Prendre le premier match (ou le groupe capturé)
                m3u8_url = matches[0] if isinstance(matches[0], str) else matches[0][-1]
                m3u8_url = m3u8_url.replace("\\/", "/")
                
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
        print(f"\n📋 Recherche 'hls' dans HTML:")
        hls_occurrences = [i for i in range(len(html)) if html.startswith('hls', i)][:5]
        for idx in hls_occurrences:
            print(f"   Position {idx}: {html[idx:idx+100]}")
        
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
