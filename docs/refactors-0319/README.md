# Refactoring Proposal 2026-03-19: Ray CPU/GPU 設定の統合

## 概要

`config.yaml` および対応する Pydantic スキーマ（`ws_src/models.py`）における
`services.ray.cpu` / `services.ray.gpu` の分割構造の理由を分析し、
**`gpu: (base) + GPU固有設定`** という継承モデルへのリファクタリング案を比較する。

### このフォルダの構成

| ファイル | 内容 |
|---------|------|
| `README.md`（本ファイル） | 分割理由の分析・分離レイヤー選択肢・設定変更の全体比較 |
| [ray-default.md](./ray-default.md) | `ray.default` フォールバック設計の考察（`cpu`/`gpu` が共通値を参照する代替案） |
| [traefik-proxy.md](./traefik-proxy.md) | Traefik リバースプロキシ・ランダムポートの詳細検討 |

---

## 前提: 同時起動不可の原則

> **`ray-cpu` と `ray-gpu` は同時に起動しない。**  
> どちらか一方のみが本番クラスターの Head として動作する。

この原則により:

- ポートの重複（`head_port`, `dashboard_port`, `client_port`）は **問題にならない**
- 「2つの独立した Head を動的に切り替える」設計は **採用しない**
- CPU/GPU の分割理由として「ポート干渉回避」「独立 Head 設計」は **無効**

同時起動を排他制御する既存機構:

```yaml
# templates/compose.yaml.jinja2
  ray-cpu:
    profiles:
      - ray-cpu   # docker compose --profile ray-cpu up でのみ起動
  ray-gpu:
    profiles:
      - ray-gpu   # docker compose --profile ray-gpu up でのみ起動
```

一方を起動すると他方は起動されない構造がすでに存在している。

---

## 1. なぜ CPU と GPU が分割されているか（有効な理由のみ）

### 1-1. Docker ランタイムの差異（唯一絶対的な理由）

GPU ノードは **NVIDIA Container Toolkit** を必要とし、compose テンプレート上で
`deploy.resources.reservations.devices` を明示的に付与する必要がある。

```yaml
# templates/compose.yaml.jinja2 (ray-gpu のみ)
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

これは CPU ノードには不要であり、Docker レベルの構造的差異として分離される。

### 1-3. デフォルトイメージの差異

| ノード    | デフォルトイメージ               | 説明                  |
|-----------|----------------------------------|-----------------------|
| `ray-cpu` | `rayproject/ray:latest`          | CPU 汎用              |
| `ray-gpu` | `rayproject/ray:latest-gpu`      | CUDA 対応             |

`RayConfig.model_post_init` でフォールバック設定:

```python
# ws_src/models.py
if self.cpu.image is None:
    self.cpu.image = "rayproject/ray:latest"
if self.gpu.image is None:
    self.gpu.image = "rayproject/ray:latest-gpu"
```

### 1-4. ~~ポートの干渉回避~~ ← 同時起動不可の原則により無効

~~両ノードが同一ホスト上で同時起動できるように、ポートを完全に分離している。~~

同時起動しない前提を採用したため、`head_port`, `dashboard_port`, `client_port` は
CPU と GPU で **同一値を使用できる**。既存の `check_port_conflicts` バリデータも
この制約を見直す候補になる。

### 1-5. 条件付きデプロイ

`config.yaml` の `host.has_gpu: true` + `services.ray.gpu.enabled: true` の両方が
揃ったときのみ `ray-gpu` サービスが生成される。GPU 非搭載ホストでは CPU クラスターのみ稼働。

```jinja2
{% if host.has_gpu and services.ray.gpu.enabled %}
  ray-gpu:
    ...
{% endif %}
```

### 1-6. 小括: 分割の合理性（同時起動不可の原則適用後）

| 理由                         | 判定 | 評価                                                            |
|------------------------------|------|-----------------------------------------------------------------|
| Docker デバイス予約の差異    | ✅ 有効 | GPU のみ `deploy.resources.reservations.devices` が必要。構造的に不可避 |
| イメージの差異               | 🔶 条件付き | CUDA 対応イメージを CPU でも使えば単一化可能 |
| ポート干渉回避               | ❌ 無効 | 同時起動不可の原則により不要 |
| 独立 Head として起動可能     | ❌ 無効 | 採用しない設計方針 |
| 共通フィールドの重複記述     | ⚠️ 課題 | `image`, `build`, `cpus`, `memory` 等が冗長 |
| スキーマが兄弟関係（並列）   | ⚠️ 課題 | "GPU は CPU の拡張" という意味論を表現できていない |

**真に分離が必要な項目は以下の通り（後述 §3 参照）。**

---

## 2. テンプレート以外での分離レイヤー選択肢

「Jinja2 テンプレートに `{% if host.has_gpu %}` を書く」以外に、
どの抽象レイヤーで`cpu` / `gpu` の差異を吸収できるかを整理する。

### 選択肢 A: Docker Compose `profiles`（現行・最小変更）

```yaml
# _build/compose.yaml (生成済み)
  ray-cpu:
    profiles: [ray-cpu]
  ray-gpu:
    profiles: [ray-gpu]
