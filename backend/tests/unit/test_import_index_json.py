from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from scripts.import_index_json import (
    _build_caption,
    _build_source_ref,
    _load_legacy_rows,
    _parse_datetime,
    _parse_tags,
    _resolve_legacy_file_path,
    _resolve_source,
)


def test_load_legacy_rows_supports_items_key(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text('{"items":[{"id":"a"},{"id":"b"}]}', encoding="utf-8")

    rows = _load_legacy_rows(index_path)
    assert len(rows) == 2
    assert rows[0]["id"] == "a"
    assert rows[1]["id"] == "b"


def test_load_legacy_rows_supports_root_array(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text('[{"id":"x"},{"id":"y"}]', encoding="utf-8")

    rows = _load_legacy_rows(index_path)
    assert [row["id"] for row in rows] == ["x", "y"]


def test_resolve_source_auto_and_fallback():
    source, used_fallback = _resolve_source("telegram", "auto")
    assert source.value == "telegram"
    assert used_fallback is False

    source, used_fallback = _resolve_source("legacy_unknown", "auto")
    assert source.value == "manual"
    assert used_fallback is True


def test_build_source_ref_priority():
    assert _build_source_ref({"source_ref": "manual:123"}, source_ref_prefix="legacy", item_id="i1") == "manual:123"
    assert _build_source_ref({"message_id": "999"}, source_ref_prefix="legacy", item_id="i1") == "msg:999"
    assert _build_source_ref({}, source_ref_prefix="legacy", item_id="i1") == "legacy:i1"


def test_resolve_legacy_file_path_with_automation_prefix(tmp_path):
    legacy_root = tmp_path / "automation_data"
    files_dir = legacy_root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    file_path = files_dir / "example.pdf"
    file_path.write_bytes(b"dummy")

    index_path = legacy_root / "index.json"
    index_path.write_text('{"items":[]}', encoding="utf-8")

    resolved, attempts = _resolve_legacy_file_path(
        "automation/data/files/example.pdf",
        index_json_path=index_path,
        legacy_root=legacy_root,
    )
    assert resolved == file_path
    assert len(attempts) > 0


def test_build_caption_prefers_existing_caption_raw():
    raw = "제목\n설명\n#분류:회의"
    assert _build_caption("ignored", "ignored", "ignored", "2026-02-25", ["태그"], raw) == raw


def test_build_caption_composes_expected_lines():
    caption = _build_caption(
        title="문서 제목",
        description="문서 설명",
        category="회의",
        event_date_text="2026-02-25",
        tags=["alpha", "beta"],
        caption_raw=None,
    )
    assert "문서 제목" in caption
    assert "문서 설명" in caption
    assert "#분류:회의" in caption
    assert "#날짜:2026-02-25" in caption
    assert "#태그:alpha,beta" in caption


def test_parse_tags_handles_list_and_csv():
    assert _parse_tags(["A", " B ", "A"]) == ["A", "B"]
    assert _parse_tags("A, B ; C\nD") == ["A", "B", "C", "D"]


def test_parse_datetime_supports_iso_and_z_suffix():
    iso_with_z = _parse_datetime("2026-02-25T08:12:13Z")
    assert iso_with_z is not None
    assert iso_with_z.tzinfo is not None

    naive = _parse_datetime("2026-02-25T08:12:13")
    assert naive is not None
    assert naive.tzinfo is not None


def test_resolve_legacy_file_path_returns_none_for_missing(tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir(parents=True, exist_ok=True)
    index_path = legacy_root / "index.json"
    index_path.write_text("{}", encoding="utf-8")

    resolved, attempts = _resolve_legacy_file_path(
        "automation/data/files/missing.pdf",
        index_json_path=index_path,
        legacy_root=legacy_root,
    )
    assert resolved is None
    assert isinstance(attempts, list)
    assert all(isinstance(path, Path) for path in attempts)
