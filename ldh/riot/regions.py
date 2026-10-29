# Copiado sin cambios de Coach AI (coach/regions.py) el 2026-10-29.
"""Plataformas de LoL y su ruteo regional."""

# platform host -> routing value de match-v5 / account-v1
PLATFORM_TO_ROUTING = {
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "na1": "americas",
    "eun1": "europe",
    "euw1": "europe",
    "me1": "europe",
    "ru": "europe",
    "tr1": "europe",
    "jp1": "asia",
    "kr": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

PLATFORMS = sorted(PLATFORM_TO_ROUTING)


def routing_for(platform: str) -> str:
    platform = platform.lower().strip()
    try:
        return PLATFORM_TO_ROUTING[platform]
    except KeyError:
        raise ValueError(
            f"Plataforma desconocida: {platform!r}. Validas: {', '.join(PLATFORMS)}"
        ) from None


def platform_host(platform: str) -> str:
    return f"https://{platform.lower().strip()}.api.riotgames.com"


def routing_host(platform: str) -> str:
    return f"https://{routing_for(platform)}.api.riotgames.com"
