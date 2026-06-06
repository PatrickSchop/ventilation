"""Lock current behavior of Configuration: type inference/mismatch,
dotted getValue traversal, missing-file silent, save/load round-trip.

Note: load() with a malformed JSON currently raises JSONDecodeError (L5).
The xfail test for that is added in Phase 4.
"""

import json
import os
import pytest
from Configuration import Configuration, _Configuration, ElementGroup, Element


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """Configuration is a module-level singleton; reset between tests."""
    fresh = _Configuration()
    fresh._name = "Configuration"
    fresh._items = {}
    monkeypatch.setattr("Configuration.Configuration", fresh)
    yield


class TestAddElement:
    def test_type_inferred_from_default_int(self):
        g = ElementGroup()
        g.addElement("count", defaultValue=1)
        assert g._items["count"]._type is int
        assert g._items["count"]._value == 1

    def test_type_inferred_from_default_str(self):
        g = ElementGroup()
        g.addElement("name", defaultValue="foo")
        assert g._items["name"]._type is str
        assert g._items["name"]._value == "foo"

    def test_explicit_type(self):
        g = ElementGroup()
        g.addElement("port", valueType=int, defaultValue=1883)
        assert g._items["port"]._type is int
        assert g._items["port"]._value == 1883

    def test_type_mismatch_raises(self):
        el = Element()
        el._name = "port"
        el._type = int
        el._value = 0
        with pytest.raises(Exception):
            el.setValue("not an int")


class TestGetValue:
    def test_top_level_value(self):
        g = ElementGroup()
        g.addElement("server", defaultValue="home")
        assert g.getValue("server") == "home"

    def test_dotted_path(self):
        g = ElementGroup()
        mqtt = g.addElementGroup("mqtt")
        mqtt.addElement("server", defaultValue="home")
        assert g.getValue("mqtt.server") == "home"

    def test_deep_dotted(self):
        outer = ElementGroup()
        mid = outer.addElementGroup("a")
        inner = mid.addElementGroup("b")
        inner.addElement("c", defaultValue=42)
        assert outer.getValue("a.b.c") == 42

    def test_missing_returns_none(self):
        g = ElementGroup()
        assert g.getValue("missing") is None
        assert g.getValue("missing.deeper") is None


class TestLoad:
    def test_missing_file_silent(self, tmp_path):
        fresh = _Configuration()
        fresh._name = "Configuration"
        # Should not raise
        fresh.load(str(tmp_path / "does-not-exist.json"))
        assert fresh._items == {}

    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "config.json")
        fresh = _Configuration()
        fresh._name = "Configuration"
        mqtt = fresh.addElementGroup("mqtt")
        mqtt.addElement("server", defaultValue="home")
        mqtt.addElement("port", valueType=int, defaultValue=1883)

        fresh.save(path)
        assert os.path.exists(path)

        loaded = _Configuration()
        loaded._name = "Configuration"
        mqtt2 = loaded.addElementGroup("mqtt")
        mqtt2.addElement("server", defaultValue="x")
        mqtt2.addElement("port", valueType=int, defaultValue=0)
        loaded.load(path)
        assert loaded.getValue("mqtt.server") == "home"
        assert loaded.getValue("mqtt.port") == 1883
