import html
import re

from app.services.caption_parser import CaptionParseResult

_HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_BLOCK_CLOSE_RE = re.compile(r"</(p|div|li|h[1-6]|blockquote|tr)>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def build_summary_from_document_fields(
    title: str | None,
    description: str | None,
    *,
    max_length: int = 400,
) -> str:
    """Build a short plain-text summary from editable document fields."""
    raw_description = (description or "").strip()
    if raw_description:
        text = _HTML_BREAK_RE.sub("\n", raw_description)
        text = _HTML_BLOCK_CLOSE_RE.sub("\n", text)
        text = _HTML_TAG_RE.sub(" ", text)
        text = html.unescape(text)
        text = _WHITESPACE_RE.sub(" ", text).strip()
        if text:
            return text[:max_length]
        return raw_description[:max_length]

    return (title or "").strip()[:max_length]


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
