from app.services.archive_set_parser import infer_structured_tags


def test_infer_dcp_set_and_revision_and_main_kind():
    tags = infer_structured_tags(
        title="Document Control Procedure rev.2",
        description="운영 절차 문서",
        filename="dcp_rev2.pdf",
        existing_tags=[],
    )

    assert "set:dcp" in tags
    assert "dockey:document-control-procedure" in tags
    assert "rev:2" in tags
    assert "kind:main" in tags


def test_infer_general_arrangement_drawing_draft():
    tags = infer_structured_tags(
        title="General Arrangement Drawing Draft 버전",
        description="",
        filename="X42-77-900-XYZ Rev.0.pdf",
        existing_tags=[],
    )

    assert "set:general-arrangement-drawing" in tags
    assert "dockey:general-arrangement-drawing" in tags
    assert "rev:0" in tags
    assert "kind:drawing" in tags


def test_respect_existing_structured_tags():
    tags = infer_structured_tags(
        title="Document Control Procedure rev.1",
        description="한글 번역본",
        filename="dcp_rev1_ko.docx",
        existing_tags=["set:custom", "dockey:custom-doc", "rev:1", "kind:manual", "lang:ko"],
    )

    assert tags == []
