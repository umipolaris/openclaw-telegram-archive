from app.services.archive_set_parser import extract_structured_fields, revision_rank


def test_extract_structured_fields_priority_from_tags():
    fields = extract_structured_fields(
        tags=["set:dcp", "dockey:document-control-procedure", "rev:2", "kind:main", "lang:ko"],
        title="Document Control Procedure Rev.2",
        category="절차서",
    )

    assert fields["set_key"] == "dcp"
    assert fields["document_key"] == "document-control-procedure"
    assert fields["revision"] == "2"
    assert fields["kind"] == "main"
    assert fields["language"] == "ko"


def test_extract_structured_fields_fallback_when_tags_missing():
    fields = extract_structured_fields(
        tags=["기타"],
        title="General Arrangement Drawing Rev.0",
        category="도면",
    )

    assert fields["set_key"] == "__unmapped__"
    assert fields["document_key"] == "General Arrangement Drawing"
    assert fields["revision"] == "0"
    assert fields["kind"] == "도면"


def test_revision_rank_for_numeric_and_draft():
    assert revision_rank("5") == 5
    assert revision_rank("rev.12") == 12
    assert revision_rank("draft") == -2
    assert revision_rank(None) == -1
