from dataclasses import dataclass
from datetime import date, datetime
import re

from app.services.caption_parser import CaptionParseResult
from app.services.archive_set_parser import infer_structured_tags
from app.services.date_parser import parse_event_date_from_text
from app.services.rule_categories import extract_categories_from_rules_json


@dataclass
class RuleInput:
    caption: CaptionParseResult
    title: str
    description: str
    filename: str
    body_text: str
    metadata_date_text: str | None
    ingested_at: datetime


@dataclass
class RuleOutput:
    category: str
    tags: list[str]
    event_date: date
    review_reasons: list[str]


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "document",
    "file",
    "title",
    "description",
    "manual",
    "note",
    "분류",
    "날짜",
    "태그",
    "문서",
    "파일",
    "제목",
    "설명",
    "작성",
    "수정",
    "및",
    "또는",
    "그리고",
}
_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_AUTO_TAG_LIMIT = 3
_KIND_CATEGORY_MAP = {
    "manual": "매뉴얼",
    "guide": "가이드",
    "account-list": "계정 리스트",
    "drawing": "도면",
    "main": "절차",
}
_SET_CATEGORY_MAP = {
    "dcp": "DCP",
    "general-arrangement-drawing": "General Arrangement Drawing",
}
_GENERIC_CATEGORY_KEYS = {"기타", "default", "misc", "unknown", "uncategorized", "미분류"}


