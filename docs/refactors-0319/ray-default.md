# `ray.default` フォールバック設計の考察

> **このドキュメントの位置づけ**  
> [README.md](./README.md) §6 の「Pydantic 継承モデル（cpu を base とする案）」に対する
> 代替案として、`ray.default` セクションを設けるフォールバック設計を分析する。

---

## 1. 動機

`cpu` を base にして `gpu` が継承する案（§6）には次の問題がある:

- `RayGPUConfig` が `RayCPUConfig` を継承すると、**GPU が CPU の派生物**という意味論になる
  → CPU と GPU は「役割が違う同階層のノード」であり、継承よりコンポジションが自然
- cpu 固有のデフォルト（例: `head_port=6379`）を gpu が継承し、
  gpu でオーバーライドしない場合に cpu と同じ値になる（意図 vs 偶然が不明確）

`ray.default` を明示的なフォールバック層として設けることで:

- cpu/gpu は **独立した設定** として存在し続ける
- 共通値は `ray.default` に一元化し、両者が参照する
- 「書かなければ default の値を使う」という意図をスキーマで直接表現できる

---

## 2. フォールバック解決の優先順位

```
ray.cpu.<field>  (明示指定) ─→ 最優先
ray.default.<field>          ─→ フォールバック（必須・プログラムへのべた書きなし）
```

> **原則**: ポート番号・image など設定値をコードにハードコードしない。
> `ray.default` の必須フィールドが未記載の場合は Pydantic がバリデーションエラーを出す。

```yaml
# config.yaml 例
services:
  ray:
    target: cpu          # 起動するノードタイプ（"cpu" または "gpu"）

    default:             # 共通フォールバック（全フィールド必須）
      image: rayproject/ray:latest
      head_port: 6379
      dashboard_port: 8265
      client_port: 10001
      cpus: 4
      memory: 8g
      build:
        enabled: false
        dockerfile: ../Dockerfile
        target: ray-runtime
        context: ..

    cpu:
      {}   # 全フィールドを ray.default から解決（上書きしたい場合のみ記述）

    gpu:
      image: rayproject/ray:latest-gpu   # GPU 向けイメージを上書き
      num_gpus: 1
      runtime: nvidia
      # ポート類は ray.default から解決
```

---

### 2-1. cpu と gpu の起動優先度（現状）

`ray.sh` は **`HEAD_WHITELIST`** 環境変数（compose テンプレートで
`nodes.head_whitelist` から生成）の順序でスキャンを行い Head を選出する。

| シナリオ | Head になるノード | 根拠 |
|----------|-----------------|------|
| `--profile ray-cpu` のみ起動 | ray-cpu が自動的に Head | ホワイトリスト内に他ノードが存在しないため即 Head |
| `--profile ray-gpu` のみ起動 | ray-gpu が自動的に Head | 同上 |
| cluster-test（両方同時起動） | **ray-cpu が優先** | ホワイトリスト順が `[ray-cpu, ray-gpu]` であり、ray-cpu が先に TCP スキャンして既存 Head を見つけられず自分が Head に。ray-gpu はその後 ray-cpu を発見して Worker に |

**起動優先度を変更したい場合** は `config.yaml` の
`nodes.head_whitelist: [ray-gpu, ray-cpu]` の順序を入れ替えるだけでよい。
`ray.default` のフォールバック設計はこの優先度とは直交した概念であり、
どちらのノードが Head になっても適用されるデフォルト値として機能する。

---

## 3. `ray.default` 化できる項目の洗い出し

### 3-1. 全フィールドの分類

`RayNodeConfig`（基底クラス）の全フィールドを 4 区分に分類する。

