# 代替案: `cpu: (base)`, `gpu: (base) + GPU固有設定`

> **このドキュメントの位置づけ**  
> [README.md](./README.md) から分離した、CPU を base とした継承案の詳細記述。  
> `ray.default` フォールバック案（[ray-default.md](./ray-default.md)）との比較・意思決定のために保管する。  
> 採用を決定した場合は [ray-default.md §6](./ray-default.md#6-raydefault-案-vs-gpu-が-cpu-を継承-案の比較) も参照すること。

---

## 1. 設計意図

> **GPU ノードは「CPU ノードの設定をすべて引き継ぎ、GPU 固有設定を追加した」もの**

という意味論を、スキーマと設定ファイルの構造そのもので表現する。

---

## 2. Pydantic モデル（提案）

```
RayBaseConfig          ← 実運用で使う共通フィールド（旧 RayNodeConfig 相当）
RayCPUConfig           ← RayBaseConfig のエイリアス（= base そのもの）
RayGPUConfig           ← RayCPUConfig を継承 + GPU 固有フィールド追加

RayConfig              ← cpu: RayCPUConfig を "base" として保持
  ├── cpu: RayCPUConfig   # base 設定（="cpu"）
  └── gpu: RayGPUConfig   # base + gpu オーバーライド
```

**変更点の要点:**

| 項目 | 現行 | 提案 |
|------|------|------|
| `RayCPUConfig` の基底 | `RayNodeConfig` | `RayNodeConfig`（同じ） |
| `RayGPUConfig` の基底 | `RayNodeConfig` | `RayCPUConfig` |
| GPU 固有フィールド | テンプレートにハードコード (`RAY_NUM_GPUS: "1"`) | `RayGPUConfig.num_gpus: int = 1` としてスキーマに昇格 |
| `RayConfig.image` / `.build` | `model_post_init` で cpu/gpu へ伝播 | `cpu:` のフィールドをそのまま gpu が継承するため不要に |

**提案コード概略:**

```python
class RayCPUConfig(RayNodeConfig):
    """Ray CPU service configuration (= base)"""
    image: Optional[str] = Field(default=None)
    dashboard_port: int = Field(default=8265, ...)
    client_port: int = Field(default=10001, ...)
    head_port: int = Field(default=6379, ...)


class RayGPUConfig(RayCPUConfig):
    """Ray GPU service configuration (= base + GPU)"""
    # GPU 固有デフォルトでオーバーライド
    image: Optional[str] = Field(default=None)   # → latest-gpu へのフォールバック
    dashboard_port: int = Field(default=8266, ...)
    client_port: int = Field(default=10002, ...)
    head_port: int = Field(default=6380, ...)
    # GPU 固有フィールド（新規追加）
    num_gpus: int = Field(default=1, ge=0, description="GPU count for Ray")
    runtime: str = Field(default="nvidia", description="Docker GPU runtime")


class RayConfig(BaseModel):
    """Ray service configuration"""
    cpu: RayCPUConfig = Field(default_factory=RayCPUConfig)
    gpu: RayGPUConfig = Field(default_factory=RayGPUConfig)
    # image / build は cpu に一本化（gpu は cpu から継承）
```

---

## 3. config.yaml（提案）

```yaml
services:
  ray:
    # --- base (= cpu) ---
    cpu:
      enabled: true
      image: null               # null → rayproject/ray:latest (デフォルト)
      build:
        enabled: false
        dockerfile: ../Dockerfile
        target: ray-runtime
        context: ..
      head_port: 6379
      dashboard_port: 8265
      client_port: 20001
      # cpus: 4
      # memory: 8g

    # --- base + GPU 固有 ---
    gpu:
      enabled: true
      # image / build は cpu から継承 → 上書きしたい場合のみ記述
      # image: null             # null → rayproject/ray:latest-gpu (デフォルト)
      head_port: 6380           # cpu と異なるポートのみ上書き
      dashboard_port: 8266
      client_port: 20002
      num_gpus: 1               # GPU 固有（新規）
      runtime: nvidia           # GPU 固有（新規）
      # cpus: 4
      # memory: 16g
```

---

## 4. 現行 vs 提案 比較表

### 4-1. config.yaml の記述量

| セクション | 現行 | 提案 | 差分 |
|-----------|------|------|------|
| `ray.build` | トップレベルに独立 | `ray.cpu.build` 配下に移動 | 意味論的に cpu の設定として明確化 |
| `ray.gpu.image` | 未記載（`model_post_init` で補完） | 未記載（継承で補完） | 同等 |
| `ray.gpu.build` | 未記載（`model_post_init` で補完） | 未記載（継承で補完） | 同等 |
| GPU 個数 | テンプレートに `RAY_NUM_GPUS: "1"` ハードコード | `gpu.num_gpus: 1` として設定可能 | 設定の柔軟性が向上 |
| GPU ランタイム | テンプレートに `driver: nvidia` ハードコード | `gpu.runtime: nvidia` として設定可能 | AMD GPU など将来対応が容易に |

### 4-2. Pydantic モデルの変更

| クラス | 現行 | 提案 |
|--------|------|------|
| `RayNodeConfig` | 抽象基底（直接利用しない） | 据え置き（変更なし） |
| `RayCPUConfig` | `RayNodeConfig` を継承 | 同左（変更なし） |
| `RayGPUConfig` | `RayNodeConfig` を継承 | `RayCPUConfig` を継承に変更 |
| `RayConfig` | `image`, `build` フィールドを持ち `model_post_init` で伝播 | `image`, `build` を削除（継承で解決） |
| `model_post_init` | image/build の伝播ロジックが必要 | 大幅に簡略化または削除可能 |

### 4-3. テンプレート（Jinja2）の変更

| 箇所 | 現行 | 提案 |
|------|------|------|
| `RAY_NUM_GPUS` 環境変数 | `"1"` ハードコード | `{{ services.ray.gpu.num_gpus }}` に変更 |
| `driver: nvidia` | ハードコード | `{{ services.ray.gpu.runtime }}` に変更 |
| CPU/GPU の image/build フォールバック | `model_post_init` で処理済みの値を参照 | スキーマのデフォルト値を参照（同等） |

### 4-4. メリット / デメリット

| 観点 | 現行 | 本案 |
|------|------|------|
| 意味論的明快さ | GPU が CPU の「拡張」であることがコードから読み取りにくい | クラス継承が意味論を直接表現 |
| 設定の冗長性 | `ray.build` がトップレベルに浮いており gpu への伝播が暗黙的 | `cpu.build` に統合され gpu が自動継承 |
| GPU 個数の設定 | テンプレートの魔法数字 `"1"` を変更不可 | `config.yaml` から直接制御可能 |
| GPU ランタイム | `nvidia` 固定（AMD 不対応） | `runtime: amd` 等への切り替えが可能 |
| 後方互換性 | — | `ray.build` → `ray.cpu.build` への移動は破壊的変更 |
| 実装コスト | — | `RayGPUConfig` の基底変更 + フィールド追加 + テンプレート修正 |
| `enabled` の管理 | cpu/gpu それぞれで `enabled: bool` を個別管理 | 継承のため同様に個別管理が必要 |
| プログラムへの値のべた書き | `6379` 等がコードに残る | 継承デフォルト値としてコードに残る（`ray.default` 案より多い） |

---

## 5. 移行ガイドライン

### 5-1. 破壊的変更の範囲

- `config.yaml` の `services.ray.build` キーが廃止 → `services.ray.cpu.build` に移動
- 既存の `config.yaml` を使用しているユーザーは移行が必要

### 5-2. 移行手順

1. `ws_src/models.py` の `RayGPUConfig` の基底を `RayNodeConfig` → `RayCPUConfig` に変更
2. `RayGPUConfig` に `num_gpus: int = 1` と `runtime: str = "nvidia"` を追加
3. `RayConfig` から `image`, `build` フィールドと `model_post_init` の伝播ロジックを削除
4. `templates/compose.yaml.jinja2` の `RAY_NUM_GPUS: "1"` を `{{ services.ray.gpu.num_gpus }}` へ置換
5. `templates/compose.yaml.jinja2` の `driver: nvidia` を `{{ services.ray.gpu.runtime }}` へ置換
6. `config.yaml` / `config.example.yaml` の `services.ray.build` を `services.ray.cpu.build` に移動
7. JSON Schema を再生成: `uv run ws schema generate`

### 5-3. 優先度評価

| 変更 | 影響範囲 | 優先度 |
|------|----------|--------|
| `RayGPUConfig` の継承元変更 | モデル・バリデーションのみ | 中（ロジック整理） |
| `num_gpus` / `runtime` のスキーマ昇格 | テンプレート + 設定ファイル | 高（柔軟性向上） |
| `ray.build` → `ray.cpu.build` 移動 | 設定ファイルの後方互換 | 低（破壊的変更のため慎重に） |

---

## 参照

| ファイル | 関連箇所 |
|---------|---------|
| [ray-default.md](./ray-default.md) | `ray.default` フォールバック設計（推奨案）との比較 |
| [README.md §5](./README.md) | 現行構造の詳細 |
| [ws_src/models.py](../ws_src/models.py) | `RayNodeConfig`, `RayCPUConfig`, `RayGPUConfig`, `RayConfig` |
| [config.yaml](../config.yaml) | `services.ray.cpu`, `services.ray.gpu`, `services.ray.build` |
