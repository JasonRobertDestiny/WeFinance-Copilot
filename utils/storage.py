"""File-based persistence utilities for Streamlit session data."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STORAGE_PREFIX = "wefinance_"


def _resolve_storage_file() -> Path:
    """Determine a writable storage path, falling back to the workspace if needed."""
    env_path = os.getenv("WEFINANCE_STORAGE_FILE")
    if env_path:
        candidate = Path(env_path).expanduser()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    default_path = Path.home() / ".wefinance" / "data.json"
    try:
        default_path.parent.mkdir(parents=True, exist_ok=True)
        with default_path.open("a", encoding="utf-8"):
            pass
        return default_path
    except PermissionError:
        fallback = Path.cwd() / ".wefinance" / "data.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "Permission denied for %s, falling back to %s",
            default_path.parent,
            fallback,
        )
        return fallback


STORAGE_FILE = _resolve_storage_file()


class StorageBackend:
    """Abstract interface for storage engines."""

    def save(self, key: str, value: Any) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def load(self, key: str, default: Any = None) -> Optional[Any]:  # pragma: no cover
        raise NotImplementedError

    def clear(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class FileStorageBackend(StorageBackend):
    """JSON file-backed storage implementation."""

    def __init__(self, storage_file: Path = STORAGE_FILE):
        self.storage_file = storage_file
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> Dict[str, Any]:
        """Load the entire storage payload."""
        if not self.storage_file.exists():
            return {}
        try:
            with self.storage_file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load storage file: %s", exc)
            return {}

    def _save_all(self, data: Dict[str, Any]) -> bool:
        """Persist the entire payload atomically."""
        try:
            with self.storage_file.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to save storage file: %s", exc)
            return False

    def save(self, key: str, value: Any) -> bool:
        """Persist a single namespaced key."""
        data = self._load_all()
        data[f"{STORAGE_PREFIX}{key}"] = value
        return self._save_all(data)

    def load(self, key: str, default: Any = None) -> Optional[Any]:
        """Load a value by key."""
        data = self._load_all()
        return data.get(f"{STORAGE_PREFIX}{key}", default)

    def clear(self) -> bool:
        """Delete the storage file."""
        try:
            if self.storage_file.exists():
                self.storage_file.unlink()
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to clear storage: %s", exc)
            return False


_storage = FileStorageBackend()


def save_to_storage(key: str, value: Any) -> bool:
    """
    Save a value to persistent storage.

    Args:
        key: Logical key without prefix.
        value: JSON-serialisable payload.
    """
    try:
        return _storage.save(key, value)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to save %s to storage: %s", key, exc)
        return False


def load_from_storage(key: str, default: Any = None) -> Optional[Any]:
    """
    Load a value from persistent storage.

    Args:
        key: Logical key without prefix.
        default: Value returned when the key is missing.
    """
    try:
        return _storage.load(key, default)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load %s from storage: %s", key, exc)
        return default


def clear_all_storage() -> bool:
    """Clear every persisted item."""
    try:
        return _storage.clear()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to clear storage: %s", exc)
        return False
