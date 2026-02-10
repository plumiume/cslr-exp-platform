from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path


def load_config_model(project_root: Path):
    ws_path = project_root / "ws"
    loader = importlib.machinery.SourceFileLoader("ws", str(ws_path))
    spec = importlib.util.spec_from_loader("ws", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec for {ws_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Config


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_model = load_config_model(project_root)
    schema = config_model.model_json_schema()
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")

    output_path = project_root / ".vscode" / "config.schema.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
