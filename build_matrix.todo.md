# Docker Build Matrix - ビルド進捗管理

最終更新: 2026-02-11

## イメージサイズ削減の方針変更（レビュー反映）

**変更理由**: runtime で torch.utils.cpp_extension を使う拡張ビルドが必要、および devel でプロファイラ・functorch/torch.compile 系を使用するため。

**新しい方針**:
- **devel**: 最小限のクリーンアップのみ（__pycache__/.pyc + conda clean）
- **runtime**: torch.utils.cpp_extension に必要なファイルを保持
  - torch/include, torch/share (C++/CUDA 拡張ビルドに必須)
  - .a (静的ライブラリ)
  - .so のデバッグシンボル (プロファイラ・スタックトレース用)
  - functorch (torch.compile 系に必要)
  - nvidia ヘッダー
- **Docker BuildKit キャッシュマウント**: pip/bazel/ccache で高速化

**期待される軽量化**:
- base env / conda 本体の排除: ~200-500MB削減
- __pycache__/.pyc の削除: ~50-100MB削減
- 合計: 250-600MB削減（控えめな見積もり）

**イメージ名**:
- 修正前: `plumiume/cslr-exp-platform` ❌
- 修正後: `plumiiume/cslr-exp-platform` ✅ (iが2つ)

## ビルド状況サマリー

| CUDA   | Python | ターゲット         | 状態 | 最終ビルド | イメージサイズ | 備考 |
|--------|--------|-------------------|------|------------|---------------|------|
| 12.8.1 | 3.13   | devel             | ✅   | 2026-02-10 | 29.4GB        | -    |
| 12.8.1 | 3.13   | runtime           | ✅   | 2026-02-10 | 20.3GB        | -    |
| 12.8.1 | 3.13   | ray-devel         | ✅   | 2026-02-10 | 30.2GB        | -    |
| 12.8.1 | 3.13   | ray-runtime       | ✅   | 2026-02-10 | 20.6GB        | -    |
| 12.8.1 | 3.13   | marimo-devel      | ✅   | 2026-02-10 | 30.4GB        | -    |
| 12.8.1 | 3.13   | marimo-runtime    | ✅   | 2026-02-10 | -             | 既存 |
| 13.1.1 | 3.14   | devel             | ⏳   | -          | -             | -    |
| 13.1.1 | 3.14   | runtime           | ⏳   | -          | -             | -    |
| 13.1.1 | 3.14   | ray-devel         | ⏳   | -          | -             | -    |
| 13.1.1 | 3.14   | ray-runtime       | ⏳   | -          | -             | -    |
| 13.1.1 | 3.14   | marimo-devel      | ⏳   | -          | -             | -    |
| 13.1.1 | 3.14   | marimo-runtime    | ✅   | 2026-02-10 | 14.5GB        | 5.6分 |
| 12.8.1 | 3.14   | devel             | ⏳   | -          | -             | -    |
| 12.8.1 | 3.14   | runtime           | ⏳   | -          | -             | -    |
| 12.8.1 | 3.14   | ray-devel         | ⏳   | -          | -             | -    |
| 12.8.1 | 3.14   | ray-runtime       | ⏳   | -          | -             | -    |
| 12.8.1 | 3.14   | marimo-devel      | ⏳   | -          | -             | -    |
| 12.8.1 | 3.14   | marimo-runtime    | ✅   | 2026-02-10 | 20.9GB        | 27.5分 |

**凡例:**
- ⏳ 未実行
- 🔄 ビルド中
- ✅ 成功
- ❌ 失敗
- ⚠️  警告あり

## ビルド優先順位

### Phase 1: 基本構成（最優先）
- [x] CUDA 12.8.1 + Python 3.13 + marimo-runtime (既存)
- [x] CUDA 12.8.1 + Python 3.13 + runtime (21.1分)
- [x] CUDA 12.8.1 + Python 3.13 + ray-runtime (4.8分)

### Phase 2: 開発環境
- [x] CUDA 12.8.1 + Python 3.13 + devel (2.8分 - キャッシュ利用)
- [x] CUDA 12.8.1 + Python 3.13 + ray-devel (0.2分 - キャッシュ利用)
- [x] CUDA 12.8.1 + Python 3.13 + marimo-devel (0.3分 - キャッシュ利用)

### Phase 3: 次世代環境（CUDA 13.x）
- [x] CUDA 13.1.1 + Python 3.14 + marimo-runtime (5.6分)
- [ ] CUDA 13.1.1 + Python 3.14 + runtime
- [ ] CUDA 13.1.1 + Python 3.14 + ray-runtime

### Phase 4: Python 3.14 バリエーション
- [x] CUDA 12.8.1 + Python 3.14 + marimo-runtime (27.5分)
- [ ] CUDA 12.8.1 + Python 3.14 + runtime
- [ ] CUDA 12.8.1 + Python 3.14 + ray-runtime

