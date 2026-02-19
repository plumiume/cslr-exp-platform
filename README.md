# CSLR Experiment Platform

Ray クラスターベースの実験プラットフォーム（Docker Compose構成）

## 概要

このプロジェクトは、マルチホスト環境を想定した Ray クラスターを Docker Compose で構築するためのテンプレートシステムです。`ws` CLI ツールで設定の生成からクラスターの起動・管理までを一貫して行えます。

### 主な機能

- **自動IP検出**: Ray ノードのIPアドレスを自動検出（手動設定不要）
- **ホワイトリスト制御**: `config.yaml` の `nodes` でHead候補ノードを指定し、ヘルスチェックで自動選出
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
# WSL / Ubuntu の場合
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows の場合
# winget install --id=astral-sh.uv -e
```

### 2. 設定ファイルの準備

```bash
cp config.example.yaml config.yaml
# 必要に応じて config.yaml を編集
```

### 3. Docker Compose 設定の生成と起動

```bash
# 設定ファイルを生成（_build/compose.yaml に出力）
uv run ws generate

# クラスターを起動
uv run ws up -d

# クラスター状態の確認
uv run ws ps

# ログ確認
uv run ws logs -f
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
uv run ws down
```

### 6. 開発時のユニットテスト実行

```bash
uv run pytest
```

## ws CLI コマンド

| コマンド | 説明 |
|---------|------|
| `ws generate` | テンプレートから `_build/compose.yaml` を生成 |
| `ws up [-d] [--build]` | サービスを起動（自動で generate を実行） |
| `ws down [-v]` | サービスを停止 |
| `ws ps` | 実行中のサービスを表示 |
| `ws logs [-f] [--tail N]` | ログを表示 |
| `ws test [--up\|--down\|--logs\|--collect-logs] [--duration N] [--target cpu\|gpu] [--head host:port]` | テストコンテナの管理 |

※ `--target` に応じて cluster-test の接続先ノード（CPU/GPU）を切り替えます。CPU/GPU の同時起動はクラスターテスト用途に限定してください。

## 運用ポリシー

### 1) 重要点

- 通常運用では `ray-cpu` / `ray-gpu` は排他的に起動します。
- CPU/GPU 同時起動は `ws test` によるクラスターテスト用途のみを前提とします。

### 2) 実行レベル制限

- スキーマ上で CPU/GPU 同時有効を禁止するのではなく、`ws up` の実行時に制限します。
- `ws up ray-cpu ray-gpu` はエラーで停止します。

### 3) future マーク方針

- 以下は将来利用（future/reserved）として保持します。
   - `host.hostname`
   - `services.ray.cpu.address` / `services.ray.gpu.address`
   - `volumes.ray_data`

## 設定ファイル

### config.yaml

メインの設定ファイル。サービスの有効/無効、ポート、リソース制限等を定義。

```yaml
services:
  ray:
    cpu:
      enabled: true
      image: rayproject/ray:latest
         cpus: 4
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

nodes:
   head_whitelist:
      - ray-cpu
      - ray-gpu
   head_address: null
   health_service:
      url: "http://health:8080"
      timeout: 1
   cluster:
      discovery_timeout: 5
      wait_for_head: 30
```

### config.yaml の `nodes` セクション

ノードのホワイトリストとヘルスチェック設定。

**重要**: `head_whitelist` には、**この設定を適用するマシンから到達可能なホスト名**を指定してください。

#### シングルホスト環境（Docker Compose単独）

```yaml
nodes:
   head_whitelist:
      - ray-cpu      # docker-composeで定義されたコンテナのホスト名
      - ray-gpu

   head_address: null

   health_service:
      url: "http://health:8080"
      timeout: 1
