from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"openapi exported: {output}")


if __name__ == "__main__":
    main()