### Phase 5: 全開発環境
- [ ] CUDA 13.1.1 + Python 3.14 + devel
- [ ] CUDA 13.1.1 + Python 3.14 + ray-devel
- [ ] CUDA 13.1.1 + Python 3.14 + marimo-devel
- [ ] CUDA 12.8.1 + Python 3.14 + devel
- [ ] CUDA 12.8.1 + Python 3.14 + ray-devel
- [ ] CUDA 12.8.1 + Python 3.14 + marimo-devel

## 各パターンの想定ビルド時間

| ターゲット         | 想定時間 | 実測時間（初回） | 実測時間（キャッシュ） | 備考                           |
|-------------------|----------|-----------------|----------------------|--------------------------------|
| devel             | 40-60分  | 21.1分         | 2.8分                | 完全ビルド（PyG等ソースビルド） |
| runtime           | 5-10分   | 21.1分         | -                    | devel からコピー              |
| ray-devel         | 50-70分  | -              | 0.2分                | devel + Ray ビルド（nightly wheel使用時）|
| ray-runtime       | 5-10分   | 4.8分          | -                    | ray-devel からコピー          |
| marimo-devel      | 55-75分  | -              | 0.3分                | ray-devel + marimo            |
| marimo-runtime    | 5-10分   | 5.6-27.5分     | -                    | marimo-devel からコピー       |

**累積時間（1セット - CUDA 12.8.1 + Python 3.13）**: 約30分（キャッシュ利用時）

**新しいCUDA/Pythonバージョン（初回）**: 約30-40分（PyGソースビルドあり）

## ビルド実行コマンド

### Phase 1 の実行
```powershell
# runtime (基本ランタイム)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target runtime

# ray-runtime (Ray付きランタイム)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-runtime
```

### Phase 2 の実行
```powershell
# devel (開発環境ベース)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target devel

# ray-devel (Ray開発環境)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-devel

# marimo-devel (完全開発環境)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target marimo-devel
```

### 一括実行（CUDA 12.8.1 + Python 3.13 全パターン）
```powershell
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13
```

## CI/CD 定期ビルド計画

### スケジュール案
- **毎週月曜 02:00 JST**: Phase 1（基本構成）
- **毎週水曜 02:00 JST**: Phase 2（開発環境）
- **毎週金曜 02:00 JST**: Phase 3（次世代環境）
- **毎月1日 02:00 JST**: 全パターンビルド

### ビルド環境要件
- Docker with BuildKit
- 最低 100GB 空きストレージ
- 16GB以上のメモリ推奨
- ローカルランナー: Windows PowerShell 7.x

## トラブルシューティングログ

### 2026-02-10
- [✅] CUDA 12.8.1 + Python 3.13 + runtime: 成功
  - ビルド時間: 21.1分
  - イメージサイズ: 20.3GB
  
- [✅] CUDA 12.8.1 + Python 3.13 + ray-runtime: 成功（2回目）
  - ビルド時間: 4.8分
  - イメージサイズ: 20.6GB
  - 問題: 初回ビルド失敗 - Dockerfile内のPythonバージョンがハードコードされていた（cp314）
  - 解決: Python バージョンを動的に取得するよう修正

- [✅] CUDA 12.8.1 + Python 3.13 + devel: 成功
  - ビルド時間: 2.8分（キャッシュ利用）
  - イメージサイズ: 29.4GB

- [✅] CUDA 12.8.1 + Python 3.13 + ray-devel: 成功
  - ビルド時間: 0.2分（キャッシュ利用）
  - イメージサイズ: 30.2GB

- [✅] CUDA 12.8.1 + Python 3.13 + marimo-devel: 成功
  - ビルド時間: 0.3分（キャッシュ利用）
  - イメージサイズ: 30.4GB

- [✅] CUDA 13.1.1 + Python 3.14 + marimo-runtime: 成功
  - ビルド時間: 5.6分
  - イメージサイズ: 14.5GB
  - 備考: PyG拡張のソースビルドあり（約9分）

- [✅] CUDA 12.8.1 + Python 3.14 + marimo-runtime: 成功
  - ビルド時間: 27.5分
  - イメージサイズ: 20.9GB
  - 備考: PyG拡張のソースビルドあり（約13分）

## 次回更新予定

- [ ] 各ターゲットのビルド完了後、状態を更新
- [ ] 実際のビルド時間を記録
- [ ] イメージサイズを記録
- [ ] エラーがあれば詳細をトラブルシューティングログに追加

---

## イメージサイズ削減プラン

### 現状分析

| イメージ | サイズ | ベースイメージ概算 | conda 概算 |
|----------|--------|-------------------|-----------|
| devel (cu128-py313)       | 29.4GB | ~8GB (devel)   | ~21GB |
| runtime (cu128-py313)     | 20.3GB | ~5GB (runtime) | ~15GB |
| ray-runtime (cu128-py313) | 20.6GB | ~5GB (runtime) | ~15.5GB |
| marimo-runtime (cu130-py314) | 14.5GB | ~3.5GB (runtime) | ~11GB |
| marimo-runtime (cu128-py314) | 20.9GB | ~5GB (runtime) | ~16GB |