def _match_keywords(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _normalize_tag_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _build_allowed_category_map(rules: dict | None) -> dict[str, str]:
    names = extract_categories_from_rules_json(rules if isinstance(rules, dict) else None)
    allowed: dict[str, str] = {}
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        key = _normalize_tag_key(name)
        if key not in allowed:
            allowed[key] = name
    return allowed


def _extract_keyword_tags(
    *,
    title: str,
    description: str,
    caption_raw: str,
    existing_tags: list[str],
    max_count: int = 12,
) -> list[str]:
    merged = " ".join((title or "", description or "", caption_raw or "")).strip()
    if not merged:
        return []

    existing_keys = {_normalize_tag_key(tag) for tag in existing_tags if tag.strip()}
    inferred: list[str] = []

    for token in _TOKEN_PATTERN.findall(merged):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if token.isdigit():
            continue
        if re.fullmatch(r"\d{2,8}", token):
            continue

        normalized = token if not token.isascii() else lowered
        key = _normalize_tag_key(normalized)
        if key in existing_keys:
            continue

        inferred.append(normalized)
        existing_keys.add(key)
        if len(inferred) >= max_count:
            break

    return inferred


def _extract_structured_tag_map(tags: list[str]) -> dict[str, str]:
    tag_map: dict[str, str] = {}
    for raw in tags:
        tag = raw.strip()
        if ":" not in tag:
            continue
        key, value = tag.split(":", maxsplit=1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value or key in tag_map:
            continue
        tag_map[key] = value
    return tag_map


def _tag_matches_pattern(tag_values: set[str], pattern: str) -> bool:
    normalized_pattern = _normalize_tag_key(pattern)
    if not normalized_pattern:
        return False
    if normalized_pattern.endswith("*"):
        prefix = normalized_pattern[:-1]
        if not prefix:
            return False
        return any(value.startswith(prefix) for value in tag_values)
    return normalized_pattern in tag_values


def _infer_category_from_tag_rules(tags: list[str], rules: dict | None) -> str | None:
    if not isinstance(rules, dict):
        return None
    raw_tag_rules = rules.get("tag_category_rules", [])
    tag_rules = [rule for rule in raw_tag_rules if isinstance(rule, dict)] if isinstance(raw_tag_rules, list) else []
    if not tag_rules:
        return None

    normalized_tags = {_normalize_tag_key(tag) for tag in tags if tag.strip()}
    if not normalized_tags:
        return None

    for rule in tag_rules:
        category = str(rule.get("category") or "").strip()
        raw_patterns = rule.get("tags", [])
        patterns = [str(item).strip() for item in raw_patterns if str(item).strip()] if isinstance(raw_patterns, list) else []
        if not category or not patterns:
            continue

        match_mode = str(rule.get("match", "any")).strip().lower()
        if match_mode == "all":
            matched = all(_tag_matches_pattern(normalized_tags, pattern) for pattern in patterns)
        else:
            matched = any(_tag_matches_pattern(normalized_tags, pattern) for pattern in patterns)
        if matched:
            return category
    return None


def _choose_plain_tag_as_category(tags: list[str], default_category: str) -> str | None:
    default_key = _normalize_tag_key(default_category)
    generic_keys = {_normalize_tag_key(key) for key in _GENERIC_CATEGORY_KEYS}
    generic_keys.add(default_key)

    for raw in tags:
        tag = raw.strip()
        if not tag or ":" in tag:
            continue
        key = _normalize_tag_key(tag)
        if key in generic_keys:
            continue
        if re.fullmatch(r"[0-9._/\-]+", tag):
            continue
        return tag
    return None


def _infer_category_from_tags(
    *,
    explicit_tags: list[str],
    auto_tag_candidates: list[str],
    rules: dict | None,
    default_category: str,
    allow_auto_plain_fallback: bool = True,
) -> str | None:
    seen: set[str] = set()
    ordered_tags: list[str] = []
    for raw in [*explicit_tags, *auto_tag_candidates]:
        tag = raw.strip()
        if not tag:
            continue
        key = _normalize_tag_key(tag)
        if key in seen:
            continue
        seen.add(key)
        ordered_tags.append(tag)

    if not ordered_tags:
        return None

    by_rule = _infer_category_from_tag_rules(ordered_tags, rules)
    if by_rule:
        return by_rule

    structured = _extract_structured_tag_map(ordered_tags)
    kind = structured.get("kind", "").strip().lower()
    if kind and kind in _KIND_CATEGORY_MAP:
        return _KIND_CATEGORY_MAP[kind]

    set_key = structured.get("set", "").strip().lower()
    if set_key and set_key in _SET_CATEGORY_MAP:
        return _SET_CATEGORY_MAP[set_key]

    if allow_auto_plain_fallback:
        return _choose_plain_tag_as_category(ordered_tags, default_category)
    return None


def apply_rules(ctx: RuleInput, rules: dict | None) -> RuleOutput:
    rules = rules or {}
    allowed_category_map = _build_allowed_category_map(rules)

    default_category_raw = rules.get("default_category", "기타")
    if isinstance(default_category_raw, str) and default_category_raw.strip():
        default_category = default_category_raw.strip()
    else:
        default_category = "기타"

    default_key = _normalize_tag_key(default_category)
    if default_key in allowed_category_map:
        default_category = allowed_category_map[default_key]
    elif default_category:
        allowed_category_map[default_key] = default_category

    def resolve_allowed_category(raw: str | None) -> str | None:
        if not raw:
            return None
        key = _normalize_tag_key(raw)
        return allowed_category_map.get(key)

    category_rules_raw = rules.get("category_rules", [])
    category_rules = [rule for rule in category_rules_raw if isinstance(rule, dict)] if isinstance(category_rules_raw, list) else []

    review_reasons: list[str] = []

    explicit_tags = [tag.strip() for tag in ctx.caption.explicit_tags if tag.strip()]
    tags = list(explicit_tags)
    auto_tag_candidates: list[str] = []

    category_resolved = False
    if ctx.caption.explicit_category:
        allowed_explicit = resolve_allowed_category(ctx.caption.explicit_category.strip())
        if allowed_explicit:
            category = allowed_explicit
            category_resolved = True
        else:
            category = default_category
            review_reasons.append("CATEGORY_OUT_OF_RULESET")
    else:
        category = default_category

    if not category_resolved:
        ordered_sources = [
            ("title", ctx.title),
            ("description", ctx.description),
            ("filename", ctx.filename),
            ("body", ctx.body_text),
        ]

        matched = False
        for source_name, text in ordered_sources:
            if not text:
                continue
            for rule in category_rules:
                rule_keywords = rule.get("keywords", {})
                keywords = rule_keywords.get(source_name, []) if isinstance(rule_keywords, dict) else []
                if keywords and _match_keywords(text, keywords):
                    rule_category = rule.get("category", default_category)
                    if isinstance(rule_category, str):
                        category = resolve_allowed_category(rule_category.strip()) or default_category
                    else:
                        category = default_category
                    rule_tags = rule.get("tags", [])
                    if isinstance(rule_tags, list):
                        auto_tag_candidates.extend(rule_tags)
                    matched = True
                    category_resolved = True
                    break
            if matched:
                break

    date_candidates = [
        ctx.caption.explicit_date,
        ctx.caption.caption_raw,
        ctx.title,
        ctx.filename,
        ctx.metadata_date_text,
    ]
    event_date = None
    for candidate in date_candidates:
        parsed = parse_event_date_from_text(candidate, ctx.ingested_at)
        if parsed:
            event_date = parsed
            break

    if event_date is None:
        event_date = ctx.ingested_at.date()
        review_reasons.append("DATE_MISSING")

    inferred = infer_structured_tags(
        title=ctx.title,
        description=ctx.description,
        filename=ctx.filename,
        existing_tags=[*tags, *auto_tag_candidates],
    )
    auto_tag_candidates.extend(inferred)

    # Extract lightweight keyword tags before category inference so
    # tag_category_rules can use them.
    auto_tag_candidates.extend(
        _extract_keyword_tags(
            title=ctx.title,
            description=ctx.description,
            caption_raw=ctx.caption.caption_raw,
            existing_tags=[*tags, *auto_tag_candidates],
        )
    )

    if not category_resolved:
        inferred_category = _infer_category_from_tags(
            explicit_tags=explicit_tags,
            auto_tag_candidates=auto_tag_candidates,
            rules=rules,
            default_category=default_category,
            allow_auto_plain_fallback=False,
        )
        if inferred_category and inferred_category.strip():
            allowed_inferred = resolve_allowed_category(inferred_category.strip())
            if allowed_inferred:
                category = allowed_inferred
                category_resolved = True
            else:
                review_reasons.append("CATEGORY_OUT_OF_RULESET")
        else:
            review_reasons.append("CLASSIFY_FAIL")

    if not category_resolved and "CLASSIFY_FAIL" not in review_reasons:
        review_reasons.append("CLASSIFY_FAIL")

    if category and category != default_category:
        auto_tag_candidates.append(category)

    explicit_keys = {_normalize_tag_key(tag) for tag in tags}
    auto_keys: set[str] = set()
    limited_auto_tags: list[str] = []
    for raw in auto_tag_candidates:
        tag = raw.strip()
        if not tag:
            continue
        key = _normalize_tag_key(tag)
        if key in explicit_keys or key in auto_keys:
            continue
        auto_keys.add(key)
        limited_auto_tags.append(tag)
        if len(limited_auto_tags) >= _AUTO_TAG_LIMIT:
            break

    tags = sorted(set([*tags, *limited_auto_tags]))
    return RuleOutput(category=category, tags=tags, event_date=event_date, review_reasons=review_reasons)