| フィールド | 型 | `ray.default` 化 | 分類 | 理由 |
|-----------|-----|:---:|------|------|
| `target` | `Literal["cpu","gpu"]` | — | `RayConfig` 固有 | ノードではなく `RayConfig` 上のフィールド。どちらを起動するかを宣言する |
| `enabled` | `bool` | — | Resolved 計算フィールド | Schema には存在しない。`target == node_type` で Resolved 時に計算される |
| `image` | `Optional[str]` | ✅ 可 | 共通設定 | 現行 `ray.image` と同等。custom runtime など同一イメージを使う場合 |
| `build` | `Optional[BuildConfig]` | ✅ 可 | 共通設定 | 現行 `ray.build` と同等。Dockerfile は共通のため |
| `cpus` | `Optional[float]` | ✅ 可 | リソース | 同一ホストでの CPU 割り当てが CPU/GPU ノードで同じになることが多い |
| `memory` | `Optional[str]` | ✅ 可 | リソース | 同上 |
| `head_port` | `int` | ✅ 可 | ポート系 | 同時起動不可の原則により単一値で十分 |
| `dashboard_port` | `int` | ✅ 可 | ポート系 | 同上 |
| `client_port` | `int` | ✅ 可 | ポート系 | 同上 |
| `node_ip_address` | `Optional[str]` | ✅ 可 | ネットワーク | 同一ホスト上の CPU/GPU は通常同じ IP |
| `node_manager_port` | `Optional[int]` | ✅ 可 | ポート系 | 同時起動不可なら共通化可能 |
| `object_manager_port` | `Optional[int]` | ✅ 可 | ポート系 | 同上 |
| `min_worker_port` | `Optional[int]` | ✅ 可 | ポート系 | 同上 |
| `max_worker_port` | `Optional[int]` | ✅ 可 | ポート系 | 同上 |
| `address` | `Optional[str]` | ❌ 不可 | ノード固有 | 後述 §3-3 参照 |

**GPU 固有フィールド**（§6 の提案で追加される項目）:

| フィールド | `ray.default` 化 | 理由 |
|-----------|:---:|------|
| `num_gpus` | ❌ 不可 | CPU ノードに GPU 数を設定するのは無意味 |
| `runtime` | ❌ 不可 | `nvidia` / `amd` は GPU 専用 |

### 3-2. `ray.default` 化する意義が大きい項目

優先度付き:

| 優先度 | フィールド | 根拠 |
|--------|-----------|------|
| ⭐⭐⭐ | `head_port`, `dashboard_port`, `client_port` | 同時起動不可の原則で単一値化でき、重複が完全に解消 |
| ⭐⭐⭐ | `build` | 現行 `ray.build` の責務を `ray.default.build` に整理（名前空間の明確化） |
| ⭐⭐ | `cpus`, `memory` | 実際の運用で cpu/gpu が同じリソース制限を持つことが多い |
| ⭐⭐ | `image` | 現行 `ray.image` と同等（`ray.default.image` に明示的に移動） |
| ⭐ | `node_ip_address`, `node_manager_port`, `object_manager_port` | NAT 環境や固定ポート環境での設定簡略化 |

**`enabled` と `target` の設計:**  
`enabled` はスキーマには存在せず、`RayNodeResolved` 上の計算フィールドとして `target == node_type` から導出される。  
「どちらを起動するか」の宣言は `ray.target: "cpu" | "gpu"` で一元管理し、  
cpu/gpu どちらが有効かを型システムが保証する（`Literal` 型によりタイポも防止）。

### 3-3. `address` が `ray.default` 化できない理由

`address` は `ray start --address=<HEAD>:<PORT>` に渡す **Worker モードの接続先** であり、
非ホワイトリストノードが Head へ接続するときのみ参照される（`ray.sh` L71–L82）。

**具体的な問題シナリオ:**

```
[ホストA]  ray-cpu   → HEAD として起動（address は無視される）
[ホストB]  ray-gpu   → WORKER として起動（address = ray-cpu:6379 を使う）
[ホストC]  ray-extra → WORKER として起動（address = ray-cpu:6379 を使う）
```

ここで `ray.default.address = "ray-cpu:6379"` を設定したとする。

