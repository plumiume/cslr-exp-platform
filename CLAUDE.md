# Claude Code Instructions

## Python

- Always use `uv run python script.py` instead of `python script.py`.
- Use `uv run python -m <module>` instead of `python -m <module>` for module execution.
- Always use `uv add <pkg>` instead of `pip install <pkg>` to add packages.
- Prioritize `uv` for dependency management; do not suggest pip/poetry/conda commands.
- After writing Python scripts, execute `uv run black <path>` to format code.
- After creating Python scripts, validate with `uv run pyright` and `uv run flake8`.
- Allow `# noqa: E501` only when CLI output is the reason for the error.

## Examples

- Run: `uv run ws schema generate`
- Module: `uv run python -m ws generate`
- Add: `uv add rich`

## PR Review

- When receiving a PR review request, post the review results as review comments.

## GitHub CLI

- After creating or replying with `gh issue create`, `gh pr create`, `gh issue comment` etc., confirm with `gh issue view` or `gh pr view`.
- When you see "PR#XX" or "Issue#XX", check the GitHub posts.
