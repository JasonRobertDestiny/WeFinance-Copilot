"""Tests for the file-based storage helpers."""

from __future__ import annotations

import threading

import pytest

from utils.storage import (
    STORAGE_FILE,
    FileStorageBackend,
    clear_all_storage,
    load_from_storage,
    save_to_storage,
)


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure each test leaves no persisted residue."""
    yield
    clear_all_storage()


def test_save_and_load_simple_data():
    """Persist and restore a primitive value."""
    assert save_to_storage("test_key", "test_value")
    assert load_from_storage("test_key") == "test_value"


def test_save_and_load_complex_data():
    """Persist nested structures."""
    complex_payload = {
        "transactions": [
            {"date": "2025-01-01", "merchant": "测试", "amount": 100.0}
        ],
        "budget": 5000.0,
        "tags": ["餐饮", "购物"],
    }
    assert save_to_storage("complex", complex_payload)
    assert load_from_storage("complex") == complex_payload


def test_load_nonexistent_key_returns_default():
    """Unknown keys should fall back to provided defaults."""
    assert load_from_storage("missing_key", "default") == "default"


def test_clear_all_storage_removes_keys():
    """Clear helper removes every stored key."""
    save_to_storage("key1", "value1")
    save_to_storage("key2", "value2")
    assert clear_all_storage()
    assert load_from_storage("key1") is None
    assert load_from_storage("key2") is None


def test_storage_file_creation():
    """Saving via the default backend should create files/directories."""
    if STORAGE_FILE.exists():
        STORAGE_FILE.unlink()
    assert save_to_storage("test_creation", "value")
    assert STORAGE_FILE.exists()
    assert STORAGE_FILE.parent.exists()


def test_storage_corruption_returns_default(tmp_path):
    """Gracefully handle malformed JSON payloads."""
    temp_file = tmp_path / "broken.json"
    temp_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file.write_text("{invalid json}", encoding="utf-8")
    backend = FileStorageBackend(storage_file=temp_file)
    assert backend.load("whatever", "default") == "default"


def test_load_default_after_external_corruption():
    """Global loader should not crash when file is corrupted."""
    STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_FILE.write_text("{invalid json}", encoding="utf-8")
    assert load_from_storage("any_key", "default") == "default"


def test_concurrent_writes_do_not_crash():
    """Parallel writes should not raise errors."""
    def write_data(value):
        save_to_storage("concurrent_key", value)

    threads = [threading.Thread(target=write_data, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert load_from_storage("concurrent_key") in range(10)