- `ray-cpu`: ホワイトリスト内 + HEAD 判定 → `address` は参照されない（無害だが意図が混濁）
- `ray-gpu`: ホワイトリスト内 + WORKER 判定
  → `ray.sh` は既存 HEAD の TCP スキャン結果 (`RAY_ADDRESS`) を使って接続するため、
    `address` フィールドは **`HEAD_ADDRESS_CFG` 経由** でのみ参照される
    （`HEAD_ADDRESS_CFG` は `nodes.head_address` から来る。`RayNodeConfig.address` とは別経路）

**`RayNodeConfig.address` と `nodes.head_address` の違い:**

| フィールド | 参照箇所 | 用途 |
|-----------|---------|------|
| `nodes.head_address` | `ray.sh` の `HEAD_ADDRESS_CFG` | 非ホワイトリストノードの接続先（既存の設計） |
| `RayNodeConfig.address` | 現状テンプレートで未使用（`future/reserved`） | 将来のテスト互換用として予約 |

`RayNodeConfig.address` はまだ実装に接続されていない将来予約フィールドのため、
`ray.default` 化すると「共通のデフォルト接続先」という誤った意味論になる危険がある。
`nodes.head_address`（全ノード共通の Head 接続先）とも混同しやすい。

---

## 4. Pydantic モデル設計（Schema / Resolved 分離）

### 4-1. 設計方針

| 原則 | 説明 |
|------|------|
| プログラムへの値のべた書き禁止 | ポート・image 等のデフォルト値をコードに記述しない。`ray.default` が必ず埋める |
| `ray.default` は必須フィールド | `ray.default.head_port` 等は `Optional` ではなく必須。未記載なら Pydantic がエラー |
| Schema / Resolved 分離 | `RayNodeSchema`（ユーザー入力値）と `RayNodeResolved`（フォールバック解決済み値）を型で分離 |
| `enabled` を持たない | Ray サービス起動失敗はスタック全体の起動失敗となるため `enabled=false` に意味がない。`enabled` フィールドは Schema にも Resolved にも存在しない |
| `target` で起動ノードを宣言 | `ray.target: "cpu" \| "gpu"` で起動するノードを宣言。`RayNodeResolved.target` として解決後も保持される |
| `RayNodeResolved` は基底クラス | `RayNodeResolved` は共通フィールドを持つ基底クラス。`RayCpuResolved`（新規フィールドなし）と `RayGpuResolved`（`num_gpus`/`runtime` 追加）が継承する。共通フィールドはテンプレートから `resolved.head_port` 等で直接参照でき、GPU 固有フィールドのみ `resolved.target` で分岐する |

### 4-2. `RayDefaultConfig`: 必須フォールバックモデル

全フィールドを **必須**（Optional なし）とし、プログラムがデフォルト値を持たないことを型レベルで保証する。  
環境依存で省略可能な項目（`node_ip_address` 等）のみ `Optional` を許容する。

```python
class RayDefaultConfig(BaseModel):
    """
    Shared fallback values for ray.cpu and ray.gpu.
    All applicable fields are REQUIRED — no hardcoded fallback values in the program.
    """
    image: str = Field(description="Base Docker image (e.g. 'rayproject/ray:latest')")
    build: RayBuildConfig = Field(description="Build config")
    cpus: float = Field(gt=0, description="CPU limit")
    memory: str = Field(description="Memory limit (e.g. '8g')")
    head_port: int = Field(ge=1024, le=65535)
    dashboard_port: int = Field(ge=1024, le=65535)
    client_port: int = Field(ge=1024, le=65535)
    # 環境依存: 省略可能
    node_ip_address: Optional[str] = Field(default=None)
    node_manager_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    object_manager_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    min_worker_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    max_worker_port: Optional[int] = Field(default=None, ge=1024, le=65535)
```

### 4-3. Schema 層: ユーザー入力をそのまま表現

`enabled` はスキーマに持たず、`RayConfig.target` で起動ノードを一意に決定する。  
`None` は「未指定 → `ray.default` から解決」を意味する。

