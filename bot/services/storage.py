# Copiado de LDH Stats PR (bot/services/storage.py) el 2026-10-29.
"""Simple JSON-based persistent storage for guild settings and role configs.

Todo lo que el bot escribe en runtime (settings por guild, roles, cachés de emojis,
sugerencias) vive en DATA_DIR. En Railway el disco del contenedor es efímero (se
borra en cada redeploy), así que DATA_DIR apunta al volumen persistente:

1. ``BOT_DATA_DIR`` si está definida (override explícito).
2. ``RAILWAY_VOLUME_MOUNT_PATH``, que Railway define solo cuando el servicio tiene
   un volumen montado (hoy ``/data``).
3. ``bot/data`` como fallback para desarrollo local.

Los archivos bundled de solo lectura (p.ej. ``tips.json``) siguen en
BUNDLED_DATA_DIR, que viaja con el código.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

BUNDLED_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATA_DIR = (
    os.getenv("BOT_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or BUNDLED_DATA_DIR
)


def data_path(filename: str) -> str:
    """Ruta absoluta de un archivo de datos persistente dentro de DATA_DIR."""
    return os.path.join(DATA_DIR, filename)


def load_json(path: str, default):
    """Lee un .json; devuelve *default* si no existe o está corrupto."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s — starting fresh.", path, e)
    return default


def save_json(path: str, data) -> None:
    """Escritura atómica (temp + replace) para no corromper el .json ante un crash."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        logger.error("Failed to save %s: %s", path, e)


class JSONStorage:
    """Read/write a JSON file as a dict, with auto-save."""

    def __init__(self, filename: str):
        self.path = data_path(filename)
        data = load_json(self.path, {})
        self._data: dict = data if isinstance(data, dict) else {}

    def save(self) -> None:
        """Write current data to disk."""
        save_json(self.path, self._data)

    def get(self, key: str, default=None):
        return self._data.get(str(key), default)

    def set(self, key: str, value) -> None:
        self._data[str(key)] = value
        self.save()

    def delete(self, key: str) -> None:
        self._data.pop(str(key), None)
        self.save()

    def all(self) -> dict:
        return self._data.copy()
