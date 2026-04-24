"""Tests for KeyStore encrypted storage."""
import pytest
from pathlib import Path
from src.utils.keystore import KeyStore


@pytest.fixture
def ks(tmp_path):
    return KeyStore(str(tmp_path / "test_keystore.db"), salt=b"test_salt_32bytes_padding_here!!")


def test_set_and_get_key(ks):
    ks.set_key("api_key", "super_secret_value", master_pwd="master123")
    retrieved = ks.get_key("api_key", master_pwd="master123")
    assert retrieved == "super_secret_value"


def test_wrong_password_fails(ks):
    ks.set_key("api_key", "secret", master_pwd="correct_pwd")
    with pytest.raises(Exception):
        ks.get_key("api_key", master_pwd="wrong_pwd")


def test_missing_key_raises(ks):
    with pytest.raises(KeyError):
        ks.get_key("nonexistent", master_pwd="any")


def test_list_keys(ks):
    ks.set_key("key1", "v1", "pwd")
    ks.set_key("key2", "v2", "pwd")
    keys = ks.list_keys()
    assert "key1" in keys
    assert "key2" in keys


def test_delete_key(ks):
    ks.set_key("key1", "v1", "pwd")
    ks.delete_key("key1")
    with pytest.raises(KeyError):
        ks.get_key("key1", "pwd")


def test_overwrite_key(ks):
    ks.set_key("k", "old", "pwd")
    ks.set_key("k", "new", "pwd")
    assert ks.get_key("k", "pwd") == "new"
