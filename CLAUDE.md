# Claude Code Instructions

## Python

- python 実行は `python script.py` を使わず、必ず `uv run python script.py` を使う。
- モジュール実行は `python -m <module>` ではなく `uv run python -m <module>` を使う。
- パッケージ追加は `pip install <pkg>` を使わず、必ず `uv add <pkg>` を使う。
- 依存関係の操作は uv を優先し、pip/poetry/conda のコマンドは提案しない。
- python スクリプトを記述したら `uv run black <path>` を実行してフォーマットする。
- CLI の表示が理由で E501 が出る場合のみ `# noqa: E501` を許可する。

## Examples

- Run: `uv run ws schema generate`
- Module: `uv run python -m ws generate`
- Add: `uv add rich`
