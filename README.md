# CSLR Experiment Platform

Ray クラスターベースの実験プラットフォーム（Docker Compose構成）

## 概要

このプロジェクトは、マルチホスト環境を想定した Ray クラスターを Docker Compose で構築するためのテンプレートシステムです。`ws` CLI ツールで設定の生成からクラスターの起動・管理までを一貫して行えます。

### 主な機能

- **自動IP検出**: Ray ノードのIPアドレスを自動検出（手動設定不要）
- **ホワイトリスト制御**: `nodes.yaml` でHead候補ノードを指定し、ヘルスチェックで自動選出
- **GPU対応**: NVIDIA GPU を使用した Ray クラスター構成
- **統合サービス**: MLflow, Redis, Marimo などの統合
- **テスト環境**: ネットワーク分離されたテストコンテナで接続性を検証

## アーキテクチャ

```
物理ホスト
├── Docker Network: ray-network (172.28.0.0/16)
│   ├── health (ヘルスチェック)    port 8888
│   ├── ray-cpu (Head/Worker)      port 6379, 8265, 10001
│   ├── ray-gpu (Head/Worker)      port 6380, 8266, 10002
│   ├── ray-redis                  port 6381→6379
│   ├── mlflow                     port 5000
│   ├── mlflow-postgres            (internal)
│   └── marimo                     port 8080
│
└── クラスターテスト時（別ネットワーク）
    ├── test-ray-client   172.30.0.0/24
    └── test-ray-worker   172.30.0.0/24
```

## クイックスタート

### 1. uv のインストール

```bash
# uv のインストール (未インストールの場合)
winget install --id=astral-sh.uv -e
```

### 2. 設定ファイルの準備

```bash
cp config.example.yaml config.yaml
# 必要に応じて config.yaml を編集
```

### 3. Docker Compose 設定の生成と起動

```bash
# 設定ファイルを生成（_build/compose.yaml に出力）
uv run python ws generate

# クラスターを起動
uv run python ws up -d

# クラスター状態の確認
uv run python ws ps

# ログ確認
uv run python ws logs -f
```

### 4. クラスター状態の確認

```bash
# Ray Dashboard にアクセス (Windows)
start http://localhost:8265

# Ray Client API から接続テスト
uv run python -c "import ray; ray.init('ray://localhost:10001'); print(ray.cluster_resources())"
```

### 5. クラスターの停止

```bash
uv run python ws down
```

## ws CLI コマンド

| コマンド | 説明 |
|---------|------|
| `ws generate` | テンプレートから `_build/compose.yaml` を生成 |
| `ws up [-d] [--build]` | サービスを起動（自動で generate を実行） |
| `ws down [-v]` | サービスを停止 |
| `ws ps` | 実行中のサービスを表示 |
| `ws logs [-f] [--tail N]` | ログを表示 |
| `ws test [--up\|--down\|--logs]` | テストコンテナの管理 |

## 設定ファイル

### config.yaml

メインの設定ファイル。サービスの有効/無効、ポート、リソース制限等を定義。

```yaml
services:
  ray:
    cpu:
      enabled: true
      image: rayproject/ray:latest
      cpus: "4"
      memory: 8g
      head_port: 6379
      dashboard_port: 8265
      client_port: 10001
    gpu:
      enabled: true
      image: rayproject/ray:latest-gpu
      head_port: 6380
      dashboard_port: 8266
      client_port: 10002
  redis:
    port: 6381  # ホスト側ポート（コンテナ内は6379）
```

### nodes.yaml

ノードのホワイトリストとヘルスチェック設定。

```yaml
head_whitelist:
  - ray-cpu
  - ray-gpu

head_address: null  # 明示的なHeadアドレス（省略時はホワイトリストから自動決定）

health_service:
  url: "http://health:8080"
  timeout: 1
```

## Head/Worker 自動判定

`ray-ep.sh` エントリポイントスクリプトが起動時に以下のロジックでモードを決定：

1. ホスト名が `nodes.yaml` のホワイトリストに含まれるか確認
2. ヘルスチェックサービスに接続（`timeout: 1s`）
3. 他のホワイトリストノードに既存Headがいるか確認
4. 条件に応じて Head または Worker として起動

ホワイトリスト外のノードは自動的に Worker モードで起動し、`HEAD_ADDRESS` 環境変数またはホワイトリスト最初のノードに接続します。

## ディレクトリ構成

```
.
├── config.example.yaml          # 設定例
├── config.yaml                  # 実際の設定
├── nodes.yaml                   # ノードホワイトリスト設定
├── ws                           # CLI ツール（Python typer）
├── pyproject.toml               # Python プロジェクト設定
├── template/
│   ├── compose.yaml.jinja2      # メインテンプレート
│   ├── cluster-test.compose.yaml.jinja2  # テスト用テンプレート
│   ├── ray-ep.sh                # Ray エントリポイント（CPU/GPU統合）
│   └── health-ep.sh             # ヘルスチェックサーバー
└── _build/
    ├── compose.yaml             # 生成されたメイン設定
    └── cluster-test.compose.yaml # 生成されたテスト設定
```

## トラブルシューティング

### クラスターが起動しない

```bash
# ログを確認
uv run python ws logs ray-cpu

# Ray の状態を確認
docker compose -f _build/compose.yaml exec ray-cpu ray status

# Raylet のログを確認
docker compose -f _build/compose.yaml exec ray-cpu cat /tmp/ray/session_latest/logs/raylet.out
```

### 既知の問題

1. **`--node-ip-address` は使用しない**: Ray は自動的にコンテナのIPを検出します
2. **GCS health check failures**: ノードIPが正しく設定されていない場合に発生
3. **ポート衝突**: Redis(6381) と Ray head(6379/6380) のホスト側ポートが重ならないよう注意

## 依存関係

- Docker Engine 20.10+
- Docker Compose 2.0+
- Python 3.12+ (テンプレート生成用)
- uv (Pythonパッケージマネージャー)

GPU使用時:
- NVIDIA Docker runtime
- NVIDIA GPU Driver
- CUDA 11.0+

## ライセンス

MIT License

## 参考資料

- [Ray Documentation](https://docs.ray.io/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Ray Cluster Setup Guide](https://docs.ray.io/en/latest/cluster/getting-started.html)
