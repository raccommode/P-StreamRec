"""
Fonctions utilitaires pour P-StreamRec
"""

import re
from typing import Optional


def slugify(text: str) -> str:
    """
    Convertit un texte en slug valide pour nom de fichier
    
    Args:
        text: Texte à convertir
        
    Returns:
        Slug valide (lettres, chiffres, tirets, underscores)
    """
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text.strip('_')


def extract_username(url: str) -> Optional[str]:
    """
    Extrait le nom d'utilisateur d'une URL Chaturbate
    
    Args:
        url: URL complète ou username simple
        
    Returns:
        Username ou None si invalide
    """
    # Si c'est déjà juste un username
    if not url.startswith('http'):
        return slugify(url)
    
    # Extraire depuis URL
    match = re.search(r'chaturbate\.com/([^/?\s]+)', url)
    if match:
        return slugify(match.group(1))
    
    return None


def format_bytes(bytes_value: int) -> str:
    """
    Formate une taille en bytes de manière lisible
    
    Args:
        bytes_value: Taille en bytes
        
    Returns:
        Chaîne formatée (ex: "1.5 GB", "256.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Formate une durée en secondes de manière lisible
    
    Args:
        seconds: Durée en secondes
        
    Returns:
        Chaîne formatée (ex: "2h 30m 15s", "45m 30s")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def validate_m3u8_url(url: str) -> bool:
    """
    Vérifie si une URL est une URL M3U8 valide
    
    Args:
        url: URL à vérifier
        
    Returns:
        True si valide, False sinon
    """
    if not url:
        return False
    
    # Doit commencer par http(s)
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Doit se terminer par .m3u8
    if not url.endswith('.m3u8'):
        return False
    
    return True