### 問題点

1. **`/opt/conda` 全体をコピーしている**
   - base env（Miniforge本体 + solver + 不要パッケージ）: ~1.5GB
   - conda pkg キャッシュ残骸
   - py env 内の不要ファイル（テスト、ドキュメント、ヘッダー）

2. **PyTorch の不要コンポーネント**
   - `torch/test/` : ~500MB
   - `torch/lib/*.a` (静的ライブラリ) : ~200MB
   - `caffe2/` レガシー部分
   - `torchvision`/`torchaudio` 未使用なら ~1-2GB

3. **conda 環境構造の冗長性**
   - base env + py env の二重管理
   - conda 自体のメタデータ

4. **共有ライブラリの未 strip**
   - `.so` ファイルにデバッグシンボルが残存: ~500MB-1GB

5. **レイヤー構造**
   - RUN ごとにレイヤーが作られ、中間ファイルが残る

### 削減施策（優先度順）

#### 🔴 施策 A: conda-pack で py env のみ転送（効果: -3〜5GB）

```dockerfile
# devel 最終段で conda-pack
RUN conda install -n base conda-pack -y \
    && conda pack -n py -o /tmp/py-env.tar.gz --ignore-editable-packages \
    && conda clean -afy

# runtime で展開（conda 本体不要）
FROM nvidia/cuda:...-runtime-ubuntu24.04 AS runtime
RUN mkdir -p /opt/env && tar xzf /tmp/py-env.tar.gz -C /opt/env \
    && /opt/env/bin/conda-unpack
ENV PATH=/opt/env/bin:$PATH
```

- base env と conda メタデータを完全排除
- `/opt/conda` → `/opt/env`（py env のみ）

#### 🔴 施策 B: PyTorch 不要ファイル削除の強化（効果: -1〜2GB）

```dockerfile
# devel 最終クリーニングに追加
RUN rm -rf /opt/conda/envs/py/lib/python*/site-packages/torch/test \
    && rm -rf /opt/conda/envs/py/lib/python*/site-packages/torch/include \
    && rm -rf /opt/conda/envs/py/lib/python*/site-packages/torch/share \
    && rm -rf /opt/conda/envs/py/lib/python*/site-packages/caffe2 \
    && find /opt/conda/envs/py -name "*.a" -delete \
    && find /opt/conda/envs/py -name "*.pdb" -delete
```

#### 🟡 施策 C: .so ファイルの strip（効果: -500MB〜1GB）

```dockerfile
RUN find /opt/conda/envs/py -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true
```

#### 🟡 施策 D: torchvision / torchaudio の分離（効果: -1〜2GB）

実際に使用しているか確認し、不要なら削除:
```dockerfile
# torchvision / torchaudio が不要な場合
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/${CUDA_TAG}
# 必要な場合のみ追加
```

#### 🟢 施策 E: base イメージの見直し（効果: -1〜3GB）

```dockerfile
# cudnn-runtime → runtime（cuDNN 不要なら）
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04

# または Ubuntu ベース + 必要な CUDA ライブラリのみ pip から取得
```

#### 🟢 施策 F: Miniforge → uv/pip only（効果: -1.5GB）

runtime で conda を使わず、uv + venv で構成:
```dockerfile
FROM nvidia/cuda:...-runtime-ubuntu24.04 AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=devel /opt/conda/envs/py/lib/python*/site-packages /opt/site-packages
ENV PYTHONPATH=/opt/site-packages
```

### 削減効果の見積もり

| 施策 | 効果 | 難易度 | リスク | 優先度 |
|------|------|--------|--------|--------|
| A: conda-pack | -3〜5GB | 中 | 低 | 🔴 高 |
| B: torch 不要削除強化 | -1〜2GB | 低 | 低 | 🔴 高 |
| C: strip .so | -0.5〜1GB | 低 | 低 | 🟡 中 |
| D: torchvision/audio 分離 | -1〜2GB | 低 | 要確認 | 🟡 中 |
| E: base イメージ見直し | -1〜3GB | 中 | 中 | 🟢 低 |
| F: uv/pip only | -1.5GB | 高 | 中 | 🟢 低 |

### 目標サイズ

| ターゲット | 現在 | 施策A+B+C | 施策全適用 |
|-----------|------|-----------|-----------|
| runtime   | 20.3GB | ~15GB | ~12GB |
| ray-runtime | 20.6GB | ~15.5GB | ~12.5GB |
| marimo-runtime | 20.9GB | ~16GB | ~13GB |

### 実装順序

1. **Step 1**: 施策 B（torch 不要削除）+ 施策 C（strip）— リスク最小
2. **Step 2**: 施策 A（conda-pack）— 最大効果
3. **Step 3**: 施策 D（torchvision/audio 分離）— 要件確認後
4. **Step 4**: 施策 E, F — 長期的な構成変更