```python
class RayNodeSchema(BaseModel):
    """
    ユーザーが config.yaml に書いた値をそのまま保持する。
    None は「未指定 → ray.default から解決」を表す。
    enabled は含まない（ray.target で制御）。
    """
    image: Optional[str] = None
    build: Optional[RayBuildConfig] = None
    cpus: Optional[float] = None
    memory: Optional[str] = None
    head_port: Optional[int] = None
    dashboard_port: Optional[int] = None
    client_port: Optional[int] = None
    node_ip_address: Optional[str] = None
    node_manager_port: Optional[int] = None
    object_manager_port: Optional[int] = None
    min_worker_port: Optional[int] = None
    max_worker_port: Optional[int] = None


class RayCPUSchema(RayNodeSchema):
    """CPU ノード固有の設定（上書きしたいフィールドのみ記述）"""


class RayGPUSchema(RayNodeSchema):
    """GPU ノード固有の設定"""
    num_gpus: int = Field(default=1, ge=0)
    runtime: str = Field(default="nvidia")
```

### 4-4. Resolved 層: フォールバック解決済み確定値コンテナ

Ray サービスの起動失敗はスタック全体の起動失敗を意味するため `enabled=false` は無意味。  
`enabled` は Schema にも Resolved にも存在せず、起動制御は `target` のみで行う。

`RayNodeResolved` は cpu/gpu **両方**のフォールバック解決済み値を保持するコンテナとし、  
`target` フィールドでどちらが起動するかを表す。テンプレートは `resolved.target` で分岐する。

```python
class RayNodeResolved(BaseModel):
    """
    CPU/GPU 共通フィールドを持つフォールバック解決済み確定値の基底クラス。
    enabled は存在しない（起動失敗 = スタック全体の失敗のため false が無意味）。
    RayCpuResolved と RayGpuResolved がこのクラスを継承する。
    """
    target: Literal["cpu", "gpu"]
    image: str
    build: RayBuildConfig
    cpus: float
    memory: str
    head_port: int
    dashboard_port: int
    client_port: int
    node_ip_address: Optional[str]
    node_manager_port: Optional[int]
    object_manager_port: Optional[int]
    min_worker_port: Optional[int]
    max_worker_port: Optional[int]


class RayCpuResolved(RayNodeResolved):
    """CPU ノードの確定値（RayNodeResolved から新規フィールドなし）"""
    pass


class RayGpuResolved(RayNodeResolved):
    """GPU ノードの確定値（RayNodeResolved を継承し GPU 固有フィールドを追加）"""
    num_gpus: int
    runtime: str
```

### 4-5. `RayConfig`: target + Schema → `RayNodeResolved`

```python
class RayConfig(BaseModel):
    target: Literal["cpu", "gpu"] = Field(
        description="起動するノードタイプ。cpu または gpu のいずれかを指定する。"
    )
    default: RayDefaultConfig          # 必須（プログラムに落としこみ値なし）
    cpu: RayCPUSchema = Field(default_factory=RayCPUSchema)
    gpu: RayGPUSchema = Field(default_factory=RayGPUSchema)

    # Resolved は model_post_init で生成（ユーザーが直接指定しない）
    resolved: Optional[RayNodeResolved] = Field(default=None, exclude=True)

    def model_post_init(self, __context: object) -> None:
        if self.target == "cpu":
            self.resolved = self._resolve_cpu()
        else:
            self.resolved = self._resolve_gpu()

    def _resolve_cpu(self) -> RayCpuResolved:
        d, s = self.default, self.cpu

        def pick(node_val, default_val):
            return node_val if node_val is not None else default_val

        return RayCpuResolved(
            target="cpu",
            image=pick(s.image, d.image),
            build=pick(s.build, d.build),
            cpus=pick(s.cpus, d.cpus),
            memory=pick(s.memory, d.memory),
            head_port=pick(s.head_port, d.head_port),
            dashboard_port=pick(s.dashboard_port, d.dashboard_port),
            client_port=pick(s.client_port, d.client_port),
            node_ip_address=s.node_ip_address or d.node_ip_address,
            node_manager_port=s.node_manager_port or d.node_manager_port,
            object_manager_port=s.object_manager_port or d.object_manager_port,
            min_worker_port=s.min_worker_port or d.min_worker_port,
            max_worker_port=s.max_worker_port or d.max_worker_port,
        )

    def _resolve_gpu(self) -> RayGpuResolved:
        d, s = self.default, self.gpu

        def pick(node_val, default_val):
            return node_val if node_val is not None else default_val

        return RayGpuResolved(
            target="gpu",
            image=pick(s.image, d.image),
            build=pick(s.build, d.build),
            cpus=pick(s.cpus, d.cpus),
            memory=pick(s.memory, d.memory),
            head_port=pick(s.head_port, d.head_port),
            dashboard_port=pick(s.dashboard_port, d.dashboard_port),
            client_port=pick(s.client_port, d.client_port),
            node_ip_address=s.node_ip_address or d.node_ip_address,
            node_manager_port=s.node_manager_port or d.node_manager_port,
            object_manager_port=s.object_manager_port or d.object_manager_port,
            min_worker_port=s.min_worker_port or d.min_worker_port,
            max_worker_port=s.max_worker_port or d.max_worker_port,
            num_gpus=s.num_gpus,
            runtime=s.runtime,
        )
```

