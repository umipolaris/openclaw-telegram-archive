from app.services.summary_service import build_summary_from_document_fields


def test_build_summary_from_document_fields_strips_html_and_decodes_entities():
    summary = build_summary_from_document_fields(
        "제목",
        "<p>첫 줄&nbsp;내용</p><ul><li>항목A</li><li>항목B</li></ul>",
    )

    assert summary == "첫 줄 내용 항목A 항목B"


def test_build_summary_from_document_fields_falls_back_to_title():
    summary = build_summary_from_document_fields("문서 제목", "   ")

    assert summary == "문서 제목"


def test_build_summary_from_document_fields_truncates_to_max_length():
    summary = build_summary_from_document_fields("제목", "<p>" + ("A" * 500) + "</p>", max_length=120)

    assert len(summary) == 120
    assert summary == "A" * 120
