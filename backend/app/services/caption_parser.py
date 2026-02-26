import re
from dataclasses import dataclass

_META_PATTERNS = {
    "category": re.compile(r"^#분류\s*:\s*(.+)$", re.IGNORECASE),
    "date": re.compile(r"^#날짜\s*:\s*(.+)$", re.IGNORECASE),
    "tags": re.compile(r"^#태그\s*:\s*(.+)$", re.IGNORECASE),
}


@dataclass
class CaptionParseResult:
    title: str
    description: str
    caption_raw: str
    explicit_category: str | None
    explicit_date: str | None
    explicit_tags: list[str]


def sanitize_filename(filename: str) -> str:
    name = filename.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
    stem = name.rsplit(".", maxsplit=1)[0] if "." in name else name
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Untitled"


def _normalize_caption_text(caption: str) -> str:
    # Manual multipart usage occasionally sends escaped newlines (`\n`) as plain text.
    # Normalize only when real newline characters are absent.
    if "\n" not in caption and "\\n" in caption:
        return caption.replace("\\r\\n", "\n").replace("\\n", "\n")
    return caption


def parse_caption(caption: str | None, filename: str) -> CaptionParseResult:
    if caption and caption.strip():
        normalized_caption = _normalize_caption_text(caption)
        lines = [line.rstrip() for line in normalized_caption.splitlines()]
        non_empty = [line for line in lines if line.strip()]
        title = non_empty[0].strip() if non_empty else sanitize_filename(filename)
        body_lines = non_empty[1:] if len(non_empty) > 1 else []
    else:
        title = sanitize_filename(filename)
        body_lines = []

    explicit_category: str | None = None
    explicit_date: str | None = None
    explicit_tags: list[str] = []

    cleaned_desc: list[str] = []
    for line in body_lines:
        s = line.strip()
        m = _META_PATTERNS["category"].match(s)
        if m:
            explicit_category = m.group(1).strip()
            continue
        m = _META_PATTERNS["date"].match(s)
        if m:
            explicit_date = m.group(1).strip()
            continue
        m = _META_PATTERNS["tags"].match(s)
        if m:
            explicit_tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
            continue
        cleaned_desc.append(line)

    description = "\n".join(cleaned_desc).strip()

    return CaptionParseResult(
        title=title,
        description=description,
        caption_raw=caption or "",
        explicit_category=explicit_category,
        explicit_date=explicit_date,
        explicit_tags=explicit_tags,
    )
