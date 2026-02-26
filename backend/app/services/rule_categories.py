def _slugify(text: str) -> str:
    return text.strip().lower().replace(" ", "-")


def extract_categories_from_rules_json(rules_json: dict | None) -> list[str]:
    rules = rules_json or {}
    names: list[str] = []
    seen: set[str] = set()

    def add_category(raw: object) -> None:
        if not isinstance(raw, str):
            return
        name = raw.strip()
        if not name:
            return
        key = _slugify(name)
        if key in seen:
            return
        seen.add(key)
        names.append(name)

    for item in rules.get("category_rules", []) or []:
        if isinstance(item, dict):
            add_category(item.get("category"))
    for item in rules.get("tag_category_rules", []) or []:
        if isinstance(item, dict):
            add_category(item.get("category"))
    add_category(rules.get("default_category"))

    if not names:
        names.append("기타")
    return names