```

#### マルチホスト環境

複数の物理ホストでRayクラスターを構成する場合：

1. **各ホストで名前解決を設定**
   - DNS または `/etc/hosts` で他のホストのホスト名を解決できるようにする
   - 例: `/etc/hosts` に `192.168.1.10 ray-cpu-host-a` を追加

2. **各ホストの `config.yaml` に同じ `nodes` 設定を記述**
   ```yaml
    nodes:
       head_whitelist:
          - ray-cpu-host-a    # host-a のRay CPUノード
          - ray-gpu-host-a    # host-a のRay GPUノード
          - ray-cpu-host-b    # host-b のRay CPUノード

       head_address: null

       health_service:
          url: "http://health:8080"  # 各ホストのローカルヘルスチェック
          timeout: 1
   ```

3. **docker-compose.yaml でホスト名を設定**
   ```yaml
   services:
     ray-cpu:
       hostname: ray-cpu-host-a  # ホワイトリストと一致させる
   ```

## Head/Worker 自動判定

`ray-ep.sh` エントリポイントスクリプトが起動時に以下のロジックでモードを決定：

### 判定フロー

1. **ホワイトリストチェック**
   - コンテナの `hostname` が `config.yaml` の `nodes.head_whitelist` に含まれるか確認
   - マルチホストの場合、ネットワーク経由で到達可能なホスト名である必要がある

2. **ヘルスチェックサービス接続**
   - ヘルスチェックサービスに接続（`timeout: 1s`）
   - 利用可能 → 既存Headノード検索へ
   - 利用不可 → Head モードで起動（フェイルセーフ）

3. **既存Head検出**
   - 他のホワイトリストノードに TCP 接続を試行（`RAY_HEAD_PORT`）
   - 既存Head発見 → Worker モードで接続
   - 未発見 → Head モードで起動（最初のノード）

4. **起動モード決定**
   - **Head モード**: 最初に起動したホワイトリストノード
   - **Worker モード**: 既存Headが見つかった場合、またはホワイトリスト外

### ホワイトリスト外ノード

ホワイトリスト外のノードは自動的に Worker モードで起動し、以下の優先順位で接続先を決定：

1. 環境変数 `HEAD_ADDRESS` が設定されている場合、それを使用
2. `config.yaml` の `nodes.head_address` が設定されている場合、それを使用
3. ホワイトリストの最初のノード + `RAY_HEAD_PORT` に接続

マルチホスト環境では、Workerノードから Head ノードへのネットワーク到達性を確保してください。

## ディレクトリ構成

```
.
├── config.example.yaml          # 設定例
├── config.yaml                  # 実際の設定
├── ws                           # CLI ツール（Python typer）
├── pyproject.toml               # Python プロジェクト設定
├── templates/
│   ├── compose.yaml.jinja2      # メインテンプレート
│   └── cluster-test.compose.yaml.jinja2  # テスト用テンプレート
├── entrypoints/
│   ├── ray.sh                   # Ray エントリポイント（CPU/GPU統合）
│   └── health.sh                # ヘルスチェックサーバー
└── _build/
    ├── compose.yaml             # 生成されたメイン設定
    └── cluster-test.compose.yaml # 生成されたテスト設定
```

## トラブルシューティング

### `uv run black` が `No such file or directory` で失敗する

**症状**: `uv run black --version` が `Failed to spawn: black` で失敗する。

**原因**: 別ワークツリーで作られた `.venv/bin/black` の shebang が、現在存在しない別パスの Python を指している。

**対処法**:

```bash
rm -rf .venv
uv sync --all-groups
uv run black --version
```

必要に応じて、`uv run python -m black --version` でも確認できます。

### クラスターが起動しない

```bash
# ログを確認
uv run ws logs ray-cpu

# Ray の状態を確認
docker compose -f _build/compose.yaml exec ray-cpu ray status

