"""Tests for SymbolRegistry bidirectional mapping."""
import pytest
from src.core.object import SymbolRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    SymbolRegistry.reset()
    yield
    SymbolRegistry.reset()


def test_register_and_lookup():
    sid = SymbolRegistry.get_or_register("000001.SZ")
    assert SymbolRegistry.lookup(sid) == "000001.SZ"


def test_same_symbol_same_id():
    s1 = SymbolRegistry.get_or_register("600036.SH")
    s2 = SymbolRegistry.get_or_register("600036.SH")
    assert s1 == s2


def test_different_symbols_different_ids():
    s1 = SymbolRegistry.get_or_register("000001.SZ")
    s2 = SymbolRegistry.get_or_register("000002.SZ")
    assert s1 != s2


def test_ids_are_sequential():
    ids = [SymbolRegistry.get_or_register(f"sym{i}") for i in range(5)]
    assert ids == list(range(5))


def test_missing_id_raises():
    with pytest.raises(KeyError):
        SymbolRegistry.lookup(9999)