```

- `docker compose --profile ray-cpu up` で排他起動を保証
- テンプレートは現状維持、**config.yaml・モデルに変更不要**
- GPU/CPU の分岐は compose ファイルの 2 サービスとして残る
- **適用コスト: ゼロ（既に導入済み）**

### 選択肢 B: Docker Compose `extends`

```yaml
# base-ray.yaml
services:
  ray-base:
    image: rayproject/ray:latest
    restart: "no"
    volumes: [...]

# compose.yaml
services:
  ray:
    extends:
      file: base-ray.yaml
      service: ray-base
    environment:
      RAY_NUM_GPUS: "0"

  ray-gpu:
    extends:
      file: base-ray.yaml
      service: ray-base
    environment:
      RAY_NUM_GPUS: "1"
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]
```

- `extends` で共通設定を DRY 化できるが、Jinja2 テンプレートから生成する場合は利点が薄い
- Docker Compose v2 では `extends` でネットワーク・ボリュームは継承されない制限あり
- **適用コスト: 中（テンプレート構造変更 + 分割ファイル管理）**

### 選択肢 C: Pydantic モデルレイヤー（継承）

```python
class RayCPUConfig(RayNodeConfig):   # base
    ...

class RayGPUConfig(RayCPUConfig):   # base + gpu 拡張
    num_gpus: int = Field(default=1)
    runtime: str = Field(default="nvidia")
```

- スキーマ上で「GPU は CPU の拡張」という意味論を表現
- `RayConfig.model_post_init` の image/build 伝播ロジックが不要になる
- テンプレートの `RAY_NUM_GPUS: "1"` を `{{ services.ray.gpu.num_gpus }}` に動的化
- **適用コスト: 中（モデル・テンプレート・スキーマ変更）**

### 選択肢 D: エントリポイント（シェルスクリプト）レイヤー

```bash
# ray.sh の先頭に追加
GPU_MODE="${RAY_NUM_GPUS:-0}"
if [ "$GPU_MODE" -gt 0 ]; then
    GPU_ARGS="--num-gpus=$GPU_MODE"
else
    GPU_ARGS=""
