# Plan: tools/build_matrix.py `--monitor-disk` をクロスプラットフォーム対応 (issue #21)

## 概要

`tools/build_matrix.py` の `--monitor-disk` が内部で呼ぶ `get_disk_free_gb()` が
`shutil.disk_usage("C:\\")` に固定されており、Linux/macOS で例外になってクラッシュする。

目的: `--monitor-disk` が少なくとも Linux + Windows で動作すること。

## 変更対象

- [../tools/build_matrix.py](../tools/build_matrix.py)

## 方針

- `shutil.disk_usage()` に渡すパスを OS で切り替える
  - Windows: `SystemDrive` を優先し、未設定時は `C:\\`
  - 非 Windows: `/`
- 可能なら「どのパーティションを監視しているか」が分かるように、例外時のフォールバックも用意する
  - 最小構成: 上記パスで十分
  - 安全策: 失敗したら `Path.cwd()`（ワークスペースがあるパーティション）を試す

## Steps

1. **`get_disk_free_gb()` を OS 依存しない実装へ変更**

   対象: [tools/build_matrix.py](../tools/build_matrix.py#L45)

   - Before: `shutil.disk_usage("C:\\")`
   - After:
     - `platform.system()` もしくは `os.name` で Windows 判定
     - Windows の場合は `os.environ.get("SystemDrive", "C:") + "\\"`
     - 非 Windows は `/`
     - 例外時は `Path.cwd()` などにフォールバック（必要なら）

2. **（任意だが推奨）リグレッションテストを追加**

   - 新規: `tests/test_build_matrix_monitor_disk.py`
   - ねらい: Linux 環境で `get_disk_free_gb()` が例外を投げず float を返すこと
   - 実装案:
     - Windows 判定を `platform.system()` に寄せておく（`monkeypatch` で差し替えやすい）
     - もしくは判定/パス決定を `_disk_usage_path()` のような小関数に分離して単体テストする

## Verification

- Linux でクラッシュしないこと:
  - `uv run python tools/build_matrix.py --all --monitor-disk --dry-run`
- 既存チェック:
  - `uv run pyright`
  - `uv run flake8`
  - `uv run pytest`

## Decisions

- 非 Windows の監視対象は `/` をデフォルトにする（issue 提案に合わせた最小修正）
- Windows は `SystemDrive` を優先し、フォールバックは `C:\\`
