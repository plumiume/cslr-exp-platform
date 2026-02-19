# Ray Runtime Migration Plan

## 概要
rayproject/ray公式イメージから、Dockerfileのray-runtimeイメージへ移行する計画

## 目的
- PyTorch + PyG + Ray + Marimoを統合したカスタムイメージの使用
- CUDA 13.x + Python 3.14 環境の実現
- marimo-ray連携の検証

## 現在の構成

### イメージ
- **ray-cpu**: rayproject/ray:latest
- **ray-gpu**: rayproject/ray:latest-gpu
- **marimo**: marimo-team/marimo:latest

### 課題
- rayproject/ray イメージにはPyG/Marimoが含まれていない
- Python 3.14サポートが不明
- 各サービスが分離しており連携が複雑

## 新しい構成

### Dockerfile ステージ
```
devel (CUDA devel)
  ├─ ray-devel (+ Ray)
  │   └─ marimo-devel (+ Marimo)
  │
runtime (CUDA runtime, 軽量)
  ├─ ray-runtime (+ Ray) ← CPU/GPU両用
  │   └─ marimo-runtime (+ Marimo) ← デフォルト
```

### ターゲットイメージ
1. **ray-runtime** (CPU/GPU共用)
   - CUDA 13.1.1 runtime
   - Python 3.14 (conda)
   - PyTorch + PyG + Ray
   - サイズ最適化

2. **marimo-runtime** (オプション)
   - ray-runtime + Marimo
   - ノートブック開発用

## 変更内容

### 1. Dockerfile調整 ✓
- ビルドステージは完成済み
- ray-runtimeがCPU/GPU両用として機能

### 2. ビルドコマンド追加
- CPU版: `docker build --target ray-runtime -t cslr-exp-platform:ray-runtime .`
- GPU版: 同じイメージ（CUDA runtimeはGPU対応済み）
- Marimo版: `docker build --target marimo-runtime -t cslr-exp-platform:marimo-runtime .`

### 3. compose.yaml.jinja2 更新

```yaml
# ビルドセクション追加
x-ray-build: &ray-build
  build:
    context: ..
    dockerfile: Dockerfile
    target: ray-runtime
    args:
      - CUDA_VERSION=13.1.1
      - PYTHON_VERSION=3.14
      - CUDA_TAG=cu130

x-ray: &ray
  image: ${PROJECT_NAME:-cslr-exp-platform}:ray-runtime
  # or build: *ray-build
```

### 4. config.yaml 更新

```yaml
services:
  ray:
    cpu:
      # image: "rayproject/ray:latest"
      image: "cslr-exp-platform:ray-runtime"
      build:
        enabled: true
        dockerfile: "../Dockerfile"
        target: "ray-runtime"
    gpu:
      # image: "rayproject/ray:latest-gpu" 
      image: "cslr-exp-platform:ray-runtime"  # 同じイメージ
      build:
        enabled: true
        dockerfile: "../Dockerfile"
        target: "ray-runtime"
  marimo:
    # image: "marimo-team/marimo:latest"
    image: "cslr-exp-platform:marimo-runtime"
    build:
      enabled: true
      dockerfile: "../Dockerfile"
      target: "marimo-runtime"
```

### 5. ray-ep.sh 修正

**問題点:**
- 現在: `export PATH="/home/ray/anaconda3/bin:$PATH"`
- 新環境: conda は `/opt/conda`、環境名は `py`

**解決策:**
環境変数 `USE_CONDA_ENV` で切り替え

```bash
# Detect environment type
if [ -d "/opt/conda" ] && [ -n "${USE_CONDA_ENV:-}" ]; then
    # Custom ray-runtime image (conda environment)
    export PATH="/opt/conda/bin:$PATH"
    RAY_EXEC="conda run -n py ray"
    PYTHON_EXEC="conda run -n py python"
else
    # Official rayproject/ray image
    export PATH="/home/ray/anaconda3/bin:$PATH"
    RAY_EXEC="ray"
    PYTHON_EXEC="python"
fi

# 以降、rayコマンドは $RAY_EXEC で実行
eval $RAY_EXEC start ...
```

### 6. compose.yaml.jinja2 - entrypoint更新

```yaml
environment:
  - USE_CONDA_ENV=1  # ray-runtime用のフラグ
  
# userとentrypointの調整
user: "1000:1000"  # conda環境は一般ユーザーで実行可能
entrypoint: ["/bin/bash", "-c", "/app/ray.sh"]
```

### 7. marimoサービスの更新

```yaml
marimo:
  image: ${PROJECT_NAME:-cslr-exp-platform}:marimo-runtime
  environment:
    - USE_CONDA_ENV=1
  command: ["conda", "run", "-n", "py", "marimo", "edit", "--host", "0.0.0.0"]
  volumes:
    - ../notebooks:/workspace:rw  # ノートブック保存用
```

## 実装順序

### Phase 1: イメージビルド準備
- [x] Dockerfileのステージ確認
- [ ] ビルド引数の設定確認
- [ ] .dockerignore の作成（ビルド高速化）

### Phase 2: ray-ep.sh の conda対応
- [ ] 環境検出ロジック追加
- [ ] RAY_EXEC変数による実行コマンド切り替え
- [ ] ユーザー権限の調整（root不要に）

### Phase 3: テンプレート更新  
- [ ] compose.yaml.jinja2 にbuildセクション追加
- [ ] 環境変数 USE_CONDA_ENV 追加
- [ ] entrypoint/user の調整

### Phase 4: config.yaml スキーマ拡張
- [ ] BuildConfig モデル追加（ws.py）
- [ ] config.example.yaml 更新
- [ ] config.yaml 更新

### Phase 5: ビルドテスト
- [ ] ray-runtime イメージビルド
- [ ] marimo-runtime イメージビルド
- [ ] イメージサイズ確認

### Phase 6: 起動テスト
- [ ] ray-cpu 起動テスト
- [ ] ray-gpu 起動テスト（GPU環境）
- [ ] marimo 起動テスト

### Phase 7: 連携テスト
- [ ] Ray Dashboard アクセス確認
- [ ] Ray Client API 接続テスト
- [ ] marimo → ray-cpu 接続テスト
- [ ] PyG動作確認

### Phase 8: ドキュメント更新
- [ ] README.md にビルド手順追加
- [ ] カスタムイメージ利用の説明
- [ ] トラブルシューティング追加

## 検証項目

### イメージサイズ
```bash
docker images cslr-exp-platform:ray-runtime --format "{{.Size}}"
# 目標: < 8GB
```

### Ray起動確認
```bash
docker exec cslr-exp-platform-ray-cpu conda run -n py ray status
```

### PyG動作確認
```python
import torch
import torch_geometric as pyg
print(f"PyTorch: {torch.__version__}")
print(f"PyG: {pyg.__version__}")
```

### Marimo-Ray連携
```python
# marimoノートブック内
import ray
ray.init("ray://ray-cpu:10001")
print(ray.cluster_resources())
```

## ロールバック計画

問題が発生した場合:
1. config.yaml のイメージを元に戻す
2. `uv run ws generate` で再生成
3. `uv run ws up -d --build` で再起動

## 推定所要時間

- Phase 1-2: 準備 (30分)
- Phase 3-4: 実装 (1時間)
- Phase 5-7: テスト (1時間)
- Phase 8: ドキュメント (30分)

**合計: 約3時間**

## 備考

- GPU環境がない場合はray-gpu のテストはスキップ
- ビルドキャッシュを活用して高速化
- 初回ビルドはPyGのコンパイルで時間がかかる（20-30分）
