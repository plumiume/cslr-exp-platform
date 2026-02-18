from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from ws_src.schema_utils import generate_config_schema

    generate_config_schema(project_root)


if __name__ == "__main__":
    main()
