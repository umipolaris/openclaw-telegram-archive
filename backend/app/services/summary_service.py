from app.services.caption_parser import CaptionParseResult


def build_summary(
    parsed_caption: CaptionParseResult,
    filename: str,
    mime_type: str,
    extracted_text: str | None = None,
    extracted_sheets: list[str] | None = None,
) -> str:
    if parsed_caption.caption_raw.strip():
        text = parsed_caption.caption_raw.strip()
        return text[:500]

    if mime_type.startswith("application/vnd.openxmlformats-officedocument.spreadsheetml"):
        sheets = extracted_sheets or []
        if sheets:
            return f"시트: {', '.join(sheets[:10])}"

    if mime_type in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        if extracted_text and extracted_text.strip():
            return extracted_text.strip()[:500]

    return f"파일 요약 없음 ({filename})"
