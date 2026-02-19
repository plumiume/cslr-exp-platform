# Configuration Reference

`config.yaml` の主要フィールドとバリデーション仕様（実装準拠）です。

## 目次

- [概要](#概要)
- [トップレベル構造](#トップレベル構造)
- [services セクション](#services-セクション)
- [network セクション](#network-セクション)
- [cluster_test セクション](#cluster_test-セクション)
- [nodes セクション](#nodes-セクション)
- [環境変数オーバーライド](#環境変数オーバーライド)
- [バリデーションルール](#バリデーションルール)
- [運用ポリシー](#運用ポリシー)

---

## 概要

`config.yaml` は Pydantic Settings で読み込まれます。

優先順位:
1. 環境変数
2. `.env`
3. `config.yaml`
4. デフォルト値

---

## トップレベル構造

```yaml
host:
  has_gpu: false
  gpu_type: null
  hostname: localhost
  ip_address: null

project:
  name: cslr-exp-platform
  version: 0.1.0

network:
  subnet: 172.28.0.0/16

services:
  ray: { ... }
  mlflow: { ... }
  redis: { ... }
  marimo: { ... }
  health: { ... }

volumes:
  mlflow_data: ./data/mlflow
  postgres_data: ./data/postgres
  ray_data: ./data/ray

cluster_test:
  target: cpu
  test_network_subnet: 172.30.0.0/24
  worker_node_manager_port: 30000
  worker_object_manager_port: 30001
  worker_min_worker_port: 30010
  worker_max_worker_port: 30020
  worker_cpu_node_manager_port: 30100
  worker_cpu_object_manager_port: 30101
  worker_cpu_min_worker_port: 30110
  worker_cpu_max_worker_port: 30120

nodes:
  head_whitelist: [ray-cpu, ray-gpu]
  head_address: null
  health_service: { ... }
  cluster: { ... }
```

---

## services セクション

### services.ray.cpu / services.ray.gpu

共通フィールド:

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `enabled` | `bool` | `true` | サービス有効化 |
| `image` | `str \| null` | cpu:`rayproject/ray:latest` / gpu:`rayproject/ray:latest-gpu` | Docker イメージ |
| `cpus` | `float \| null` | `null` | CPU 制限 |
| `memory` | `str \| null` | `null` | 例: `8g`, `512m` |
| `head_port` | `int` | cpu:`6379` / gpu:`6380` | Head ポート |
| `dashboard_port` | `int` | cpu:`8265` / gpu:`8266` | Dashboard ポート |
| `client_port` | `int` | cpu:`10001` / gpu:`10002` | Ray Client ポート |
| `node_ip_address` | `str \| null` | `null` | Advertised IP |
| `node_manager_port` | `int \| null` | `null` | 固定 NodeManager ポート |
| `object_manager_port` | `int \| null` | `null` | 固定 ObjectManager ポート |
| `min_worker_port` | `int \| null` | `null` | worker ポート範囲(最小) |
| `max_worker_port` | `int \| null` | `null` | worker ポート範囲(最大) |

GPU 追加フィールド:

| フィールド | 型 | デフォルト |
|---|---|---|
| `runtime` | `str` | `nvidia` |

`services.ray.image` は cpu/gpu の `image` 未指定時のフォールバックとして使われます。

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

| フィールド | 型 | デフォルト |
|---|---|---|
| `enabled` | `bool` | `true` |
| `image` | `str` | `redis:7-alpine` |
| `port` | `int` | `6381` |

### services.marimo

| フィールド | 型 | デフォルト |
|---|---|---|
| `enabled` | `bool` | `true` |
| `image` | `str` | `marimo-labs/marimo:latest` |
| `build` | `object \| null` | `null` |
| `port` | `int` | `8080` |

### services.health

| フィールド | 型 | デフォルト |
|---|---|---|
| `enabled` | `bool` | `true` |
| `port` | `int` | `8888` |

---

## network セクション

| フィールド | 型 | デフォルト |
|---|---|---|
| `subnet` | `str` | `172.28.0.0/16` |

---

## cluster_test セクション

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `target` | `"cpu" \| "gpu"` | `"cpu"` | テスト接続先 |
| `test_network_subnet` | `str` | `172.30.0.0/24` | test-network subnet |
| `worker_node_manager_port` | `int` | `30000` | test-ray-worker NodeManager |
| `worker_object_manager_port` | `int` | `30001` | test-ray-worker ObjectManager |
| `worker_min_worker_port` | `int` | `30010` | test-ray-worker range min |
| `worker_max_worker_port` | `int` | `30020` | test-ray-worker range max |
| `worker_cpu_node_manager_port` | `int` | `30100` | test-ray-worker-cpu NodeManager |
| `worker_cpu_object_manager_port` | `int` | `30101` | test-ray-worker-cpu ObjectManager |
| `worker_cpu_min_worker_port` | `int` | `30110` | test-ray-worker-cpu range min |
| `worker_cpu_max_worker_port` | `int` | `30120` | test-ray-worker-cpu range max |

注意:
- `target=gpu` では GPU 接続系テストを行い、追加で CPU 側検証ワーカーが生成されます。
- CPU/GPU 同時起動は cluster-test（検証用途）を前提にしてください。

---

## nodes セクション

### nodes.head_whitelist

- 型: `list[str]`
- 空リスト不可

### nodes.head_address

- 型: `str | null`
- 固定接続先を明示したいときのみ設定

### nodes.health_service

| フィールド | 型 | デフォルト |
|---|---|---|
| `url` | `str` | `http://health:8080` |
| `timeout` | `int` | `1` |
| `max_retries` | `int` | `3` |
| `retry_interval` | `float` | `0.5` |

### nodes.cluster

| フィールド | 型 | デフォルト |
|---|---|---|
| `discovery_timeout` | `int` | `5` |
| `wait_for_head` | `int` | `30` |

---

## 環境変数オーバーライド

命名規則:
- プレフィックス: `CSLR_`
- ネスト区切り: `__`

例:

```bash
CSLR_SERVICES__RAY__CPU__CPUS=8
CSLR_SERVICES__RAY__GPU__IMAGE=rayproject/ray:latest-gpu
CSLR_CLUSTER_TEST__TARGET=gpu
CSLR_NETWORK__SUBNET=10.0.0.0/16
CSLR_NODES__HEAD_WHITELIST=ray-cpu,ray-gpu
```

---

## バリデーションルール

- `network.subnet`, `cluster_test.test_network_subnet` は CIDR 形式
- `memory` は `^\d+[gmGM]$`
- ポートは 1024-65535
- `head_whitelist` は空不可
- `min_worker_port` と `max_worker_port` は同時指定必須かつ `min <= max`
- `cluster_test` の worker ポート範囲は `min <= max`
- ポート重複（サービス間・cluster_test固定ポート）は禁止

---

## 運用ポリシー

### 1) 重要点

- 通常運用では `ray-cpu` / `ray-gpu` を同時に有効化しない前提です。
- CPU/GPU 同時起動は `cluster_test`（`ws test`）用途に限定します。

### 2) 実行レベル制限

- 同時起動の制限は設定バリデーションではなく、コマンド実行時に適用します。
- `ws up ray-cpu ray-gpu` はエラー終了し、通常 compose の同時起動を防止します。

### 3) future マーク方針

- 次の項目は将来拡張のために保持する future/reserved 項目です。
  - `host.hostname`
  - `services.ray.cpu.address` / `services.ray.gpu.address`
  - `volumes.ray_data`
- これらは現時点で主要な起動制御には使わず、互換性維持と将来機能の拡張余地として扱います。

---

## 関連ドキュメント

- [README.md](../README.md)
- [docs/architecture.md](architecture.md)
- [notes/test-cluster-readme.md](../notes/test-cluster-readme.md)
