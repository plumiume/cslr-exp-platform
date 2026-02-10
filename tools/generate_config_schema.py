from __future__ import annotations

import json
from pathlib import Path

from ws import Config


def main() -> None:
    schema = Config.model_json_schema()
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")

    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / ".vscode" / "config.schema.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
