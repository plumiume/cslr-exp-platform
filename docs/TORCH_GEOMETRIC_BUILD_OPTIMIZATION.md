# PyTorch Geometric 拡張ライブラリのビルド高速化ガイド

このドキュメントでは、`torch_scatter`、`torch_sparse`、`torch_cluster`、`torch_spline_conv`、`pyg_lib` などのPyTorch Geometric拡張ライブラリのビルド時間を短縮する方法をまとめています。

## 目次

1. [概要](#概要)
2. [ビルド戦略](#ビルド戦略)
3. [高速化テクニック](#高速化テクニック)
4. [イメージサイズ削減](#イメージサイズ削減)
5. [トラブルシューティング](#トラブルシューティング)

## 概要

PyTorch Geometric (PyG) の拡張ライブラリは、CUDAカーネルを含むC++/CUDA拡張であり、ソースからビルドすると非常に時間がかかります（1ライブラリあたり5〜15分）。

### ビルド対象ライブラリ

- **torch_scatter**: テンソルのscatter/gather操作の高速化
- **torch_sparse**: スパース行列演算の最適化
- **torch_cluster**: クラスタリングアルゴリズム（k-NN, radius searchなど）
- **torch_spline_conv**: B-Spline畳み込み
- **pyg_lib**: PyGコア機能のC++実装

## ビルド戦略

### 1. Wheelインストール優先（推奨）

最も高速な方法は、プリビルドされたwheelパッケージを使用することです。

```bash
# PyTorchとCUDAのバージョンを取得
TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])")
CUDA_TAG="cu130"  # 例: cu121, cu130, cu131

# Wheelリポジトリからインストール
pip install --no-cache-dir \
    pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv \
    -f "https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html"
```

**メリット:**
- ビルド時間なし（数十秒でインストール完了）
- ビルド依存関係（nvcc、cmake、ninjaなど）が不要

**デメリット:**
- 最新のPyTorch/CUDAバージョンでは利用できない場合がある
- Python 3.14など新しいバージョンではwheel未提供の可能性

### 2. ソースビルド（フォールバック）

Wheelが利用できない場合のソースビルドの最適化方法：

```bash
# 必須: ビルドツールのインストール
apt-get install -y build-essential cmake ninja-build

# Ninjaを使った高速ビルド
pip install --no-cache-dir --no-build-isolation ninja

# ライブラリのビルド（並列度を最大化）
pip install --no-cache-dir --no-build-isolation torch_scatter
pip install --no-cache-dir --no-build-isolation torch_sparse
pip install --no-cache-dir --no-build-isolation torch_cluster
pip install --no-cache-dir --no-build-isolation torch_spline_conv

# pyg_lib（最も時間がかかる）
pip install --no-cache-dir --no-build-isolation \
    git+https://github.com/pyg-team/pyg-lib.git
```

## 高速化テクニック

### 1. `--no-build-isolation` フラグ

**効果**: ビルド時間を約30-40%短縮

```bash
pip install --no-build-isolation torch_scatter
```

このフラグは、pipが各パッケージごとに独立したビルド環境を作成するのを防ぎます。

**注意**: 依存関係が既にインストールされている必要があります。

### 2. Ninja ビルドシステム

**効果**: makeより2-3倍高速

```bash
pip install ninja
export CMAKE_GENERATOR=Ninja
```

Ninjaは並列ビルドに最適化されており、特にC++/CUDAコンパイルで効果的です。

### 3. 並列ビルドジョブ数の調整

```bash
# CPUコア数に応じて調整（デフォルトは全コア使用）
export MAX_JOBS=8

# または環境変数で制御
pip install torch_scatter
```

**推奨値**:
- メモリ豊富（32GB以上）: `MAX_JOBS=$(nproc)`（全コア）
- メモリ制限（16GB以下）: `MAX_JOBS=4`（メモリ不足を回避）

### 4. キャッシュの活用

Docker BuildKitのキャッシュマウントを使用：

```dockerfile
# Dockerfileでのキャッシュマウント
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-build-isolation torch_scatter
```

### 5. 段階的インストール戦略（Dockerfile向け）

```dockerfile
# Step A: Wheelを試行
RUN TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])") \
    && pip install --no-cache-dir \
        pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv \
        -f "https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html" \
    || echo "Wheel install failed, will try source build"

# Step B: torch_scatter/sparse/cluster/spline_convのソースビルド
RUN python -c "import torch_scatter" 2>/dev/null \
    || pip install --no-cache-dir --no-build-isolation torch_scatter && \
       pip install --no-cache-dir --no-build-isolation torch_sparse && \
       pip install --no-cache-dir --no-build-isolation torch_cluster && \
       pip install --no-cache-dir --no-build-isolation torch_spline_conv

# Step C: pyg_libのソースビルド（最も時間がかかる）
RUN python -c "import pyg_lib" 2>/dev/null \
    || pip install --no-cache-dir --no-build-isolation \
        git+https://github.com/pyg-team/pyg-lib.git
```

**この戦略の利点**:
- Wheelが利用可能な場合は高速インストール
- 一部だけWheel利用可能な場合も最適化
- 各ライブラリを個別にチェックするため、部分的な成功も活用

### 6. ccacheの導入（再ビルド時に有効）

```bash
# ccacheのインストール
apt-get install -y ccache

# ccacheの設定
export PATH=/usr/lib/ccache:$PATH
export CCACHE_DIR=/tmp/ccache
export CCACHE_MAXSIZE=5G

# ビルド
pip install --no-build-isolation torch_scatter
```

再ビルド時に大幅な高速化が期待できます（初回は効果なし）。

## イメージサイズ削減

ビルド後のDocker イメージサイズを削減する施策：

### 1. ビルドアーティファクトのクリーンアップ

```bash
# pipキャッシュの削除
rm -rf ~/.cache/pip /tmp/*

# Cargoキャッシュの削除（Rustツールを使った場合）
rm -rf ~/.cargo

# Bazelキャッシュの削除（Rayなどで使用）
rm -rf ~/.cache/bazel
```

### 2. PyTorch不要ファイルの削除

```bash
SP=/opt/conda/envs/py/lib/python*/site-packages

# テスト・開発ファイルの削除
rm -rf $SP/torch/test $SP/torch/testing/_internal
rm -rf $SP/torch/include $SP/torch/share
rm -rf $SP/caffe2 $SP/functorch
rm -rf $SP/torch/utils/benchmark $SP/torch/utils/bottleneck
```

**削減効果**: 約500MB-1GB

### 3. 静的ライブラリ・デバッグシンボルの削除

```bash
# .a（静的ライブラリ）の削除
find /opt/conda/envs/py -type f -name "*.a" -delete

# .pdb（Windowsデバッグシンボル）の削除
find /opt/conda/envs/py -type f -name "*.pdb" -delete

# 共有ライブラリのstrip
find /opt/conda/envs/py -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true
find /opt/conda/envs/py -name "*.so.*" -exec strip --strip-unneeded {} + 2>/dev/null || true
```

**削減効果**: 約200-400MB

### 4. Python中間ファイルの削除

```bash
# .pycファイルの削除
find /opt/conda/envs/py -type f -name "*.pyc" -delete

# __pycache__ディレクトリの削除
find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Cythonソースファイルの削除
find /opt/conda/envs/py -type f -name "*.pyx" -delete
find /opt/conda/envs/py -type f -name "*.pxd" -delete
```

### 5. ヘッダーファイル・ドキュメントの削除

```bash
# NVIDIAヘッダーファイル（runtime不要）
find $SP/nvidia -type f -name "*.h" -delete 2>/dev/null || true

# ドキュメントファイル
find $SP -type f -name "*.rst" -delete
find $SP -type f -name "*.md" ! -name "LICENSE*" -delete 2>/dev/null || true

# テストディレクトリ
find $SP -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find $SP -type d -name "test" -path "*/site-packages/*/test" -exec rm -rf {} + 2>/dev/null || true
```

### 6. マルチステージビルド

```dockerfile
# develステージでビルド
FROM nvidia/cuda:13.1.1-cudnn-devel-ubuntu24.04 AS devel
# ... ビルド処理 ...

# runtimeステージへ環境のみコピー
FROM nvidia/cuda:13.1.1-cudnn-runtime-ubuntu24.04 AS runtime
COPY --from=devel /opt/conda/envs/py /opt/conda/envs/py
```

**削減効果**:
- nvcc、cmake、ninja などのビルドツールを含まない
- base conda環境を含まない
- 約1-2GB削減

## トラブルシューティング

### 問題1: Wheelが見つからない

**症状**:
```
ERROR: Could not find a version that satisfies the requirement torch_scatter
```

**解決策**:
1. PyTorchバージョンとCUDAバージョンを確認
2. [PyG Wheelリポジトリ](https://data.pyg.org/whl/)で対応状況を確認
3. ソースビルドにフォールバック

### 問題2: ソースビルドで "nvcc not found"

**症状**:
```
error: command 'nvcc' failed: No such file or directory
```

**解決策**:
```bash
# CUDAツールキットのdevelイメージを使用
FROM nvidia/cuda:13.1.1-cudnn-devel-ubuntu24.04

# PATHにCUDAを追加
export PATH=/usr/local/cuda/bin:$PATH
```

### 問題3: メモリ不足でビルドが失敗

**症状**:
```
c++: fatal error: Killed signal terminated program cc1plus
```

**解決策**:
```bash
# 並列ジョブ数を制限
export MAX_JOBS=2
pip install --no-build-isolation torch_scatter

# Dockerビルド時はメモリを増やす
docker build --memory=16g --memory-swap=32g -t myimage .
```

### 問題4: CMakeバージョンエラー

**症状**:
```
CMake 3.18 or higher is required
```

**解決策**:
```bash
# 最新CMakeをpipでインストール
pip install --upgrade cmake

# またはapt-getで最新版
apt-get install -y cmake
```

### 問題5: pyg_lib ビルドが非常に遅い

**症状**: pyg_libのビルドに30分以上かかる

**解決策**:
1. Ninjaビルドシステムを使用（必須）
2. 十分なメモリを確保（推奨16GB以上）
3. ccacheを使用して再ビルドを高速化

```bash
pip install ninja
export CMAKE_GENERATOR=Ninja
pip install --no-build-isolation git+https://github.com/pyg-team/pyg-lib.git
```

## ベンチマーク

典型的なビルド時間（16コアCPU、32GBメモリ環境）:

| 方法 | torch_scatter | torch_sparse | pyg_lib | 合計 |
|------|---------------|--------------|---------|------|
| Wheel | 10秒 | 10秒 | 10秒 | **30秒** |
| ソースビルド（make） | 8分 | 10分 | 25分 | **43分** |
| ソースビルド（ninja + --no-build-isolation） | 5分 | 6分 | 15分 | **26分** |

**推奨**: 常にWheel優先、利用不可時のみソースビルド

## まとめ

### ビルド高速化のベストプラクティス

1. **Wheelを最優先**: プリビルドパッケージが利用可能か必ず確認
2. **Ninjaを使用**: makeより2-3倍高速
3. **--no-build-isolation**: ビルド環境の再作成を回避
4. **並列度を調整**: メモリに応じてMAX_JOBSを設定
5. **段階的戦略**: Wheel → ソースビルドのフォールバック

### イメージサイズ削減のベストプラクティス

1. **マルチステージビルド**: devel → runtimeで環境のみコピー
2. **徹底的なクリーンアップ**: ビルド後に不要ファイルを削除
3. **stripでシンボル削除**: .soファイルから20-30%削減
4. **テスト・ドキュメント削除**: 実行に不要なファイルを除去

これらの施策を組み合わせることで、ビルド時間を大幅に短縮し、最終的なDockerイメージサイズを数GB削減できます。