fi
ray start --head $GPU_ARGS --port=$RAY_HEAD_PORT ...
```

- 単一コンテナ + 単一イメージで GPU/CPU を環境変数で切り替え
- Docker 側の `deploy.resources.reservations` は **依然として compose で分岐が必要**（GPU デバイスの確保はカーネルレベルの操作のため）
- **適用コスト: 小（スクリプト変更のみ）ただし compose の分岐は残る**

### 選択肢 E: ビルドレイヤー（Dockerfile `--build-arg`）

```dockerfile
ARG GPU_SUPPORT=false
FROM rayproject/ray:latest AS base
FROM base AS cpu
FROM rayproject/ray:latest-gpu AS gpu
FROM ${GPU_SUPPORT:+gpu}${GPU_SUPPORT:-cpu} AS final
```

- イメージのみを統一できるが、デバイス予約は解決しない
- ビルド時引数で image を切り替えるため、config.yaml の `image` フィールドが不要になりうる
- **適用コスト: 高（Dockerfile リファクタ + テスト）**

### レイヤー比較

| 選択肢 | 分離レイヤー | image 統一 | デバイス予約 | 適用コスト |
|--------|------------|-----------|-------------|-----------|
| A: profiles | Docker Compose | ✗ 現状維持 | 分岐必要 | ゼロ |
| B: extends | Docker Compose | △ DRY化 | 分岐必要 | 中 |
| C: Pydantic継承 | モデル | ✗ 現状維持 | 分岐必要 | 中 |
| D: シェルスクリプト | エントリポイント | ✗ 現状維持 | 分岐必要 | 小 |
| E: Dockerfile ARG | ビルド | ○ 統一可 | 分岐必要 | 高 |

> **「デバイス予約の分岐」はどの選択肢でも必要。** これが唯一絶対的な分岐点。

---

## 3. 真に分離が必要な項目

同時起動不可の原則を前提とした場合、設定項目を「分離不可能」「分離が望ましい」「統合可能」に分類する。

### 3-1. 分離が絶対に必要（構造的制約）

| 項目 | 理由 |
|------|------|
| `deploy.resources.reservations.devices` | GPU ランタイムのカーネルレベル予約。CPU に適用不可 |

これのみ。

### 3-2. 分離が望ましい（意味論的差異あり）

| 項目 | 理由 | 統合方法 |
|------|------|---------|
| `image` | GPU イメージは CUDA ツールチェーンを含む | CUDA イメージを CPU でも使えば統一可能（容量増大） |
| `RAY_NUM_GPUS` 環境変数 | `0` / `1` の差 | 単一フィールド `num_gpus: int` に昇格し 0 指定で CPU 相当 |
| `runtime` (Docker GPU runtime) | `nvidia` / なし | `runtime:` フィールドに統合し null で CPU 相当 |

### 3-3. 統合可能（同時起動不可により差異が消失）

| 項目 | 現行の差異 | 統合後 |
|------|-----------|--------|
| `head_port` | cpu:6379, gpu:6380 | 共通値（例: 6379）に統一可能 |
| `dashboard_port` | cpu:8265, gpu:8266 | 共通値（例: 8265）に統一可能 |
| `client_port` | cpu:10001, gpu:10002 | 共通値（例: 10001）に統一可能 |
| `cpus` / `memory` | 独立設定 | `gpu:` が `cpu:` から継承でデフォルト共通化 |
| `build` 設定 | `ray.build` でフォールバック | `cpu.build` に統合し `gpu` が継承 |

**分離が不可能な項目は `deploy.resources.reservations.devices` のみ。**  
`cpu.image` / `gpu.image` は意味論上は異なるが、技術的には統一可能。

---

## 4. ポート公開方針: `:8080` 記法によるダッシュボードの動的割り当て

同時起動不可の原則を前提とした場合、config.yaml の `dashboard_port` は
`"0:<container_port>"` 記法でホスト側ポートをランダム割り当てできる。

```yaml
# config.yaml の dashboard_port 設定
services:
  ray:
    cpu:
      dashboard_port: 8265      # コンテナ内固定、ホスト側は "0:8265" でランダム化可能
    gpu:
      dashboard_port: 8265      # 同時起動しないため cpu と同値に統一可能
```

**ポートごとのランダム化可否:**

| ポート | ランダム化 | 理由 |
|--------|-----------|------|
| `dashboard_port` | ✅ 可 | HTTP のみ、固定参照なし |
| `head_port` | ❌ 不可 | Worker が `--address=<head>:<port>` で固定参照 |
| `client_port` | ❌ 不可 | Ray Client が `ray://<host>:<port>` で固定参照 |

ランダムポートのログ通知や Traefik によるリバースプロキシの詳細は
[traefik-proxy.md](./traefik-proxy.md) を参照。

---

## 5. 現行構造の詳細

### 5-1. Pydantic モデル（現行）

```
RayNodeConfig          ← 抽象基底（全共通フィールド定義）
├── RayCPUConfig       ← CPU 固有デフォルト値のみオーバーライド
└── RayGPUConfig       ← GPU 固有デフォルト値のみオーバーライド

RayConfig              ← 共有設定 (image, build) + cpu + gpu を束ねる
  ├── image: Optional[str]       # cpu/gpu へのフォールバック
  ├── build: Optional[BuildConfig]
  ├── cpu: RayCPUConfig
  └── gpu: RayGPUConfig
```

`RayConfig.model_post_init` で `image` と `build` を cpu/gpu へ伝播させる
ロジックが必要になっており、モデル間の依存関係がコードで補完されている状態。

### 5-2. config.yaml（現行）

```yaml
services:
  ray:
    build:                          # cpu/gpu 共通ビルド設定（フォールバック）
      enabled: false
      dockerfile: ../Dockerfile
      target: ray-runtime
      context: ..

    cpu:                            # CPU ヘッドノード固有設定
      enabled: true
      head_port: 6379
      dashboard_port: 8265
      client_port: 20001

    gpu:                            # GPU ヘッドノード固有設定
      enabled: true
      head_port: 6380
      dashboard_port: 8266
      client_port: 20002
```

---

## 6. 提案: `ray.default` フォールバックモデル

> 詳細な設計・モデルコード・比較表は [ray-default.md](./ray-default.md) を参照。  
> CPU を base とした継承案は [cpu-base-model.md](./cpu-base-model.md) に分離保管している。