### 4-6. テンプレートへの影響

```jinja2
{# 変更前: enabled フラグで分岐 #}
{% if services.ray.cpu.enabled %}
- "RAY_HEAD_PORT={{ services.ray.cpu.head_port }}"
{% endif %}

{# 変更後: resolved は RayCpuResolved または RayGpuResolved（いずれも RayNodeResolved を継承） #}
{# 共通フィールドは resolved.* で直接参照。GPU 固有フィールドのみ target で分岐 #}
{% set r = services.ray.resolved %}
- "RAY_HEAD_PORT={{ r.head_port }}"
- "RAY_DASHBOARD_PORT={{ r.dashboard_port }}"
{% if r.target == "gpu" %}
- "RAY_NUM_GPUS={{ r.num_gpus }}"
{% endif %}
```

---

## 5. config.yaml の記述変化

### 5-1. 現行（3 箇所に分散）

```yaml
services:
  ray:
    build:              # トップレベルフォールバック（意味論が不明確）
      enabled: false
      ...
    image: null         # トップレベルフォールバック
    cpu:
      head_port: 6379
      dashboard_port: 8265
      client_port: 20001
    gpu:
      head_port: 6380
      dashboard_port: 8266
      client_port: 20002
```

### 5-2. 提案（`ray.default` に集約 / 必須化 / target 導入）

```yaml
services:
  ray:
    target: cpu            # 起動するノードタイプ（"cpu" または "gpu"）

    default:               # 共通フォールバック（全フィールド必須 / プログラムにデフォルト値なし）
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
      {}   # 全フィールドを ray.default から解決
           # 上書きしたい場合のみキーを記述

    gpu:
      image: rayproject/ray:latest-gpu
      num_gpus: 1
      runtime: nvidia
      # ポート類 → ray.default から解決
```

---

## 6. `ray.default` 案 vs `gpu が cpu を継承` 案の比較

