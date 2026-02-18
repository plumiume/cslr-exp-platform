#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema generation utilities."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Config


def generate_config_schema(project_root: Path) -> Path:
    """Generate config.schema.json from Pydantic model."""
    schema_path = project_root / ".vscode" / "config.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)

    config_schema = Config.model_json_schema()
    config_schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    schema_path.write_text(
        json.dumps(config_schema, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    return schema_path