### 6-1. 設計概要

cpu と gpu を「同階層の独立ノード」として扱い、共通設定を `ray.default` に集約する。  
起動するノードは `ray.target: "cpu" | "gpu"` で型安全に宣言する。

```
RayNodeSchema        ← ユーザー入力（全フィールド Optional / enabled なし）
├── RayCPUSchema     ← CPU ノード固有の上書き用スキーマ
└── RayGPUSchema     ← GPU ノード固有の上書き用スキーマ（num_gpus、runtime を追加）

RayNodeResolved      ← 共通フィールドを持つ Resolved 基底クラス（enabled なし）
                        target: "cpu" | "gpu"、image、head_port 等を保持
├── RayCpuResolved   ← CPU の確定値（新規フィールドなし）
└── RayGpuResolved   ← GPU の確定値（num_gpus、runtime を追加）

RayConfig
  ├── target: Literal["cpu", "gpu"]   # 起動ノードを宣言
  ├── default: RayDefaultConfig       # 必須フォールバック（プログラムへのべた書きなし）
  ├── cpu: RayCPUSchema
  ├── gpu: RayGPUSchema
  └── resolved: RayNodeResolved       # model_post_init で target に応じて生成
                                       # 実体は RayCpuResolved または RayGpuResolved
```

### 6-2. config.yaml（提案）

```yaml
services:
  ray:
    target: cpu        # 起動するノードタイプ（"cpu" または "gpu"）

    default:           # 共通フォールバック（全フィールド必須）
      image: rayproject/ray:latest
      head_port: 6379
      dashboard_port: 8265
      client_port: 10001
      build:
        enabled: false
        dockerfile: ../Dockerfile
        target: ray-runtime
        context: ..
      cpus: 4
      memory: 8g

    cpu:
      {}   # すべて ray.default から解決

    gpu:
      image: rayproject/ray:latest-gpu
      num_gpus: 1
      runtime: nvidia
      # ポート類 → ray.default から解決
```

### 6-3. 現行 vs 提案 主要変更点

| 観点 | 現行 | 提案 |
|------|------|------|
| 起動制御 | `cpu.enabled` / `gpu.enabled` を個別管理 | `ray.target: "cpu" \| "gpu"` で型保証。`enabled` は Schema・Resolved どちらにも存在しない |
| 共通設定の場所 | `ray.image`, `ray.build`（トップレベル・意味論不明確） | `ray.default.*`（明示的なフォールバック層） |
| プログラムの値のべた書き | `6379` 等をコードにハードコード | `ray.default` 必須化により廃止 |
| テンプレート参照 | `cpu.head_port`（Schema を直参照） | 共通フィールドは `resolved.head_port` 等を直接参照。GPU 固有フィールドのみ `resolved.target` で分岐 |
| `model_post_init` | オブジェクトを in-place 変更 → Schema と Resolved が混在 | `target` に応じて `_resolve_cpu()` または `_resolve_gpu()` を実行し、戻り値（`RayCpuResolved` / `RayGpuResolved`）を `resolved` に直接格納 |

---

## 9. 参照ファイル

| ファイル | 関連箇所 |
|---------|---------|
| [ray-default.md](./ray-default.md) | `ray.default` フォールバック設計の詳細・モデルコード・比較表 |
| [cpu-base-model.md](./cpu-base-model.md) | CPU を base にした継承案（意思決定のために保管） |
| [traefik-proxy.md](./traefik-proxy.md) | ランダムポート詳細 / Traefik 構成 / 同時起動不可の整合性チェック |
| [ws_src/models.py](../ws_src/models.py) | `RayNodeConfig`, `RayCPUConfig`, `RayGPUConfig`, `RayConfig`, `model_post_init` |
| [config.yaml](../config.yaml) | `services.ray.cpu`, `services.ray.gpu`, `services.ray.build` |
| [config.example.yaml](../config.example.yaml) | 同上 |
| [templates/compose.yaml.jinja2](../templates/compose.yaml.jinja2) | `ray-cpu`, `ray-gpu` サービス定義, `RAY_NUM_GPUS`, `driver: nvidia` |
| [entrypoints/ray.sh](../entrypoints/ray.sh) | Head/Worker 自動判定ロジック |
| [docs/architecture.md](../docs/architecture.md) | Ray クラスター起動フロー, Head/Worker 判定ロジック |
| [docs/ray-startup-options.md](../docs/ray-startup-options.md) | `ray start` オプション詳細 |
| [docs/config-reference.md](../docs/config-reference.md) | `services.ray.cpu` / `gpu` フィールド仕様 |
