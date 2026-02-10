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
    return module.Config, module.NodesConfig


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_model, nodes_model = load_config_model(project_root)

    # Generate config.yaml schema
    config_schema = config_model.model_json_schema()
    config_schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    config_output_path = project_root / ".vscode" / "config.schema.json"
    config_output_path.parent.mkdir(parents=True, exist_ok=True)
    config_output_path.write_text(
        json.dumps(config_schema, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    # Generate nodes.yaml schema
    nodes_schema = nodes_model.model_json_schema()
    nodes_schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    nodes_output_path = project_root / ".vscode" / "nodes.schema.json"
    nodes_output_path.write_text(
        json.dumps(nodes_schema, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
