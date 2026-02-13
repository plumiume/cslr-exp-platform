# System Architecture

CSLR Experiment Platform のシステムアーキテクチャとデータフロー

## 目次

- [概要](#概要)
- [アーキテクチャ概観](#アーキテクチャ概観)
- [コンポーネント構成](#コンポーネント構成)
- [設定生成フロー](#設定生成フロー)
- [Ray クラスター起動フロー](#ray-クラスター起動フロー)
- [Head/Worker 判定ロジック](#headworker-判定ロジック)
- [ネットワークアーキテクチャ](#ネットワークアーキテクチャ)
- [データ永続化](#データ永続化)

---

## 概要

CSLR Experiment Platform は、以下の設計原則に基づいています:

- **宣言的設定**: `config.yaml` でクラスター全体を定義
- **テンプレートベース**: Jinja2 テンプレートから Docker Compose 設定を生成
- **自動検出**: Head/Worker ロールを起動時に自動判定
- **マルチホスト対応**: 複数の物理ホストで分散クラスターを構築可能

---

## アーキテクチャ概観

```mermaid
graph TB
    subgraph "開発者環境"
        CONFIG[config.yaml]
        ENV[.env]
        WS[ws CLI]
    end

    subgraph "設定生成"
        MODELS[Pydantic Models]
        VALIDATE[Validation]
        TEMPLATE[Jinja2 Templates]
        COMPOSE[Docker Compose YAML]
    end

    subgraph "Docker 環境"
        HEALTH[Health Check Service]
        RAY_CPU[Ray CPU Node]
        RAY_GPU[Ray GPU Node]
        REDIS[Redis Cache]
        MLFLOW[MLflow Tracking]
        POSTGRES[PostgreSQL]
        MARIMO[Marimo Notebook]
    end

    CONFIG --> MODELS
    ENV --> MODELS
    MODELS --> VALIDATE
    VALIDATE --> TEMPLATE
    TEMPLATE --> COMPOSE
    WS --> MODELS
    COMPOSE --> HEALTH
    COMPOSE --> RAY_CPU
    COMPOSE --> RAY_GPU
    COMPOSE --> REDIS
    COMPOSE --> MLFLOW
    COMPOSE --> POSTGRES
    COMPOSE --> MARIMO

    HEALTH <-.ヘルスチェック.-> RAY_CPU
    HEALTH <-.ヘルスチェック.-> RAY_GPU
    RAY_CPU <-.クラスター接続.-> RAY_GPU
    MLFLOW --> POSTGRES
```

---

## コンポーネント構成

### 1. 設定管理層

#### config.yaml
- **役割**: 全設定の単一ソース
- **フォーマット**: YAML
- **管理対象**: サービス有効/無効、リソース制限、ポート、ネットワーク、ノード設定

#### .env ファイル（オプション）
- **役割**: 機密情報とローカル設定の管理
- **優先度**: `config.yaml` より高い
- **用途**: パスワード、環境固有の設定

#### Pydantic Models (ws_src/models.py)
- **役割**: 設定の型定義とバリデーション
- **機能**:
  - `BaseSettings` による環境変数統合
  - CIDR、メモリ、ポートのバリデーション
  - JSON Schema 生成

### 2. テンプレートエンジン層

#### ws CLI (ws_src/commands.py)
- **役割**: ユーザーインターフェース
- **コマンド**: `init`, `generate`, `up`, `down`, `ps`, `logs`, `test`, `schema`
- **機能**: 設定読み込み、テンプレート処理、Docker Compose 呼び出し

#### WorkspaceManager (ws_src/manager.py)
- **役割**: テンプレート処理とファイル生成
- **機能**:
  - `load_config()`: 設定読み込みと検証
  - `detect_host_state()`: GPU 自動検出
  - `generate_compose_file()`: メイン Compose 生成
  - `generate_cluster_test_file()`: テスト Compose 生成
  - Legacy `nodes.yaml` 検出

#### Jinja2 Templates (template/)
- **compose.yaml.jinja2**: メインクラスター定義
- **cluster-test.compose.yaml.jinja2**: テストコンテナ定義
- **ray-ep.sh**: Ray ノードエントリポイント
- **health-ep.sh**: ヘルスチェックサーバー

### 3. ランタイム層

#### Health Check Service
- **役割**: ノード状態の監視と Head 候補の追跡
- **実装**: Python Flask（`template/health-ep.sh`）
- **エンドポイント**:
  - `GET /`: ヘルスステータス
  - 将来: ノード登録とリーダー選出

#### Ray Nodes
- **CPU ノード**: 汎用計算ノード
- **GPU ノード**: CUDA 対応計算ノード
- **起動スクリプト**: `ray-ep.sh`
- **モード**: Head または Worker（自動判定）

#### 統合サービス
- **MLflow**: 実験トラッキングとモデルレジストリ
- **Redis**: キャッシュと共有ストレージ
- **Marimo**: インタラクティブノートブック
- **PostgreSQL**: MLflow バックエンド

---

## 設定生成フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as ws CLI
    participant Manager as WorkspaceManager
    participant Config as Config
    participant Validator
    participant Jinja as Jinja2
    participant File as _build/compose.yaml

    User->>CLI: uv run ws generate
    CLI->>Manager: generate_compose_file()
    
    Manager->>Config: load_config()
    Config->>Config: Read config.yaml
    Config->>Config: Read .env
    Config->>Validator: Validate settings
    
    alt nodes.yaml exists
        Validator-->>CLI: ❌ Error: Migration required
    end
    
    Validator->>Validator: Check subnet CIDR
    Validator->>Validator: Check memory format
    Validator->>Validator: Check port conflicts
    Validator->>Validator: Check head_whitelist
    
    Validator-->>Manager: ✅ Validated Config
    
    Manager->>Manager: detect_host_state()
    Manager->>Manager: Check nvidia-smi
    
    Manager->>Jinja: render(compose.yaml.jinja2)
    Jinja->>Jinja: Inject environment variables
    Jinja->>Jinja: Apply conditions
    Jinja-->>Manager: Rendered YAML
    
    Manager->>File: Write compose.yaml
    File-->>CLI: Generation complete
    CLI-->>User: ✅ Generated _build/compose.yaml
```

### 主要ステップ

1. **設定読み込み**: `config.yaml` + `.env` + 環境変数
2. **Legacy 検出**: `nodes.yaml` が存在する場合はエラー
3. **バリデーション**: Pydantic によるフィールドチェック
4. **GPU 検出**: `nvidia-smi` でホストのGPU状態を確認
5. **テンプレート処理**: Jinja2 でプレースホルダーを置換
6. **環境変数注入**: `nodes` 設定を環境変数として埋め込み
7. **ファイル出力**: `_build/compose.yaml` に書き込み

---

## Ray クラスター起動フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as ws CLI
    participant Docker as Docker Compose
    participant Health as health
    participant RayCPU as ray-cpu
    participant RayGPU as ray-gpu

    User->>CLI: uv run ws up -d
    CLI->>CLI: generate_compose_file()
    CLI->>Docker: docker compose up -d
    
    Docker->>Health: Start health service
    Health->>Health: Start Flask server :8080
    
    Docker->>RayCPU: Start ray-cpu
    RayCPU->>RayCPU: Run ray-ep.sh
    RayCPU->>RayCPU: Read ENV vars
    RayCPU->>RayCPU: Check whitelist
    RayCPU->>Health: Check connectivity
    
    alt Health available
        Health-->>RayCPU: 200 OK
        RayCPU->>RayCPU: Search existing Head
        RayCPU->>RayCPU: No Head found
        RayCPU->>RayCPU: Start as HEAD
    else Health unavailable
        RayCPU->>RayCPU: Start as HEAD (failsafe)
    end
    
    Docker->>RayGPU: Start ray-gpu
    RayGPU->>RayGPU: Run ray-ep.sh
    RayGPU->>RayGPU: Read ENV vars
    RayGPU->>Health: Check connectivity
    Health-->>RayGPU: 200 OK
    
    RayGPU->>RayCPU: Try TCP connection :6379
    RayCPU-->>RayGPU: Connected
    RayGPU->>RayGPU: Start as WORKER
    RayGPU->>RayCPU: ray start --address=ray-cpu:6379
```

### 起動シーケンス

1. **Docker Compose 起動**: サービスがほぼ同時に起動
2. **Health Service 先行**: 他のノードより先に準備完了
3. **CPU ノード起動**: Whitelist 照合 → Head として起動
4. **GPU ノード起動**: Whitelist 照合 → 既存 Head 検出 → Worker として起動

---

## Head/Worker 判定ロジック

`ray-ep.sh` による自動判定の詳細フロー

```mermaid
flowchart TD
    START([Container Start]) --> READ_ENV[環境変数読み込み]
    READ_ENV --> HOSTNAME[Self Hostname 取得]
    HOSTNAME --> CHECK_WL{Whitelist に含まれる?}
    
    CHECK_WL -->|No| ENV_ADDR{ENV: HEAD_ADDRESS 設定?}
    ENV_ADDR -->|Yes| USE_ENV[ENV の Address 使用]
    ENV_ADDR -->|No| CFG_ADDR{CFG: head_address 設定?}
    CFG_ADDR -->|Yes| USE_CFG[CFG の Address 使用]
    CFG_ADDR -->|No| USE_FIRST[Whitelist 最初のノード使用]
    USE_ENV --> WORKER[Worker モードで起動]
    USE_CFG --> WORKER
    USE_FIRST --> WORKER
    
    CHECK_WL -->|Yes| HEALTH_CHECK[Health Service 接続試行]
    HEALTH_CHECK --> HEALTH_OK{接続成功?}
    
    HEALTH_OK -->|No| HEAD[Head モードで起動<br/>Failsafe]
    
    HEALTH_OK -->|Yes| SCAN_START[Whitelist ノードをスキャン]
    SCAN_START --> TRY_CONNECT[TCP 接続試行<br/>Port: RAY_HEAD_PORT]
    TRY_CONNECT --> FOUND{既存 Head 発見?}
    
    FOUND -->|Yes| WORKER
    FOUND -->|No| MORE{他のノード残ってる?}
    MORE -->|Yes| TRY_CONNECT
    MORE -->|No| HEAD
    
    HEAD --> RAY_START_HEAD[ray start --head<br/>--port=RAY_HEAD_PORT]
    WORKER --> RAY_START_WORKER[ray start --address=HEAD_ADDR]
    
    RAY_START_HEAD --> END([Ray Running])
    RAY_START_WORKER --> END
```

### 判定条件の詳細

#### ホワイトリスト内ノード

| 条件 | Head | Worker |
|------|------|--------|
| Health 利用不可 | ✅ Failsafe | - |
| 既存 Head なし | ✅ First node | - |
| 既存 Head あり | - | ✅ Join cluster |

#### ホワイトリスト外ノード

常に Worker モードで起動し、以下の優先順位で接続先を決定:

1. 環境変数 `HEAD_ADDRESS`（最優先）
2. `config.yaml` の `nodes.head_address`
3. `nodes.head_whitelist` の最初のノード + `RAY_HEAD_PORT`

---

## ネットワークアーキテクチャ

### シングルホスト構成

```mermaid
graph TB
    subgraph "Physical Host"
        subgraph "Docker Network: ray-network (172.28.0.0/16)"
            HEALTH[health<br/>172.28.0.2]
            RAY_CPU[ray-cpu<br/>172.28.0.10]
            RAY_GPU[ray-gpu<br/>172.28.0.11]
            REDIS[ray-redis<br/>172.28.0.20]
            MLFLOW[mlflow<br/>172.28.0.30]
            POSTGRES[mlflow-postgres<br/>172.28.0.31]
            MARIMO[marimo<br/>172.28.0.40]
        end
        
        HOST_PORTS[Host Ports]
    end
    
    RAY_CPU <--> RAY_GPU
    RAY_CPU --> REDIS
    RAY_GPU --> REDIS
    MLFLOW --> POSTGRES
    
    HOST_PORTS -.8888.-> HEALTH
    HOST_PORTS -.6379.-> RAY_CPU
    HOST_PORTS -.6380.-> RAY_GPU
    HOST_PORTS -.8265.-> RAY_CPU
    HOST_PORTS -.8266.-> RAY_GPU
    HOST_PORTS -.6381.-> REDIS
    HOST_PORTS -.5000.-> MLFLOW
    HOST_PORTS -.8080.-> MARIMO
```

### マルチホスト構成

```mermaid
graph TB
    subgraph "Host A (192.168.1.10)"
        subgraph "Docker Network A: ray-network"
            HEALTH_A[health]
            RAY_CPU_A[ray-cpu-host-a<br/>HEAD]
            RAY_GPU_A[ray-gpu-host-a<br/>WORKER]
        end
    end
    
    subgraph "Host B (192.168.1.11)"
        subgraph "Docker Network B: ray-network"
            HEALTH_B[health]
            RAY_CPU_B[ray-cpu-host-b<br/>WORKER]
            RAY_GPU_B[ray-gpu-host-b<br/>WORKER]
        end
    end
    
    subgraph "Physical Network"
        NET[192.168.1.0/24]
    end
    
    RAY_GPU_A -.Worker join.-> RAY_CPU_A
    RAY_CPU_B -.Worker join.-> RAY_CPU_A
    RAY_GPU_B -.Worker join.-> RAY_CPU_A
    
    RAY_CPU_A --- NET
    RAY_CPU_B --- NET
    RAY_GPU_A --- NET
    RAY_GPU_B --- NET
```

**重要な設定**:

1. **ホスト名解決**: 各ホストで `/etc/hosts` または DNS 設定
   ```bash
   # Host A と Host B の /etc/hosts
   192.168.1.10 ray-cpu-host-a
   192.168.1.10 ray-gpu-host-a
   192.168.1.11 ray-cpu-host-b
   192.168.1.11 ray-gpu-host-b
   ```

2. **Firewall**: Ray ポートの開放
   ```bash
   # Host A
   sudo ufw allow 6379/tcp  # Ray Head port
   sudo ufw allow 8265/tcp  # Dashboard port
   ```

3. **Docker Hostname**: `docker-compose.yaml` で明示的に設定
   ```yaml
   services:
     ray-cpu:
       hostname: ray-cpu-host-a  # Whitelist と一致
   ```

---

## データ永続化

### ボリューム構成

```yaml
volumes:
  mlflow-data:        # MLflow アーティファクト
  postgres-data:      # PostgreSQL データベース
  redis-data:         # Redis 永続化（オプション）
  marimo-notebooks:   # Marimo ノートブック
  ray-temp:           # Ray 一時ファイル
```

### ディレクトリマウント

```mermaid
graph LR
    subgraph "Host Filesystem"
        HOST_TEMPLATE[template/]
        HOST_CONFIG[config.yaml]
        HOST_BUILD[_build/]
    end
    
    subgraph "Container Filesystem"
        CONT_TEMPLATE[/template/]
        CONT_BUILD[/build/]
    end
    
    HOST_TEMPLATE -.ro.-> CONT_TEMPLATE
    HOST_BUILD -.rw.-> CONT_BUILD
```

**マウントのポリシー**:
- **Read-Only (ro)**: テンプレート、スクリプト（コンテナは変更しない）
- **Read-Write (rw)**: ログ、生成ファイル（コンテナが書き込む）
- **Named Volume**: データベース、永続ストレージ

---

## セキュリティ考慮事項

### 機密情報の管理

```mermaid
flowchart LR
    SECRET[機密情報] --> ENV_VAR[環境変数]
    SECRET --> DOTENV[.env ファイル]
    SECRET --> VAULT[外部 Secret Manager]
    
    ENV_VAR --> PYDANTIC[Pydantic Settings]
    DOTENV --> PYDANTIC
    VAULT --> ENV_VAR
    
    PYDANTIC --> TEMPLATE[Jinja2 Template]
    TEMPLATE --> COMPOSE[Docker Compose]
    
    GITIGNORE[.gitignore] -.block.-> DOTENV
    GITIGNORE -.block.-> COMPOSE
```

**推奨事項**:
1. `.env` ファイルで機密情報を管理（Git に含めない）
2. `config.yaml` にはプレースホルダーのみ記載
3. 本番環境では外部 Secret Manager（AWS Secrets Manager, HashiCorp Vault など）を使用

### ネットワークセキュリティ

- **内部通信**: Docker ネットワーク内で完結
- **外部公開**: 必要最小限のポートのみホストに露出
- **ファイアウォール**: マルチホストでは Ray ポートを適切に制限

---

## パフォーマンス最適化

### リソース配分戦略

#### CPU vs GPU ノード

| ノード | 推奨 CPU | 推奨メモリ | 推奨 SHM | 用途 |
|--------|---------|-----------|----------|------|
| CPU ノード | 4-8 コア | 8-16GB | 2-4GB | 汎用計算、前処理 |
| GPU ノード | 16-32 コア | 32-64GB | 8-16GB | 深層学習、推論 |

#### 共有メモリ (shm_size)

Ray はオブジェクトストアに `/dev/shm` を使用します:

```yaml
services:
  ray:
    gpu:
      shm_size: "16g"  # 大規模データセット処理に推奨
```

**計算式**: `shm_size ≈ memory × 0.3`（Ray オブジェクトストア用）

### ネットワーク最適化

- **サブネット サイズ**: `/16` (65,536 アドレス) を推奨
- **MTU**: デフォルト 1500、Jumbo Frame (9000) も検討可
- **DNS キャッシュ**: マルチホストでは DNS サーバーの使用を推奨

---

## トラブルシューティングフロー

```mermaid
flowchart TD
    ISSUE[問題発生] --> CHECK_LOGS[ログ確認: uv run ws logs]
    CHECK_LOGS --> LOG_TYPE{エラータイプ?}
    
    LOG_TYPE -->|Connection refused| NET_ISSUE[ネットワーク問題]
    LOG_TYPE -->|GCS health check| GCS_ISSUE[Ray GCS 問題]
    LOG_TYPE -->|Validation error| CFG_ISSUE[設定エラー]
    
    NET_ISSUE --> CHECK_HOST[ホスト名解決確認]
    CHECK_HOST --> CHECK_PORT[ポート接続確認]
    CHECK_PORT --> CHECK_FW[ファイアウォール確認]
    
    GCS_ISSUE --> CHECK_IP[ノード IP 確認]
    CHECK_IP --> CHECK_HEAD[Head ノード状態確認]
    
    CFG_ISSUE --> CHECK_YAML[config.yaml 検証]
    CHECK_YAML --> CHECK_SCHEMA[uv run ws schema generate]
    
    CHECK_FW --> RESOLVE[問題解決]
    CHECK_HEAD --> RESOLVE
    CHECK_SCHEMA --> RESOLVE
```

---

## 拡張性

### 今後のアーキテクチャ拡張

1. **Kubernetes サポート**: Helm チャートへの変換
2. **Auto-scaling**: Ray Autoscaler との統合
3. **モニタリング**: Prometheus + Grafana
4. **ログ集約**: ELK Stack または Loki
5. **サービスメッシュ**: Istio による高度なネットワーク制御

### プラグインアーキテクチャ

将来的に、カスタムサービスを追加可能な設計:

```yaml
# 将来の拡張例
services:
  custom:
    my_service:
      enabled: true
      image: "my-org/my-service:latest"
      port: 9000
```

---

## 関連ドキュメント

- [README.md](../README.md) - クイックスタート
- [docs/config-reference.md](config-reference.md) - 設定リファレンス
- [CHANGELOG.md](../CHANGELOG.md) - 変更履歴
- [notes/test-cluster-readme.md](../notes/test-cluster-readme.md) - テストクラスター
