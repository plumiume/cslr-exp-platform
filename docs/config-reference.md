# Configuration Reference

`config.yaml` の全フィールドの詳細リファレンス

## 目次

- [概要](#概要)
- [トップレベル構造](#トップレベル構造)
- [services セクション](#services-セクション)
- [network セクション](#network-セクション)
- [nodes セクション](#nodes-セクション)
- [環境変数オーバーライド](#環境変数オーバーライド)
- [バリデーションルール](#バリデーションルール)

---

## 概要

`config.yaml` は CSLR Experiment Platform の中心的な設定ファイルです。Pydantic Settings を使用しており、YAML ファイル、環境変数、`.env` ファイルから設定を読み込みます。

**優先順位**:
1. 環境変数（最優先）
2. `.env` ファイル
3. `config.yaml`
4. デフォルト値

---

## トップレベル構造

```yaml
services:    # サービス定義（Ray, MLflow, Redis など）
  ray: { ... }
  mlflow: { ... }
  redis: { ... }
  marimo: { ... }

network:     # Docker ネットワーク設定
  subnet: "172.28.0.0/16"

nodes:       # クラスターノード設定
  head_whitelist: [...]
  head_address: null
  health_service: { ... }
  cluster: { ... }
```

---

## services セクション

### services.ray

Ray クラスターの設定

#### services.ray.cpu

CPU ベースの Ray ノード設定

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `enabled` | `bool` | `true` | CPU ノードを有効化 |
| `image` | `str` | `"rayproject/ray:latest"` | Docker イメージ |
| `cpus` | `str` | `"4"` | CPU コア数制限 |
| `memory` | `str` | `"8g"` | メモリ制限（例: `8g`, `16G`, `1024m`） |
| `shm_size` | `str` | `"2g"` | 共有メモリサイズ |
| `head_port` | `int` | `6379` | Ray Head ポート（ホスト側） |
| `dashboard_port` | `int` | `8265` | Ray Dashboard ポート |
| `client_port` | `int` | `10001` | Ray Client API ポート |

**バリデーション**:
- `memory` は `\d+[gmGM]$` パターンに一致する必要があります
- ポート番号は 1024-65535 の範囲
- ポートの重複は許可されません

**例**:
```yaml
services:
  ray:
    cpu:
      enabled: true
      image: "rayproject/ray:2.9.0"
      cpus: "8"
      memory: "16g"
      shm_size: "4g"
      head_port: 6379
      dashboard_port: 8265
      client_port: 10001
```

**環境変数オーバーライド**:
```bash
export CSLR_SERVICES__RAY__CPU__CPUS="16"
export CSLR_SERVICES__RAY__CPU__MEMORY="32g"
```

---

#### services.ray.gpu

GPU ベースの Ray ノード設定（CPU ノードと同じフィールド + GPU 固有設定）

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `image` | `str` | `"rayproject/ray:latest-gpu"` | GPU 対応 Docker イメージ |
| `head_port` | `int` | `6380` | CPU ノードと異なるポートを使用 |
| `dashboard_port` | `int` | `8266` | CPU ノードと異なるポートを使用 |
| `client_port` | `int` | `10002` | CPU ノードと異なるポートを使用 |

**GPU 要件**:
- NVIDIA Docker runtime
- ホストに `nvidia-smi` コマンドが利用可能
- CUDA 11.0+ ドライバー

**自動 GPU 検出**:
- `ws generate` 実行時、ホストで `nvidia-smi` が成功した場合、自動的に `gpu_type: "nvidia"` が設定されます
- `config.yaml` で明示的に `gpu_type: null` を設定すると、自動検出を無効化できます

**例**:
```yaml
services:
  ray:
    gpu:
      enabled: true
      image: "rayproject/ray:2.9.0-gpu"
      cpus: "16"
      memory: "32g"
      shm_size: "8g"
      head_port: 6380
      dashboard_port: 8266
      client_port: 10002
```

---

### services.mlflow

MLflow Tracking サーバーの設定

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `enabled` | `bool` | `true` | MLflow を有効化 |
| `port` | `int` | `5000` | MLflow UI ポート |
| `backend_store_uri` | `str` | `"postgresql://..."` | バックエンドストア URI |
| `default_artifact_root` | `str` | `"/mlflow/artifacts"` | アーティファクトのデフォルト保存先 |

**データベース設定**:
```yaml
mlflow:
  enabled: true
  port: 5000
  backend_store_uri: "postgresql://mlflow:mlflow@mlflow-postgres:5432/mlflow"
  default_artifact_root: "/mlflow/artifacts"
  
  postgres:
    user: "mlflow"
    password: "${MLFLOW_DB_PASSWORD}"
    db: "mlflow"
```

**セキュリティ要件**:
`services.mlflow.postgres.password` はデフォルト値/空文字を禁止しています。機密情報（パスワードなど）は `.env` ファイルや環境変数で必ず注入してください:

```bash
# .env
CSLR_SERVICES__MLFLOW__POSTGRES__PASSWORD="secure_password_here"
```

---

### services.redis

外部 Redis サーバーの設定（Ray の内部 Redis とは別）

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `enabled` | `bool` | `true` | Redis を有効化 |
| `port` | `int` | `6381` | ホスト側ポート（コンテナ内は 6379） |

**注意**: Ray Head ノードのポート（6379/6380）と競合しないよう、異なるポートを使用してください。

---

### services.marimo

Marimo ノートブック環境の設定

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `enabled` | `bool` | `true` | Marimo を有効化 |
| `image` | `str` | Custom marimo image | Marimo Docker イメージ |
| `port` | `int` | `8080` | Marimo UI ポート |

---

## network セクション

Docker ネットワークの設定

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `subnet` | `str` | `"172.28.0.0/16"` | サブネット CIDR |

**バリデーション**:
- CIDR 形式（`xxx.xxx.xxx.xxx/xx`）である必要があります
- `ipaddress.IPv4Network()` で検証されます

**例**:
```yaml
network:
  subnet: "192.168.100.0/24"
```

**環境変数オーバーライド**:
```bash
export CSLR_NETWORK__SUBNET="10.0.0.0/16"
```

---

## nodes セクション

Ray クラスターのノード管理設定

### 構造

```yaml
nodes:
  head_whitelist: [...]
  head_address: null
  health_service:
    url: "http://health:8080"
    timeout: 1
    max_retries: 3
    retry_interval: 2  # Custom value (default: 0.5)
  cluster:
    discovery_timeout: 5
    wait_for_head: 30
```

---

### nodes.head_whitelist

**型**: `list[str]`  
**必須**: はい（空リスト不可）  
**説明**: Ray Head ノードの候補となるホスト名のリスト

**重要**: ホスト名は Docker Compose の `hostname` またはサービス名と一致する必要があります。

**シングルホスト環境**:
```yaml
nodes:
  head_whitelist:
    - ray-cpu      # docker-compose サービス名
    - ray-gpu
```

**マルチホスト環境**:
```yaml
nodes:
  head_whitelist:
    - ray-cpu-host-a    # 物理ホスト A の CPU ノード
    - ray-gpu-host-a    # 物理ホスト A の GPU ノード
    - ray-cpu-host-b    # 物理ホスト B の CPU ノード
```

各ホストで `/etc/hosts` または DNS によるホスト名解決が必要です。

**バリデーション**:
- リストは空であってはいけません
- 各要素は文字列である必要があります

**環境変数オーバーライド**:
```bash
# カンマ区切りまたはスペース区切り
export CSLR_NODES__HEAD_WHITELIST="ray-cpu ray-gpu"
```

---

### nodes.head_address

**型**: `str | None`  
**デフォルト**: `null`  
**説明**: 固定 Head ノードアドレス（オプション）

通常は `null` のままにして自動検出を利用します。マルチホストで特定の Head ノードを固定したい場合に使用します。

**例**:
```yaml
nodes:
  head_address: "ray-cpu-host-a:6379"
```

Worker ノードはこのアドレスに接続を試みます。

**環境変数オーバーライド**:
```bash
export CSLR_NODES__HEAD_ADDRESS="192.168.1.10:6379"
```

---

### nodes.health_service

ヘルスチェックサービスの設定

#### nodes.health_service.url

**型**: `str`  
**デフォルト**: `"http://health:8080"`  
**説明**: ヘルスチェックサーバーの URL

**例**:
```yaml
nodes:
  health_service:
    url: "http://custom-health:9090"
```

#### nodes.health_service.timeout

**型**: `int`  
**デフォルト**: `1`  
**説明**: ヘルスチェック接続タイムアウト（秒）

#### nodes.health_service.max_retries

**型**: `int`  
**デフォルト**: `3`  
**説明**: ヘルスチェック失敗時の最大リトライ回数

#### nodes.health_service.retry_interval

**型**: `int`  
**デフォルト**: `2`  
**説明**: リトライ間隔（秒）

**完全な例**:
```yaml
nodes:
  health_service:
    url: "http://health:8080"
    timeout: 2
    max_retries: 5
    retry_interval: 3  # Custom value (default: 0.5)
```

---

### nodes.cluster

Ray クラスター検出の設定

#### nodes.cluster.discovery_timeout

**型**: `int`  
**デフォルト**: `5`  
**説明**: 既存 Head ノード検出のタイムアウト（秒）

`ray-ep.sh` がホワイトリストノードに TCP 接続を試行する際のタイムアウト。

#### nodes.cluster.wait_for_head

**型**: `int`  
**デフォルト**: `30`  
**説明**: Head ノード起動を待機する最大時間（秒）

Worker ノードが Head ノードの準備完了を待つ時間。

**例**:
```yaml
nodes:
  cluster:
    discovery_timeout: 10
    wait_for_head: 60
```

大規模クラスターや低速ネットワークでは、これらの値を増やすことを推奨します。

---

## 環境変数オーバーライド

Pydantic Settings により、すべての設定を環境変数でオーバーライド可能です。

### 命名規則

- プレフィックス: `CSLR_`
- ネストした設定は `__` で区切る
- 大文字・小文字は区別されません

### 例

| YAML パス | 環境変数 |
|-----------|---------|
| `services.ray.cpu.cpus` | `CSLR_SERVICES__RAY__CPU__CPUS` |
| `network.subnet` | `CSLR_NETWORK__SUBNET` |
| `nodes.head_whitelist` | `CSLR_NODES__HEAD_WHITELIST` |
| `nodes.health_service.url` | `CSLR_NODES__HEALTH_SERVICE__URL` |

### .env ファイル

プロジェクトルートに `.env` ファイルを配置することで、環境変数を永続化できます:

```bash
# .env
CSLR_SERVICES__RAY__CPU__CPUS=16
CSLR_SERVICES__RAY__CPU__MEMORY=32g
CSLR_NODES__HEAD_WHITELIST=ray-cpu,ray-gpu
CSLR_NODES__HEALTH_SERVICE__TIMEOUT=2
```

**注意**: `.env` ファイルは `.gitignore` に含まれています。

---

## バリデーションルール

Pydantic により、以下のバリデーションが自動的に適用されます:

### サブネット

```python
# 形式: xxx.xxx.xxx.xxx/xx
# 例: 172.28.0.0/16, 192.168.1.0/24
ipaddress.IPv4Network(subnet)  # 内部で検証
```

### メモリサイズ

```python
# 形式: 数字 + [g|G|m|M]
# 例: 8g, 16G, 2048m, 4096M
pattern = r'^\d+[gmGM]$'
```

### ポート番号

```python
# 範囲: 1024-65535
# 重複チェック: 全サービスで一意である必要あり
```

### head_whitelist

```python
# 空リスト禁止
# 各要素は非空文字列
assert len(head_whitelist) > 0
```

---

## 設定例

### 最小構成（シングルホスト、開発環境）

```yaml
services:
  ray:
    cpu:
      enabled: true
      cpus: "4"
      memory: "8g"
    gpu:
      enabled: false

  mlflow:
    enabled: false

  redis:
    enabled: true

  marimo:
    enabled: true

network:
  subnet: "172.28.0.0/16"

nodes:
  head_whitelist:
    - ray-cpu
  head_address: null
  health_service:
    url: "http://health:8080"
    timeout: 1
  cluster:
    discovery_timeout: 5
    wait_for_head: 30
```

### フル構成（マルチホスト、本番環境）

```yaml
services:
  ray:
    cpu:
      enabled: true
      image: "rayproject/ray:2.9.0"
      cpus: "16"
      memory: "32g"
      shm_size: "8g"
      head_port: 6379
      dashboard_port: 8265
      client_port: 10001
    
    gpu:
      enabled: true
      image: "rayproject/ray:2.9.0-gpu"
      cpus: "32"
      memory: "64g"
      shm_size: "16g"
      head_port: 6380
      dashboard_port: 8266
      client_port: 10002

  mlflow:
    enabled: true
    port: 5000
    backend_store_uri: "postgresql://mlflow:${MLFLOW_DB_PASSWORD}@mlflow-postgres:5432/mlflow"
    default_artifact_root: "/mlflow/artifacts"
    postgres:
      user: "mlflow"
      password: "${MLFLOW_DB_PASSWORD}"
      db: "mlflow"

  redis:
    enabled: true
    port: 6381

  marimo:
    enabled: true
    port: 8080

network:
  subnet: "10.0.100.0/24"

nodes:
  head_whitelist:
    - ray-cpu-host-a
    - ray-gpu-host-a
    - ray-cpu-host-b
    - ray-gpu-host-b
  head_address: null
  health_service:
    url: "http://health:8080"
    timeout: 2
    max_retries: 5
    retry_interval: 3  # Custom value (default: 0.5)
  cluster:
    discovery_timeout: 10
    wait_for_head: 60
```

対応する `.env` ファイル:

```bash
# .env
MLFLOW_DB_PASSWORD=secure_production_password_here
CSLR_SERVICES__MLFLOW__POSTGRES__PASSWORD=secure_production_password_here
```

---

## 関連ドキュメント

- [README.md](../README.md) - 基本的な使い方
- [CHANGELOG.md](../CHANGELOG.md) - 変更履歴と移行ガイド
- [docs/architecture.md](architecture.md) - システムアーキテクチャ
- [notes/test-cluster-readme.md](../notes/test-cluster-readme.md) - テストクラスター
