# Docker Build Matrix

複数のCUDA/Python/ターゲットの組み合わせで効率的にDockerイメージをビルドするためのツール。

## 概要

このプロジェクトでは、以下のビルドマトリックスをサポートしています：

- **CUDAバージョン**: 12.8.1, 13.1.1
- **Pythonバージョン**: 3.13, 3.14
- **ビルドターゲット**: 
  - `devel`: フル開発環境（nvcc + cmake + ビルドツール）
  - `runtime`: 軽量ランタイム
  - `ray-devel`: devel + Ray開発環境
  - `ray-runtime`: runtime + Ray
  - `marimo-devel`: ray-devel + Marimo開発環境
  - `marimo-runtime`: ray-runtime + Marimo

## ファイル構成

- `build-matrix.yaml`: ビルドマトリックス設定ファイル
- `tools/build_matrix.py`: マトリックス実行スクリプト
- `Dockerfile`: マルチステージビルド定義

## 使用方法

### 1. 最小構成でテスト（推奨）

```bash
uv run python tools/build_matrix.py --minimal
```

最も基本的な構成（CUDA 12.8.1 + Python 3.13 + marimo-runtime）でビルドを実行します。

### 2. 全ビルドを実行

```bash
uv run python tools/build_matrix.py --all
```

すべてのCUDA/Python/ターゲットの組み合わせをビルドします（時間がかかります）。

### 3. 特定のCUDAバージョンのみビルド

```bash
uv run python tools/build_matrix.py --cuda 12.8.1
```

### 4. 特定のPythonバージョンのみビルド

```bash
uv run python tools/build_matrix.py --python 3.13
```

### 5. 特定のターゲットのみビルド

```bash
uv run python tools/build_matrix.py --target marimo-runtime
```

### 6. 複数の条件を組み合わせる

```bash
uv run python tools/build_matrix.py --cuda 12.8.1 --python 3.13 --target marimo-runtime
```

### 7. ドライラン（コマンドの確認のみ）

```bash
uv run python tools/build_matrix.py --all --dry-run
```

実際にはビルドせず、実行されるコマンドを表示します。

## 個別ビルドコマンド例

マトリックスを使わず、個別にビルドする場合：

### marimo-runtime（CUDA 12.8.1 + Python 3.13）

```bash
docker build \
  --target marimo-runtime \
  --build-arg CUDA_VERSION=12.8.1 \
  --build-arg PYTHON_VERSION=3.13 \
  --build-arg CUDA_TAG=cu128 \
  -t plumiume/cslr-exp-platform:marimo-torch2.8.0-cu128-py313-runtime \
  --platform linux/amd64 \
  .
```

### marimo-runtime（CUDA 13.1.1 + Python 3.14）

```bash
docker build \
  --target marimo-runtime \
  --build-arg CUDA_VERSION=13.1.1 \
  --build-arg PYTHON_VERSION=3.14 \
  --build-arg CUDA_TAG=cu130 \
  -t plumiume/cslr-exp-platform:marimo-torch2.9.0-cu130-py314-runtime \
  --platform linux/amd64 \
  .
```

### devel（開発用フル環境）

```bash
docker build \
  --target devel \
  --build-arg CUDA_VERSION=12.8.1 \
  --build-arg PYTHON_VERSION=3.13 \
  --build-arg CUDA_TAG=cu128 \
  -t plumiume/cslr-exp-platform:devel-torch2.8.0-cu128-py313 \
  --platform linux/amd64 \
  .
```

## build-matrix.yaml の編集

新しいビルド構成を追加する場合、`build-matrix.yaml` を編集します：

```yaml
matrix:
  - cuda_version: "12.8.1"
    python_version: "3.13"
    cuda_tag: "cu128"
    targets:
      - name: "marimo-runtime"
        tag: "marimo-torch2.8.0-cu128-py313-runtime"
```

## ビルド時間の目安

- **最小構成（--minimal）**: 約20-40分
- **単一ターゲット**: 約20-40分
- **全ビルド（--all）**: 数時間（並列化なしの場合）

## トラブルシューティング

### ビルドが失敗する場合

1. ドライランでコマンドを確認:
   ```bash
   uv run python tools/build_matrix.py --minimal --dry-run
   ```

2. 個別にビルドして問題を特定:
   ```bash
   docker build --target devel --build-arg CUDA_VERSION=12.8.1 ...
   ```

3. ビルドキャッシュをクリア:
   ```bash
   docker builder prune
   ```

### 依存関係のエラー

スクリプト実行に必要なパッケージをインストール:

```bash
uv add pyyaml rich
```

## 関連ドキュメント

- [Dockerfile](../Dockerfile): マルチステージビルドの詳細
- [README.md](../README.md): プロジェクト全体のドキュメント
