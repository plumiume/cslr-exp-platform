# Troubleshooting Guide

CSLR Experiment Platform で発生する一般的な問題と解決方法

## 目次

- [設定とバリデーション](#設定とバリデーション)
- [クラスター起動の問題](#クラスター起動の問題)
- [ネットワーク接続の問題](#ネットワーク接続の問題)
- [Ray クラスターの問題](#ray-クラスターの問題)
- [GPU関連の問題](#gpu関連の問題)
- [パフォーマンスの問題](#パフォーマンスの問題)
- [データ永続化の問題](#データ永続化の問題)
- [デバッグ手法](#デバッグ手法)

---

## 設定とバリデーション

### ❌ Error: nodes.yaml is no longer supported

**症状**:
```
❌ nodes.yaml is no longer supported.
Please move nodes settings into config.yaml > nodes section.
```

**原因**: 
プロジェクトルートに古い `nodes.yaml` ファイルが残っている。

**解決方法**:

1. **`nodes.yaml` の内容を確認**
   ```bash
   cat nodes.yaml
   ```

2. **`config.yaml` に統合**
   ```yaml
   # config.yaml に追加
   nodes:
     head_whitelist:
       - ray-cpu
       - ray-gpu
     head_address: null
     health_service:
       url: "http://health:8080"
       timeout: 1
       max_retries: 3
       retry_interval: 2
     cluster:
       discovery_timeout: 5
       wait_for_head: 30
   ```

3. **古いファイルを削除**
   ```bash
   rm nodes.yaml
   ```

4. **設定を再生成**
   ```bash
   uv run ws generate
   ```

詳細は [CHANGELOG.md](../CHANGELOG.md#breaking-changes) を参照。

---

### ❌ Validation Error: Invalid subnet format

**症状**:
```
pydantic_core._pydantic_core.ValidationError: Invalid subnet format
```

**原因**: 
`config.yaml` の `network.subnet` が正しい CIDR 形式でない。

**解決方法**:

```yaml
# ❌ 間違い
network:
  subnet: "172.28.0.0"  # CIDR マスクがない

# ❌ 間違い
network:
  subnet: "172.28.0.0/33"  # CIDR マスクが無効（最大 /32）

# ✅ 正しい
network:
  subnet: "172.28.0.0/16"
```

**CIDR マスクの選び方**:
- `/24`: 256 アドレス（小規模クラスター）
- `/16`: 65,536 アドレス（中規模クラスター）
- `/8`: 16,777,216 アドレス（大規模クラスター）

---

### ❌ Validation Error: Invalid memory format

**症状**:
```
pydantic_core._pydantic_core.ValidationError: Memory format must match pattern ^\d+[gmGM]$
```

**原因**: 
メモリサイズのフォーマットが間違っている。

**解決方法**:

```yaml
# ❌ 間違い
services:
  ray:
    cpu:
      memory: "8GB"  # "GB" は不可
      memory: "8000m"  # 単位なし
      memory: "8gigabytes"  # 単位が間違い

# ✅ 正しい
services:
  ray:
    cpu:
      memory: "8g"   # ギガバイト（小文字）
      memory: "8G"   # ギガバイト（大文字）
      memory: "8192m"  # メガバイト（小文字）
      memory: "8192M"  # メガバイト（大文字）
```

---

### ❌ Validation Error: Port conflict detected

**症状**:
```
pydantic_core._pydantic_core.ValidationError: Port 6379 is used multiple times
```

**原因**: 
複数のサービスで同じホスト側ポートを使用している。

**解決方法**:

```yaml
# ❌ 間違い - ポート競合
services:
  ray:
    cpu:
      head_port: 6379  # Ray CPU
  redis:
    port: 6379  # Redis - 競合！

# ✅ 正しい - 異なるポート
services:
  ray:
    cpu:
      head_port: 6379  # Ray CPU
  redis:
    port: 6381  # Redis - 競合なし
```

**推奨ポート配置**:
- Ray CPU Head: 6379
- Ray GPU Head: 6380
- Redis: 6381
- Ray CPU Dashboard: 8265
- Ray GPU Dashboard: 8266
- MLflow: 5000
- Marimo: 8080
- Health: 8888

---

### ❌ Validation Error: head_whitelist cannot be empty

**症状**:
```
pydantic_core._pydantic_core.ValidationError: head_whitelist must not be empty
```

**原因**: 
`nodes.head_whitelist` が空リストまたは未設定。

**解決方法**:

```yaml
# ❌ 間違い
nodes:
  head_whitelist: []  # 空リスト

# ✅ 正しい
nodes:
  head_whitelist:
    - ray-cpu    # 最低1つは必要
    - ray-gpu    # 複数推奨
```

---

## クラスター起動の問題

### ❌ Service fails to start immediately

**症状**:
```bash
❯ uv run ws up -d
...
✘ ray-cpu exited with code 1
```

**診断手順**:

1. **ログを確認**
   ```bash
   uv run ws logs ray-cpu --tail 50
   ```

2. **コンテナステータス確認**
   ```bash
   uv run ws ps
   docker compose -f _build/compose.yaml ps -a
   ```

3. **個別サービス起動テスト**
   ```bash
   # Health サービスのみ起動
   docker compose -f _build/compose.yaml up health
   
   # Ray CPU サービスのみ起動
   docker compose -f _build/compose.yaml up ray-cpu
   ```

**よくある原因**:
- Health サービスが先に起動していない → `depends_on` を確認
- 設定ファイルのバリデーションエラー → `uv run ws generate` で再生成
- Docker イメージが存在しない → `uv run ws up --build`

---

### ❌ Container starts but exits immediately

**症状**:
コンテナが起動するがすぐに終了する（`Exited (0)` または `Exited (1)`）。

**診断手順**:

1. **終了コードを確認**
   ```bash
   docker compose -f _build/compose.yaml ps -a
   ```
   - `Exited (0)`: 正常終了（スクリプトが早期終了）
   - `Exited (1)`: エラー終了（ログを確認）

2. **コンテナログの最後を確認**
   ```bash
   uv run ws logs ray-cpu --tail 100
   ```

3. **エントリポイントを直接実行**
   ```bash
   docker compose -f _build/compose.yaml run --rm ray-cpu /bin/bash
   # コンテナ内で
   /template/ray-ep.sh
   ```

**よくある原因**:
- `ray-ep.sh` のパーミッション問題 → `chmod +x template/ray-ep.sh`
- 環境変数が正しく注入されていない → `docker inspect` で確認
- ヘルスチェックサービスが応答しない → `curl http://health:8080` をコンテナ内から実行

---

## ネットワーク接続の問題

### ❌ Cannot connect to health service

**症状**:
```
ray-ep.sh: Health check failed, starting as HEAD
```

**診断手順**:

1. **Health サービスの状態確認**
   ```bash
   uv run ws ps
   docker compose -f _build/compose.yaml logs health
   ```

2. **ネットワーク接続テスト**
   ```bash
   # Ray CPU コンテナから Health サービスに接続
   docker compose -f _build/compose.yaml exec ray-cpu curl -v http://health:8080
   ```

3. **DNS解決確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu nslookup health
   docker compose -f _build/compose.yaml exec ray-cpu ping -c 3 health
   ```

**解決方法**:

```yaml
# Health サービスが正しく定義されているか確認
services:
  health:
    image: python:3.12-slim
    networks:
      - ray-network  # 同じネットワークに属している必要がある
    ports:
      - "8888:8080"
```

Docker ネットワークを再作成:
```bash
uv run ws down
docker network rm cslr-exp-platform-issue4_ray-network
uv run ws up -d
```

---

### ❌ Worker cannot connect to Head node (シングルホスト)

**症状**:
```
ray-gpu: Cannot connect to Ray head node at ray-cpu:6379
```

**診断手順**:

1. **Head ノードが起動しているか確認**
   ```bash
   uv run ws ps
   docker compose -f _build/compose.yaml logs ray-cpu
   ```

2. **ポート接続テスト**
   ```bash
   docker compose -f _build/compose.yaml exec ray-gpu nc -zv ray-cpu 6379
   ```

3. **Ray Head の状態確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ray status
   ```

**解決方法**:

- **起動順序を確認**: `ray-cpu` が先に起動する必要がある
  ```bash
  uv run ws down
  # ray-cpu を先に起動
  docker compose -f _build/compose.yaml up -d health ray-cpu
  sleep 10
  # その後 ray-gpu を起動
  docker compose -f _build/compose.yaml up -d ray-gpu
  ```

- **Whitelist 設定を確認**:
  ```yaml
  nodes:
    head_whitelist:
      - ray-cpu  # このホスト名と一致する必要がある
  ```

- **Docker ホスト名を確認**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-cpu hostname
  # 出力: ray-cpu
  ```

---

### ❌ Worker cannot connect to Head node (マルチホスト)

**症状**:
```
ray-cpu-host-b: Cannot connect to Ray head node at ray-cpu-host-a:6379
```

**診断手順**:

1. **ホスト名解決の確認（Host B から Host A）**
   ```bash
   # Host B のコンテナから
   docker compose -f _build/compose.yaml exec ray-cpu ping -c 3 ray-cpu-host-a
   ```

2. **物理ネットワークの接続確認**
   ```bash
   # Host B のホスト OS から Host A に接続
   ping -c 3 192.168.1.10  # Host A の IP
   ```

3. **ファイアウォールの確認（Host A）**
   ```bash
   # Host A で Ray ポートが開放されているか確認
   sudo ufw status | grep 6379
   ```

**解決方法**:

**1. ホスト名解決の設定（各ホストで）**:

```bash
# /etc/hosts に追加
sudo nano /etc/hosts

192.168.1.10 ray-cpu-host-a
192.168.1.10 ray-gpu-host-a
192.168.1.11 ray-cpu-host-b
192.168.1.11 ray-gpu-host-b
```

**2. Docker Compose でホスト名を設定**:

```yaml
# Host A の config.yaml
services:
  ray:
    cpu:
      hostname: ray-cpu-host-a  # Whitelist と一致
```

**3. ファイアウォールの設定（Host A）**:

```bash
# Ray ポートを開放
sudo ufw allow 6379/tcp  # Ray Head port
sudo ufw allow 8265/tcp  # Dashboard port
sudo ufw allow 10001/tcp # Ray Client port

# 設定を有効化
sudo ufw reload
```

**4. ネットワークモードの検討**:

Docker の `bridge` ネットワークは単一ホスト内でのみ動作します。マルチホストでは以下のオプションを検討:

- **Host Network モード**:
  ```yaml
  services:
    ray-cpu:
      network_mode: host
  ```
  利点: ネットワークオーバーヘッドなし  
  欠点: ポート競合の管理が必要

- **Overlay Network** (Docker Swarm):
  ```bash
  docker swarm init
  docker network create -d overlay ray-overlay
  ```

---

## Ray クラスターの問題

### ❌ GCS health check failures

**症状**:
```
Ray GCS health check failed: Connection refused
```

**原因**: 
Ray の Global Control Service (GCS) に接続できない。

**診断手順**:

1. **Ray Head の起動確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ray status
   ```

2. **GCS プロセスの確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ps aux | grep gcs
   ```

3. **Raylet ログの確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu cat /tmp/ray/session_latest/logs/gcs_server.out
   ```

**解決方法**:

- **ノード IP の問題**: 単一ネットワークでは自動検出で動作しますが、ネットワーク分離/NAT 環境では `--node-ip-address` で到達可能な IP を指定してください。

- **GCS の再起動**:
  ```bash
  uv run ws down
  uv run ws up -d
  ```

- **Ray のクリーン再起動**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-cpu ray stop
  docker compose -f _build/compose.yaml exec ray-cpu rm -rf /tmp/ray
  docker compose -f _build/compose.yaml restart ray-cpu
  ```

---

### ❌ Ray Dashboard not accessible

**症状**:
ブラウザで `http://localhost:8265` にアクセスできない。

**診断手順**:

1. **Dashboard ポートのマッピング確認**
   ```bash
   docker compose -f _build/compose.yaml ps
   # ray-cpu の PORTS 列を確認: 0.0.0.0:8265->8265/tcp
   ```

2. **Dashboard プロセスの確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu netstat -tuln | grep 8265
   ```

3. **Ray ログの確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu cat /tmp/ray/session_latest/logs/dashboard.log
   ```

**解決方法**:

- **ポートマッピングの修正**:
  ```yaml
  # config.yaml
  services:
    ray:
      cpu:
        dashboard_port: 8265  # これがホスト側ポート
  ```

- **ファイアウォールの確認**:
  ```bash
  # Linux
  sudo ufw allow 8265/tcp
  
  # Windows (PowerShell 管理者)
  New-NetFirewallRule -DisplayName "Ray Dashboard" -Direction Inbound -LocalPort 8265 -Protocol TCP -Action Allow
  ```

- **Dashboard の明示的な起動**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-cpu ray start --head --dashboard-host=0.0.0.0 --dashboard-port=8265
  ```

---

### ❌ Ray Client connection refused

**症状**:
```python
import ray
ray.init("ray://localhost:10001")
# ConnectionError: Failed to connect to Ray cluster
```

**診断手順**:

1. **Client Server が有効か確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu netstat -tuln | grep 10001
   ```

2. **Ray Head のステータス確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ray status
   ```

**解決方法**:

- **Client Server を有効化**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-cpu ray start --head --ray-client-server-port=10001
  ```

- **ポートマッピングの確認**:
  ```yaml
  services:
    ray:
      cpu:
        client_port: 10001
        ports:
          - "${RAY_CPU_CLIENT_PORT:-10001}:10001"
  ```

- **Python から接続**:
  ```python
  import ray
  
  # クラスター内から接続
  ray.init()  # 自動検出
  
  # 外部から接続
  ray.init("ray://localhost:10001")
  
  # リソース確認
  print(ray.cluster_resources())
  ```

---

## GPU関連の問題

### ❌ GPU not detected in Ray

**症状**:
```python
ray.get_gpu_ids()  # []（空リスト）
```

**診断手順**:

1. **ホスト側で GPU 確認**
   ```bash
   nvidia-smi
   ```

2. **コンテナ内で GPU 確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-gpu nvidia-smi
   ```

3. **Ray が GPU を認識しているか確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-gpu ray status
   # Resources: {'GPU': 1, ...} と表示されるはず
   ```

**解決方法**:

- **NVIDIA Docker Runtime の確認**:
  ```bash
  docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi
  ```

- **docker-compose.yaml の確認**:
  ```yaml
  services:
    ray-gpu:
      deploy:
        resources:
          reservations:
            devices:
              - driver: nvidia
                capabilities: [gpu]
  ```

- **Ray の GPU 設定**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-gpu ray start --num-gpus=1
  ```

- **CUDA の可視性を確認**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-gpu python -c "import torch; print(torch.cuda.is_available())"
  ```

---

### ❌ CUDA version mismatch

**症状**:
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
```

**原因**: 
Docker イメージの CUDA バージョンとホストの GPU ドライバーが不一致。

**診断手順**:

1. **ホストの CUDA ドライバーバージョン確認**
   ```bash
   nvidia-smi
   # Driver Version: 535.129.03   CUDA Version: 12.2
   ```

2. **コンテナの CUDA バージョン確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-gpu nvcc --version
   ```

**解決方法**:

- **互換性マトリックス**:
  | Driver Version | 最大 CUDA Version |
  |----------------|-------------------|
  | 535.x          | 12.2              |
  | 545.x          | 12.3              |
  | 550.x          | 12.4              |

- **適切なイメージを使用**:
  ```yaml
  services:
    ray:
      gpu:
        image: "rayproject/ray:2.9.0-gpu"  # CUDA 11.8
        # または
        image: "plumiume/cslr-exp-platform:marimo-torch2.8.0-cu128-py313-runtime"  # CUDA 12.8
  ```

参考: [NVIDIA CUDA Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/)

---

## パフォーマンスの問題

### ⚠️ Slow task execution

**症状**:
Ray タスクの実行が異常に遅い。

**診断手順**:

1. **リソース使用率を確認**
   ```bash
   # ホスト側
   docker stats
   
   # Ray Dashboard で確認
   open http://localhost:8265
   ```

2. **Ray Plasma Store の状態確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ray memory --stats-only
   ```

3. **ネットワーク遅延の確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-gpu ping -c 10 ray-cpu
   ```

**解決方法**:

- **共有メモリ (shm_size) の増加**:
  ```yaml
  services:
    ray:
      cpu:
        shm_size: "8g"  # デフォルトより大きく
  ```
  Ray は `/dev/shm` をオブジェクトストアに使用します。

- **CPU/メモリリソースの増加**:
  ```yaml
  services:
    ray:
      cpu:
        cpus: "16"     # より多くのコア
        memory: "32g"  # より多いメモリ
  ```

- **Workers の数を調整**:
  ```python
  # Python コード内で
  @ray.remote(num_cpus=2, num_gpus=1)
  def my_task():
      pass
  ```

---

### ⚠️ Out of memory errors

**症状**:
```
ray.exceptions.OutOfMemoryError: Task failed with out of memory error
```

**診断手順**:

1. **メモリ使用状況確認**
   ```bash
   docker stats ray-cpu ray-gpu
   ```

2. **Plasma Store の使用量確認**
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu ray memory
   ```

**解決方法**:

- **オブジェクトストアメモリの増加**:
  ```bash
  docker compose -f _build/compose.yaml exec ray-cpu ray start --head --object-store-memory=10000000000  # 10GB
  ```

- **shm_size の増加**:
  ```yaml
  services:
    ray:
      cpu:
        shm_size: "16g"  # より大きく
  ```

- **データのチャンク化**:
  ```python
  # 大きなデータセットを小さく分割
  @ray.remote
  def process_chunk(chunk):
      return some_processing(chunk)
  
  results = ray.get([process_chunk.remote(c) for c in chunks])
  ```

---

## データ永続化の問題

### ❌ MLflow data lost after restart

**症状**:
`uv run ws down` 後に MLflow の実験データが消える。

**原因**: 
ボリュームが削除された。

**解決方法**:

- **ボリュームを保持して停止**:
  ```bash
  uv run ws down  # ボリュームは残る
  ```

- **ボリュームも削除する場合**（注意！）:
  ```bash
  uv run ws down -v  # すべてのデータが削除される
  ```

- **ボリュームの確認**:
  ```bash
  docker volume ls | grep mlflow
  ```

- **バックアップの作成**:
  ```bash
  # PostgreSQL データのバックアップ
  docker compose -f _build/compose.yaml exec mlflow-postgres pg_dump -U mlflow mlflow > mlflow_backup.sql
  
  # リストア
  docker compose -f _build/compose.yaml exec -T mlflow-postgres psql -U mlflow mlflow < mlflow_backup.sql
  ```

---

### ❌ Marimo notebooks not persisted

**症状**:
Marimo で作成したノートブックが再起動後に消える。

**解決方法**:

- **ホストディレクトリをマウント**:
  ```yaml
  services:
    marimo:
      volumes:
        - ./notebooks:/notebooks  # ホストのディレクトリにマップ
  ```

- **既存ノートブックの保存**:
  ```bash
  # コンテナからホストにコピー
  docker compose -f _build/compose.yaml cp marimo:/notebooks ./notebooks
  ```

---

## デバッグ手法

### 詳細ログの有効化

```bash
# Ray のデバッグログ
docker compose -f _build/compose.yaml exec ray-cpu ray start --head --log-style=pretty --verbose

# Docker Compose のデバッグ
docker compose -f _build/compose.yaml --verbose up
```

### インタラクティブデバッグ

```bash
# コンテナに入る
docker compose -f _build/compose.yaml exec ray-cpu /bin/bash

# 環境変数を確認
env | grep RAY
env | grep HEAD

# エントリポイントを手動実行
bash -x /template/ray-ep.sh  # デバッグモード
```

### ネットワークデバッグツール

```bash
# コンテナにツールをインストール
docker compose -f _build/compose.yaml exec ray-cpu apt-get update && apt-get install -y dnsutils netcat-openbsd iputils-ping

# DNS 確認
nslookup ray-cpu
nslookup health

# ポート接続確認
nc -zv ray-cpu 6379

# ネットワーク遅延確認
ping -c 10 ray-cpu
```

### Ray 内部状態の確認

```python
import ray

ray.init("ray://localhost:10001")

# クラスターリソースの確認
print(ray.cluster_resources())

# ノード情報の確認
print(ray.nodes())

# タスク/アクターの状態確認
print(ray.list_tasks())
print(ray.list_actors())

# メモリ使用状況
print(ray.memory())
```

### ヘルスチェックエンドポイント

```bash
# Health Service
curl http://localhost:8888/

# Ray Dashboard API
curl http://localhost:8265/api/cluster_status

# MLflow
curl http://localhost:5000/health
```

---

## よくある質問

### Q: ホワイトリストに登録したのに Worker モードで起動する

**A**: 以下を確認してください:

1. コンテナの `hostname` が Whitelist と一致しているか
   ```bash
   docker compose -f _build/compose.yaml exec ray-cpu hostname
   ```

2. Health サービスが起動しているか
   ```bash
   curl http://localhost:8888
   ```

3. 他のノードが既に HEAD として起動していないか
   ```bash
   docker compose -f _build/compose.yaml logs ray-cpu | grep "Starting Ray head"
   ```

### Q: Docker Compose generation が遅い

**A**: Python 環境を最適化してください:

```bash
# uv のキャッシュをクリア
uv cache clean

# プロジェクトの再インストール
uv sync --all-extras
```

### Q: GPU ノードが CPU タスクを実行してしまう

**A**: タスクに GPU 要件を明示してください:

```python
@ray.remote(num_gpus=1)  # GPU が必要
def gpu_task():
    import torch
    return torch.cuda.is_available()

@ray.remote  # GPU 不要（CPU ノードで実行される）
def cpu_task():
    return some_computation()
```

---

## サポート

問題が解決しない場合:

1. **ログの収集**:
   ```bash
   uv run ws logs > cluster_logs.txt
   docker compose -f _build/compose.yaml ps -a > cluster_status.txt
   ```

2. **Issue を作成**: [GitHub Issues](https://github.com/plumiume/cslr-exp-platform/issues)
   - ログファイルを添付
   - `config.yaml` の（機密情報を除く）内容
   - 環境情報（OS, Docker バージョンなど）

3. **関連ドキュメント**:
   - [README.md](../README.md)
   - [Configuration Reference](config-reference.md)
   - [System Architecture](architecture.md)
   - [CHANGELOG](../CHANGELOG.md)