# Raylet のログを確認
docker compose -f _build/compose.yaml exec ray-cpu cat /tmp/ray/session_latest/logs/raylet.out
```

### マルチホスト環境での接続問題

#### Worker ノードが Head に接続できない

**症状**: Worker ノードが "Cannot connect to Ray head node" エラーで起動失敗

**原因と対処法**:

1. **ホスト名解決の問題**
   ```bash
   # Worker ノード側で Head ノードのホスト名を解決できるか確認
   docker compose -f _build/compose.yaml exec ray-cpu getent hosts ray-cpu-host-a
   
   # 解決できない場合、/etc/hosts または DNS を設定
   # ホストマシンの /etc/hosts に追加:
   192.168.1.10 ray-cpu-host-a
   192.168.1.11 ray-gpu-host-b
   ```

2. **ネットワーク到達性の問題**
   ```bash
   # Worker ノードから Head ノードへの接続テスト
   docker compose -f _build/compose.yaml exec ray-cpu ping -c 3 ray-cpu-host-a
   
   # ポート接続テスト
   docker compose -f _build/compose.yaml exec ray-cpu nc -zv ray-cpu-host-a 6379
   ```

3. **ファイアウォール設定**
   ```bash
   # Head ノード側で Ray ポートを開放（Linuxの場合）
   sudo ufw allow 6379/tcp  # Ray Head port
   sudo ufw allow 8265/tcp  # Dashboard port
   sudo ufw allow 10001/tcp # Ray Client port
   ```

4. **Docker ネットワーク設定**
   - 各ホストで Docker が異なるネットワークを使用している場合、overlay network または host network モードを検討
   - `config.yaml` の `network.subnet` が他のネットワークと競合していないか確認

#### ホワイトリストノードが Head にならない

**症状**: ホワイトリストに登録されているが、Worker モードで起動してしまう

**確認事項**:

1. **ホスト名の一致**
   ```bash
   # コンテナ内のホスト名を確認
   docker compose -f _build/compose.yaml exec ray-cpu hostname
   
   # config.yaml の nodes.head_whitelist と一致しているか確認
   ```

2. **ホワイトリストの記載順序**
   - `head_whitelist` の順番で Head 候補が決定される
   - 最初のノードが起動時に Head になるように設定

3. **ヘルスチェックサービスの状態**
   ```bash
   # ヘルスチェックサービスが正常に動作しているか確認
   docker compose -f _build/compose.yaml logs health
   curl http://localhost:8888
   ```

### 既知の問題

1. **`--node-ip-address` は環境に応じて使用する**: 単一ネットワークでは自動検出で十分ですが、ネットワーク分離/NAT 環境では到達可能な IP を明示してください
2. **GCS health check failures**: ノードIPが正しく設定されていない場合に発生
3. **ポート衝突**: Redis(6381) と Ray head(6379/6380) のホスト側ポートが重ならないよう注意
4. **マルチホストでのホスト名解決**: Docker の組み込み DNS は単一ホスト内のみ有効。マルチホストでは外部 DNS または `/etc/hosts` が必要

## 依存関係

- Docker Engine 20.10+
- Docker Compose 2.0+
- Python 3.12+ (テンプレート生成用)
- uv (Pythonパッケージマネージャー)

GPU使用時:
- NVIDIA Docker runtime
- NVIDIA GPU Driver
- CUDA 11.0+

## ドキュメント

### 設定とリファレンス

- **[Configuration Reference](docs/config-reference.md)** - `config.yaml` の全フィールド詳細
  - サービス設定、ネットワーク、nodes セクションの完全リファレンス
  - 環境変数オーバーライドの使い方
  - バリデーションルールと設定例

- **[CHANGELOG](CHANGELOG.md)** - 変更履歴と移行ガイド
  - 破壊的変更の記録（nodes.yaml → config.yaml 統合）
  - バージョン間の移行手順

### アーキテクチャとデザイン

- **[System Architecture](docs/architecture.md)** - システムアーキテクチャ
  - コンポーネント構成図
  - 設定生成フロー
  - Ray クラスター起動シーケンス
  - Head/Worker 自動判定ロジック
  - ネットワークアーキテクチャ（シングル/マルチホスト）

### ビルドとデプロイ

- **[Build Matrix](docs/build-matrix.md)** - Docker イメージビルド
  - 複数の CUDA/Python バージョンでのビルド方法
  - ビルドマトリックスの使い方

- **[Test Cluster](notes/test-cluster-readme.md)** - テストクラスター
  - ネットワーク分離されたテストコンテナの詳細

### トラブルシューティング

- **[Troubleshooting Guide](docs/troubleshooting.md)** - 問題解決ガイド
  - 設定とバリデーションエラー
  - クラスター起動の問題
  - ネットワーク接続の問題（シングル/マルチホスト）
  - Ray クラスター固有の問題
  - GPU関連の問題
  - パフォーマンスとデバッグ手法

## ライセンス

MIT License

## 参考資料

- [Ray Documentation](https://docs.ray.io/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Ray Cluster Setup Guide](https://docs.ray.io/en/latest/cluster/getting-started.html)