| 観点 | 継承案 | `ray.default` 案（本ドキュメント） |
|------|------------|----------------------------------|
| 意味論 | GPU は CPU の派生型 | CPU と GPU は独立した同階層のノード |
| 共通設定の明示性 | 暗黙的（継承で解決） | 明示的（`ray.default` に記述） |
| ポート重複の解消 | GPU がデフォルト値をオーバーライドしなければ自動共通化 | `ray.default` に一元記述 |
| `ray.build` の扱い | `ray.cpu.build` に移動し GPU が継承 | `ray.default.build` に移動 |
| 追加フィールド（`num_gpus` 等） | `RayGPUConfig` に追加 | 同左（変わらず `RayGPUSchema` のみ） |
| モデルの複雑さ | 継承チェーン（`RayGPUConfig → RayCPUConfig → RayNodeConfig`） | Schema（全クラスが `RayNodeSchema` 継承） + Resolved の 2層 |
| `enabled` の扱い | `bool` を cpu/gpu 各ノードに直接定義 | 存在しない（起動失敗 = スタック全体の失敗のため `false` が無意味） |
| 起動ノードの宣言 | `cpu.enabled: true` / `gpu.enabled: true` を手動管理 | `ray.target: "cpu"` または `"gpu"` で型保証。`resolved.target` として解決後も保持 |
| Resolved の構造 | `cpu_resolved`, `gpu_resolved` を `RayConfig` 直下に別々に保持 | `RayNodeResolved` を基底とした継承構造。`resolved` は `RayNodeResolved` 型（実体は `RayCpuResolved` または `RayGpuResolved`） |
| テンプレートの参照先 | Schema を直接参照（解決済か不明） | 共通フィールドは `resolved.head_port` 等を直接参照。GPU 固有フィールドのみ `resolved.target` で分岐 |
| 後方互換性 | `ray.build` → `ray.cpu.build` の破壊的変更あり | `ray.build`/`ray.image` → `ray.default.*` の破壊的変更あり |
| JSON Schema の見通し | `gpu` が `cpu` のスーパーセット | `cpu`, `gpu`, `default`, `target` が並列 |

---

## 7. 実装上の注意点

### 7-1. Schema 層の `Optional` と Resolved 層の型保証

`RayNodeSchema` のポート系フィールドは `Optional[int]`（`None`＝未指定）であるが、
`RayCpuResolved` / `RayGpuResolved` では `int`（`None` なし）に宣言される。

`ray.default` 必須化により `_resolve_cpu()` / `_resolve_gpu()` 内部で `None` が残ることはなく、
各 Resolved クラスのコンストラクタで Pydantic が型検証する。
テンプレートは `resolved.head_port` 等（共通フィールド）を直接参照し、GPU 固有フィールドのみ `resolved.target` で分岐して参照するため、`None` が展開されるリスクは除去される。

### 7-2. `check_port_conflicts` バリデータへの影響

現行: CPU と GPU のポートが異なることを前提にポート衝突をチェックしている。  
`ray.default` 化後: CPU/GPU が同じポートを使うことが通常になるため、
**CPU と GPU 間のポート比較ロジックを除外**する必要がある。

```python
# 現行の check_port_conflicts: cpu と gpu が同じポートを持つと衝突と判定してしまう
# → 同時起動不可の原則を反映して、cpu-gpu 間のポート比較を除外する
```

---

## 10. 推奨方針

同時起動不可の原則を前提に、**`ray.default` + Schema/Resolved 分離案を採用する**ことを推奨する。理由:

1. CPU/GPU を「同階層の独立ノード」として扱うことがモデルの意味論に合致
2. 共通設定が `ray.default` に明示的に書かれることで設定の意図が明確
3. 現行の `ray.image` / `ray.build` トップレベルフォールバックを廃止し、
   `ray.default` に置き換えることで名前空間が整理される
4. Schema/Resolved 分離により「ユーザーが書いた値」と「実際に使われる値」が明確になる
5. `ray.target: "cpu" | "gpu"` で起動ノードを型保証して宣言。`enabled` は Schema・Resolved どちらにも存在せず `RayNodeResolved.target` で一元管理
6. `ray.default` 必須化によりプログラムへの値のべた書きが廃止され、設定ファイル側にデフォルト値の管理が一元化される

---

## 参照

| ファイル | 関連箇所 |
|---------|--------|
| [README.md §5](./README.md) | 現行構造の詳細 |
| [README.md §6](./README.md) | `ray.default` モデルの簡略版（cpu-base 継承案は [cpu-base-model.md](./cpu-base-model.md) へ） |
| [README.md §3](./README.md) | 分離・統合可能項目の分類 |
| [cpu-base-model.md](./cpu-base-model.md) | CPU を base にした継承案（意思決定のために保管） |
| [ws_src/models.py](../ws_src/models.py) | `RayNodeConfig`, `RayConfig`, `model_post_init` |
| [config.yaml](../config.yaml) | `services.ray.cpu/gpu/build/image` 現行構造 |
