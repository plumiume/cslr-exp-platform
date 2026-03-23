# Plan: RAY_PYTHON_BIN 環境変数対応 (issue #16)

## 概要

`test-ray-client` の Python 実行パスがハードコード（デフォルト `python`）されている問題を修正する。
ホスト側環境変数 `RAY_PYTHON_BIN` で Python バイナリを指定できるようにし、
未指定時は `python3` をデフォルトとして使用する。変更はテンプレートのみ。

## 変更ファイル

- [../templates/cluster-test.compose.yaml.jinja2](../templates/cluster-test.compose.yaml.jinja2)

## Steps

1. **[L205](../templates/cluster-test.compose.yaml.jinja2#L205) の `environment` 行を変更**

   - Before: `- TEST_PYTHON_EXEC=${TEST_PYTHON_EXEC:-python}`
   - After:  `- RAY_PYTHON_BIN=${RAY_PYTHON_BIN:-python3}`

2. **[L239](../templates/cluster-test.compose.yaml.jinja2#L239) の `command` ブロック内の実行行を変更**

   - Before: `su - ray -c "$TEST_PYTHON_EXEC -c ...`
   - After:  `su - ray -c "$RAY_PYTHON_BIN -c ...`

## Verification

- `uv run ws test` で生成ファイルを確認し、`RAY_PYTHON_BIN` が正しく出力される
- `RAY_PYTHON_BIN` 未指定時に `python3`、指定時にその値が使われることを compose 出力で確認

## Decisions

- 変数名: `TEST_PYTHON_EXEC` → `RAY_PYTHON_BIN`（issue 要求に合わせ変更）
- デフォルト値: `python` → `python3`（安全なデフォルトに変更）
- `ClusterTestConfig` モデルへの追加は行わず、Docker Compose 変数補間のみで完結する最小変更を採用
