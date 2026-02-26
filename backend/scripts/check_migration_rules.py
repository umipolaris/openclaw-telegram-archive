from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    versions_dir = root / "app" / "db" / "migrations" / "versions"
    files = sorted(versions_dir.glob("*.py"))
    if not files:
        print("No migration files found.")
        return 1

    violations: list[str] = []
    for migration in files:
        text = migration.read_text(encoding="utf-8")
        if "def upgrade(" not in text:
            violations.append(f"{migration.name}: missing upgrade()")
        if "def downgrade(" not in text:
            violations.append(f"{migration.name}: missing downgrade()")

    if violations:
        print("Migration rule violations:")
        for row in violations:
            print(f"- {row}")
        return 1

    print(f"Migration rules OK ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
