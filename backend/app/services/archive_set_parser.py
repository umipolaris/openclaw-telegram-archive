import re

_REV_PATTERN = re.compile(r"(?i)\brev(?:ision)?\.?\s*([a-z0-9\-_]+)\b")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_NON_SLUG_PATTERN = re.compile(r"[^0-9a-z]+")

_SET_RULES = [
    {
        "set": "dcp",
        "dockey": "document-control-procedure",
        "patterns": [r"\bdcp\b", r"document control procedure"],
    },
    {
        "set": "general-arrangement-drawing",
        "dockey": "general-arrangement-drawing",
        "patterns": [r"general arrangement drawing", r"\bgad\b"],
    },
]

_KIND_RULES = [
    ("manual", [r"\bmanual\b", r"매뉴얼"]),
    ("guide", [r"\bguide\b", r"이용 방법", r"문서 교환 시스템 소개"]),
    ("account-list", [r"account list", r"계정 리스트", r"necessaryinformation"]),
    ("drawing", [r"\bdrawing\b", r"도면"]),
    ("main", [r"\bprocedure\b", r"절차"]),
]

_LANG_RULES = [
    ("ko", [r"한글", r"국문", r"korean"]),
    ("en", [r"영문", r"english"]),
]


def normalize_key(value: str) -> str:
    normalized = re.sub(r"[^0-9a-z가-힣]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def humanize_key(value: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", value).strip()
    return cleaned or "세트 미지정"


def extract_revision_from_title(title: str) -> str | None:
    match = _REV_PATTERN.search(title or "")
    return match.group(1) if match else None


def extract_document_key_from_title(title: str) -> str:
    cleaned = _REV_PATTERN.sub("", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Untitled"


def revision_rank(revision: str | None) -> int:
    if not revision:
        return -1
    lowered = revision.strip().lower()
    if lowered in {"draft", "dft"}:
        return -2
    match = re.search(r"(\d+)", lowered)
    return int(match.group(1)) if match else -1


def extract_structured_fields(tags: list[str], title: str, category: str | None) -> dict[str, str | None]:
    set_key: str | None = None
    document_key: str | None = None
    revision: str | None = None
    kind: str | None = None
    language: str | None = None

    for raw in tags:
        tag = (raw or "").strip()
        if ":" not in tag:
            continue
        key, value = tag.split(":", maxsplit=1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue

        if key == "set" and set_key is None:
            set_key = value
        elif key == "dockey" and document_key is None:
            document_key = value
        elif key == "rev" and revision is None:
            revision = value
        elif key == "kind" and kind is None:
            kind = value
        elif key == "lang" and language is None:
            language = value

    if revision is None:
        revision = extract_revision_from_title(title)
    if document_key is None:
        document_key = extract_document_key_from_title(title)
    if kind is None and category:
        kind = category
    if set_key is None:
        set_key = "__unmapped__"

    return {
        "set_key": set_key,
        "document_key": document_key,
        "revision": revision,
        "kind": kind,
        "language": language,
    }


def extract_structured_tag_map(tags: list[str]) -> dict[str, str]:
    tag_map: dict[str, str] = {}
    for raw in tags:
        tag = (raw or "").strip()
        if ":" not in tag:
            continue
        key, value = tag.split(":", maxsplit=1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in {"set", "dockey", "rev", "kind", "lang"} and key not in tag_map:
            tag_map[key] = value
    return tag_map


def _normalize_value(value: str) -> str:
    lowered = _WHITESPACE_PATTERN.sub(" ", value.strip().lower())
    slug = _NON_SLUG_PATTERN.sub("-", lowered).strip("-")
    return slug


def infer_structured_tags(title: str, description: str, filename: str, existing_tags: list[str]) -> list[str]:
    inferred: list[str] = []
    existing = extract_structured_tag_map(existing_tags)

    title_text = title or ""
    description_text = description or ""
    filename_text = filename or ""
    merged_text = " ".join([title_text, description_text, filename_text]).lower()

    if "set" not in existing or "dockey" not in existing:
        for rule in _SET_RULES:
            if any(re.search(pattern, merged_text) for pattern in rule["patterns"]):
                if "set" not in existing:
                    inferred.append(f"set:{rule['set']}")
                    existing["set"] = rule["set"]
                if "dockey" not in existing:
                    inferred.append(f"dockey:{rule['dockey']}")
                    existing["dockey"] = rule["dockey"]
                break

    if "rev" not in existing:
        revision = extract_revision_from_title(title_text) or extract_revision_from_title(filename_text)
        if revision:
            normalized = _normalize_value(revision)
            if normalized:
                inferred.append(f"rev:{normalized}")
                existing["rev"] = normalized
        elif re.search(r"\bdraft\b", merged_text):
            inferred.append("rev:draft")
            existing["rev"] = "draft"

    if "kind" not in existing:
        for kind, patterns in _KIND_RULES:
            if any(re.search(pattern, merged_text) for pattern in patterns):
                inferred.append(f"kind:{kind}")
                existing["kind"] = kind
                break

    if "lang" not in existing:
        for lang, patterns in _LANG_RULES:
            if any(re.search(pattern, merged_text) for pattern in patterns):
                inferred.append(f"lang:{lang}")
                existing["lang"] = lang
                break

    return inferred
