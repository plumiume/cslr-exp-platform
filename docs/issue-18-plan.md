# Issue #18 対応計画: Dockerfile builder/devel/runtime 再編

> 一時ドキュメント。実装完了後は削除または CHANGELOG に統合する。

## 背景・目的

現状の `simple-devel` が builder 的責務（pip install torch 等）と devel 環境の両方を兼ねており、
BuildKit キャッシュの効きが悪い。キャッシュ戦略と最終イメージへの責務が混在している。

目的:
1. `*-builder` ステージを明示してキャッシュ効率を上げる
2. `*-devel` / `*-runtime` を対応する `*-builder` から派生させる
3. `*-devel` / `*-runtime` がキャッシュをクリーンアップした最終成果物を提供する

---

## 新しいステージツリー

```
simple-builder          (--mount=type=cache 使用、ビルド高速化専用。クリーンアップしない)
├── simple-devel        (FROM simple-builder + conda clean/pip cache 削除)
└── simple-runtime      (runtime-base + COPY --from=simple-builder + 後処理クリーンアップ)

ray-builder  (FROM simple-builder)
├── ray-devel           (FROM ray-builder + クリーンアップ)
└── ray-runtime         (runtime-base + COPY --from=ray-builder + クリーンアップ)

marimo-builder  (FROM ray-builder)
├── marimo-devel        (FROM marimo-builder + クリーンアップ)
└── marimo-runtime      (runtime-base + COPY --from=marimo-builder + クリーンアップ)
```

### キャッシュ責務の分担

| ステージ | `--mount=type=cache` | クリーンアップ | 用途 |
|---|---|---|---|
| `*-builder` | ✅ 使う | ❌ しない | ビルドキャッシュ層（中間） |
| `*-devel` | ➖ 不要 | ✅ する | 開発用最終イメージ |
| `*-runtime` | ➖ 不要 | ✅ する | 本番用最終イメージ |

---

## タスク一覧・実装方針

### TODO-1: Dockerfile — builder ステージ追加・責務移管

**作業内容:**

1. `simple-builder` を新規追加
   - ベース: `nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04`
   - 移管する処理: APT(build-essential/cmake/ninja/ccache 等)・Miniforge・conda env 作成・PyTorch・PyG
   - `--mount=type=cache` はそのまま維持（dev ビルドでのキャッシュ有効化）

2. `simple-devel` を builder 由来に変更
   - `FROM simple-builder AS simple-devel`
   - devel 固有の追加（例: デバッグツール, editable install 等）があれば追記
   - builder で完結している場合はほぼ空（エイリアス相当）

3. `simple-runtime` の COPY 元を `simple-builder` に変更
   - `COPY --from=simple-builder /opt/conda/envs/py /opt/conda/envs/py`

4. `ray-builder` を追加（`FROM simple-builder AS ray-builder`）
   - 移管: Bazelisk・Ray インストール・Ray extras
   - `ray-devel` は `FROM ray-builder`、`ray-runtime` は `COPY --from=ray-builder`

5. `marimo-builder` を追加（`FROM ray-builder AS marimo-builder`）
   - 移管: marimo インストール
   - `marimo-devel` は `FROM marimo-builder`、`marimo-runtime` は `COPY --from=marimo-builder`

**注意:**
- 既存のターゲット名 `simple-runtime` / `ray-runtime` / `marimo-runtime` は変更しない（AC 準拠）
- `runtime-base` は変更なし

---

### TODO-2: Dockerfile — devel/runtime でのキャッシュクリーンアップ

**方針:** `*-builder` はビルド効率を最大化する中間ステージとして使い捨て。
最終イメージとなる `*-devel` / `*-runtime` でキャッシュ・不要ファイルをクリーンアップする。

**`*-devel` でのクリーンアップ内容:**
```dockerfile
FROM simple-builder AS simple-devel
RUN conda clean -afy \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && pip cache purge 2>/dev/null || true
```

**`*-runtime` でのクリーンアップ内容:**
```dockerfile
FROM runtime-base AS simple-runtime
# COPY で /opt/conda/envs/py のみを取り出しているため builder の apt/conda キャッシュは持ち込まれない。
# COPY 後に .pyc/__pycache__ だけ除去する（最小限）。
COPY --from=simple-builder /opt/conda/envs/py /opt/conda/envs/py
RUN find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
```

**クリーンアップ対象一覧:**

| 対象 | devel | runtime |
|---|---|---|
| `conda clean -afy` | ✅ | ➖ (COPY で持ち込まれない) |
| `pip cache purge` | ✅ | ➖ (`--mount=type=cache` のため元々レイヤに残らない) |
| `*.pyc` / `__pycache__` | ✅ | ✅ |
| apt キャッシュ (`/var/lib/apt/lists/`) | ➖ (builder で実施済) | ➖ (runtime-base で実施済) |

---

### TODO-3: build-matrix.yaml — ターゲット追従

各マトリクスエントリの `targets` に `*-builder` を追加（中間イメージとして push したい場合）:

```yaml
- name: "simple-builder"
  tag: "simple-builder-cu130-py314-torch2.9.0"
- name: "ray-builder"
  tag: "ray-builder-cu130-py314-torch2.9.0-ray3.0.0.dev0"
- name: "marimo-builder"
  tag: "marimo-builder-cu130-py314-torch2.9.0-ray3.0.0.dev0"
```

`*-devel` / `*-runtime` の既存エントリはそのまま（ターゲット名変更なし）。

---

### TODO-4: tools/build_matrix.py — 変更なし

`*-builder` ターゲットを build-matrix.yaml に追記した場合、ツールはそのまま対応する。

---

### TODO-5: README / docs 更新

- [README.md](../README.md) のステージ説明図を更新（builder 追加、責務分担の説明）
- [docs/architecture.md](architecture.md) のステージツリー更新

---

### TODO-6: 動作確認

1. 最小ビルド（既存互換確認）—— ✅ 6/6 成功 (CUDA 12.8.1 + Python 3.13)
   ```
   simple-devel / simple-runtime / ray-devel / ray-runtime / marimo-devel / marimo-runtime
   ```
2. builder キャッシュ再利用確認 —— ✅ ビルド 2回目以降、`simple-builder` 層が全ステップ CACHED
3. `marimo-runtime` で `marimo edit` 起動チェック —— ✅
   ```
   marimo edit --help → 正常起動、Usage 表示確認
   ```
4. `marimo-runtime` で `ray.init()` / `ray.shutdown()` チェック —— ✅
   ```
   ray version: 3.0.0.dev0
   ray.init(): OK  — resources: {'memory': ..., 'CPU': 1.0, ...}
   ray.shutdown(): OK
   ```

---

## 受け入れ条件チェックリスト (Issue #18 AC)

- [x] `simple-builder` / `ray-builder` / `marimo-builder` が Dockerfile に存在する
- [x] 各 `*-devel` と `*-runtime` が対応する `*-builder` から派生している
- [x] `*-devel` / `*-runtime` がキャッシュ（`conda pkgs`, `.pyc`, `__pycache__`）をクリーンアップしている
- [x] 既存ターゲット `simple-runtime` / `ray-runtime` / `marimo-runtime` は破壊されない
- [x] 最小ビルドで動作確認（全6ターゲット CUDA 12.8.1 + Python 3.13 で成功）
- [x] `marimo-runtime` で `marimo edit` 起動確認
- [x] `marimo-runtime` で `ray.init()` / `ray.shutdown()` 動作確認
