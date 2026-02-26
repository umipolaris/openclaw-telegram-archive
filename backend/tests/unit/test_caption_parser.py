from app.services.caption_parser import parse_caption


def test_caption_priority_title_description_and_meta():
    caption = "주간 회의\n진행상황 공유\n#분류:회의\n#날짜:2026-02-24\n#태그:alpha,beta"
    parsed = parse_caption(caption, "a.pdf")

    assert parsed.title == "주간 회의"
    assert parsed.description == "진행상황 공유"
    assert parsed.explicit_category == "회의"
    assert parsed.explicit_date == "2026-02-24"
    assert parsed.explicit_tags == ["alpha", "beta"]


def test_caption_fallback_to_filename():
    parsed = parse_caption(None, "20260224_report_final.pdf")
    assert parsed.title == "20260224 report final"
    assert parsed.description == ""


def test_caption_normalizes_escaped_newline_sequences():
    caption = "문서 제목\\n설명 1\\n#분류:회의\\n#날짜:2026-02-24"
    parsed = parse_caption(caption, "x.pdf")

    assert parsed.title == "문서 제목"
    assert parsed.description == "설명 1"
    assert parsed.explicit_category == "회의"
