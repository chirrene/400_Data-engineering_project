"""Unit tests for the contract adapters and placeholders (no Airflow needed)."""
from __future__ import annotations

import sys
import types

import pytest

from src.pipeline import contracts, placeholders


def _fake_module(monkeypatch, name, **funcs):
    """Install a fake teammate module (and its parent packages) for one test."""
    parts = name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            monkeypatch.setitem(sys.modules, parent, types.ModuleType(parent))
    module = types.ModuleType(name)
    for key, value in funcs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setenv("NASA_OFFLINE", "0")


# ------------------------------------------------------------ resolution
def test_missing_module_falls_back_to_placeholder(monkeypatch):
    monkeypatch.setitem(sys.modules, "src.database.queries", None)  # import -> error
    monkeypatch.setattr(contracts, "_find", lambda *_: None)
    func, source = contracts.resolve("run_quality_checks")
    assert source == contracts.PLACEHOLDER
    assert func is placeholders.run_quality_checks


def test_broken_teammate_import_is_not_hidden(monkeypatch):
    import importlib

    def fake_import(name):
        raise ModuleNotFoundError("No module named 'dotenv'", name="dotenv")

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(ModuleNotFoundError):
        contracts.resolve("fetch_library")


# -------------------------------------------------------------- adapters
def test_fetch_apod_without_start_date_uses_backfill(monkeypatch):
    _fake_module(monkeypatch, "src.apis.apod_client", fetch_apod=lambda: [{"date": "x"}])
    func, source = contracts.resolve("fetch_apod")
    assert source == contracts.PLACEHOLDER
    assert func is placeholders.fetch_apod


def test_fetch_apod_with_start_date_is_used(monkeypatch):
    calls = []

    def fetch_apod(start_date):
        calls.append(start_date)
        return []

    _fake_module(monkeypatch, "src.apis.apod_client", fetch_apod=fetch_apod)
    func, source = contracts.resolve("fetch_apod")
    assert source == "src.apis.apod_client"
    func("2020-01-01")
    assert calls == ["2020-01-01"]


def test_offline_mode_never_calls_teammate_fetchers(monkeypatch):
    monkeypatch.setenv("NASA_OFFLINE", "1")
    _fake_module(monkeypatch, "src.apis.apod_client", fetch_apod=lambda start_date: 1 / 0)
    _, source = contracts.resolve("fetch_apod")
    assert source == contracts.PLACEHOLDER


def test_fetch_library_adapter_unwraps_and_tags(monkeypatch):
    seen = {}

    def fetch_nasa_library_pages(query, max_pages, start_year, end_year):
        seen.update(query=query, max_pages=max_pages, start=start_year, end=end_year)
        return {"collection": {"items": [{"data": [{"nasa_id": "A"}]}]}}

    _fake_module(
        monkeypatch,
        "src.apis.image_library_client",
        fetch_nasa_library_pages=fetch_nasa_library_pages,
    )
    func, source = contracts.resolve("fetch_library")
    assert source == "src.apis.image_library_client"
    items = func("nebula", 2020, 2026, 3)
    assert seen == {"query": "nebula", "max_pages": 3, "start": 2020, "end": 2026}
    assert items == [{"data": [{"nasa_id": "A"}], "_keyword": "nebula"}]


def test_normalize_adapters_batch_and_keep_keyword(monkeypatch):
    _fake_module(
        monkeypatch,
        "src.processing.normalize",
        normalize_apod=lambda r: {"source_id": r["post_id"]},
        normalize_nasa_library=lambda raw: [
            {"source_id": i["data"][0]["nasa_id"]} for i in raw["collection"]["items"]
        ],
    )
    apod, _ = contracts.resolve("normalize_apod")
    assert apod([{"post_id": 1}, {"post_id": 2}]) == [{"source_id": 1}, {"source_id": 2}]

    lib, source = contracts.resolve("normalize_library")
    assert source == "src.processing.normalize"
    rows = lib(
        [
            {"_keyword": "mars", "data": [{"nasa_id": "A"}]},
            {"_keyword": "galaxy", "data": [{"nasa_id": "B"}]},
        ]
    )
    assert sorted((r["source_id"], r["search_keyword"]) for r in rows) == [
        ("A", "mars"),
        ("B", "galaxy"),
    ]


def test_validate_adapter_drops_invalid(monkeypatch):
    _fake_module(
        monkeypatch,
        "src.processing.validate",
        validate_record=lambda r: {"is_valid": bool(r.get("title"))},
        find_duplicate_records=lambda rs: rs[1:] if len(rs) > 1 else [],
    )
    func, _ = contracts.resolve("validate_records")
    valid, metrics = func([{"title": "a"}, {"title": None}, {"title": "a"}])
    assert len(valid) == 2
    assert metrics == {"invalid_dropped": 1, "duplicates_in_batch": 1}


# ---------------------------------------------------------- placeholders
def test_placeholder_normalize_apod_unified_schema():
    rows = placeholders.normalize_apod(
        [
            {
                "post_id": 7,
                "date": "2024-12-07",
                "title": "APOD: 2024 December 7 – Rocket Engine Fireplace",
                "media_type": None,
                "explanation": "<strong>Explanation:</strong> A <a href='x'>fire</a>&nbsp;place",
                "credit": "<a href='y'>Jane Doe</a>",
            }
        ]
    )
    row = rows[0]
    assert row["source_api"] == "apod" and row["source_id"] == "7"
    assert row["title"] == "Rocket Engine Fireplace"
    assert row["explanation"] == "A fire place"
    assert row["credit"] == "Jane Doe"


def test_placeholder_normalize_library_splits_packed_keywords():
    rows = placeholders.normalize_library(
        [
            {
                "_keyword": "galaxy",
                "data": [{"nasa_id": "X1", "title": "T", "keywords": ["a, b, c"]}],
                "links": [{"rel": "preview", "href": "thumb.jpg"}],
            },
            {"_keyword": "galaxy", "data": [{"title": "no id"}]},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["keywords"] == ["a", "b", "c"]
    assert rows[0]["image_url"] == "thumb.jpg"
    assert rows[0]["search_keyword"] == "galaxy"
