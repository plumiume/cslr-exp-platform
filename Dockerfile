# =============================================================================
# PyG + Ray + Marimo  |  CUDA 13.x + Python 3.14
# =============================================================================
# ステージツリー:
#   simple-builder ─→ simple-devel
#                  ─→ simple-runtime      (from runtime-base)
#   ray-builder (from simple-builder)
#              ─→ ray-devel
#              ─→ ray-runtime             (from runtime-base)
#   marimo-builder (from ray-builder)
#                 ─→ marimo-devel
#                 ─→ marimo-runtime       (from runtime-base)
#
# ステージ責務:
#   *-builder  : BuildKit キャッシュマウントを活用した高速ビルド専用（中間ステージ）
#                クリーンアップしない
#   *-devel    : *-builder から派生。conda/pip キャッシュ・.pyc を除去した開発用最終イメージ
#   *-runtime  : runtime-base + COPY --from=*-builder。.pyc のみ除去した本番用最終イメージ
#
# 保持するもの（runtime で torch.utils.cpp_extension 利用のため）:
#   - torch/include, torch/share (C++/CUDA 拡張ビルドに必須)
#   - .a (静的ライブラリ)
#   - .so のデバッグシンボル (プロファイラ・スタックトレース用)
#   - functorch (torch.compile 系に必要)
#   - nvidia ヘッダー
# =============================================================================

# --- グローバル ARG (全ステージから参照可能) ---
ARG CUDA_VERSION=13.1.1
ARG PYTHON_VERSION=3.14
# CUDA_TAG は PyTorch wheel の index-url に使う。
# cu130 は CUDA 13.x 系ビルド（13.0/13.1 共通 tag）であり、
# CUDA_VERSION=13.1.1 のランタイムで動作させることを意図している。
ARG CUDA_TAG=cu130

# =====================================================================
#  simple-builder : PyTorch + PyG フルビルドステージ (nvcc + cmake あり)
#                  BuildKit キャッシュマウント有効。クリーンアップしない。
# =====================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04 AS simple-builder

ARG PYTHON_VERSION
ARG CUDA_TAG
ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

# ビルドに必要なパッケージ + ccache (ビルド高速化)
# ray-builder で必要な pkg-config/psmisc/unzip も含めて統合
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget ca-certificates git build-essential curl \
        cmake ninja-build ccache \
        pkg-config psmisc unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Miniforge (conda-forge デフォルト)
RUN wget -qO /tmp/miniforge.sh \
        "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh" \
    && bash /tmp/miniforge.sh -b -p ${CONDA_DIR} \
    && rm /tmp/miniforge.sh

# Python 環境
RUN conda create -n py python=${PYTHON_VERSION} -y

# py 環境を PATH の先頭に追加（インタラクティブシェルでも py 環境の python がデフォルトになる）
ENV PATH=/opt/conda/envs/py/bin:${PATH}

# デフォルトで py 環境をアクティベート（conda コマンド用）
RUN echo "conda activate py" >> /root/.bashrc

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

# ビルド最適化環境変数
ENV CMAKE_GENERATOR=Ninja
ENV MAX_JOBS=8
ENV CCACHE_DIR=/tmp/ccache
ENV CCACHE_MAXSIZE=5G
ENV PATH=/usr/lib/ccache:${PATH}

# --- PyTorch ---
# --mount=type=cache でローカルキャッシュを活用するため --no-cache-dir は付けない
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/${CUDA_TAG}

RUN python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA {torch.version.cuda}, cuDNN {torch.backends.cudnn.version()}')"

# --- Ninja (PyG拡張ビルドに必須) ---
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ninja

# --- torch_geometric 本体 ---
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch_geometric

# --- PyG 拡張: wheel → ソースビルド (統合版: キャッシュ効率化) ---
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/tmp/ccache \
    TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])") \
    && echo "=== [Step A] Trying wheels: torch-${TORCH_VERSION}+${CUDA_TAG} ===" \
    && pip install \
        pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv \
        -f "https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html" \
    || ( echo "=== [Step A] Wheel install failed, will try source build ===" \
        && echo "=== [Step B] Source building scatter/sparse/cluster/spline_conv ===" \
        && pip install --no-build-isolation torch_scatter \
        && pip install --no-build-isolation torch_sparse \
        && pip install --no-build-isolation torch_cluster \
        && pip install --no-build-isolation torch_spline_conv \
        && echo "=== [Step C] Source building pyg_lib (最も時間がかかるステップ) ===" \
        && pip install --no-build-isolation git+https://github.com/pyg-team/pyg-lib.git )

RUN echo "=== simple-builder Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')" \
    && python -c "exec('try:\n import pyg_lib\n print(f\"pyg_lib={pyg_lib.__version__}\")\nexcept Exception:\n print(\"pyg_lib: NOT AVAILABLE\")')"

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  simple-devel : simple-builder + キャッシュクリーンアップ (開発用最終イメージ)
# =====================================================================
FROM simple-builder AS simple-devel

RUN conda clean -afy \
    && pip cache purge 2>/dev/null || true \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  runtime-base : 全 runtime の共通ベース
# =====================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu24.04 AS runtime-base

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/opt/conda/envs/py/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-c"]
WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  simple-runtime : simple-builder の env を直接コピー (conda 本体不要 — 軽量)
# =====================================================================
FROM runtime-base AS simple-runtime

# /opt/conda/envs/py のみコピー (base env/conda 本体を排除)
COPY --from=simple-builder /opt/conda/envs/py /opt/conda/envs/py

RUN find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

RUN echo "=== simple-runtime Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')"

# =====================================================================
#  ray-builder : simple-builder + Ray  (nightly wheel → ソースビルド)
#                BuildKit キャッシュマウント有効。クリーンアップしない。
# =====================================================================
FROM simple-builder AS ray-builder

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

# Bazelisk (Ray ソースビルドに必要 — nightly が使えなかった場合)
RUN --mount=type=cache,target=/root/.cache/wget \
    wget -qO /usr/local/bin/bazel \
        "https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64" \
    && chmod +x /usr/local/bin/bazel

# --- Try 1: nightly wheel (高速) ---
# --- Try 2: master ソースビルド ---
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/bazel \
    --mount=type=cache,target=/tmp/ccache \
    PYTHON_CP_VERSION=$(python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')") \
    && pip install \
        "https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-3.0.0.dev0-${PYTHON_CP_VERSION}-${PYTHON_CP_VERSION}-manylinux2014_x86_64.whl" \
    && echo "=== Ray nightly wheel installed ===" \
    || ( echo "=== Nightly not found – building Ray from source ===" \
        && git clone --depth 1 https://github.com/ray-project/ray.git /tmp/ray \
        && cd /tmp/ray/python \
        && pip install -r requirements.txt \
        && RAY_INSTALL_JAVA=0 pip install . --verbose \
        && cd / && rm -rf /tmp/ray )

# Ray extras
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "ray[data,train,tune,serve]" \
    || echo "=== Note: some Ray extras may not be resolved ==="

RUN echo "=== ray-builder Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')"

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  ray-devel : ray-builder + キャッシュクリーンアップ (開発用最終イメージ)
# =====================================================================
FROM ray-builder AS ray-devel

RUN conda clean -afy \
    && pip cache purge 2>/dev/null || true \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  ray-runtime : ray-builder の env を直接コピー (軽量)
# =====================================================================
FROM runtime-base AS ray-runtime

COPY --from=ray-builder /opt/conda/envs/py /opt/conda/envs/py

RUN find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

RUN echo "=== ray-runtime Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')"

# =====================================================================
#  marimo-builder : ray-builder + Marimo
#                   BuildKit キャッシュマウント有効。クリーンアップしない。
# =====================================================================
FROM ray-builder AS marimo-builder

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install marimo

RUN echo "=== marimo-builder Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')"

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  marimo-devel : marimo-builder + キャッシュクリーンアップ (開発用最終イメージ)
# =====================================================================
FROM marimo-builder AS marimo-devel

RUN conda clean -afy \
    && pip cache purge 2>/dev/null || true \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  marimo-runtime : marimo-builder の env を直接コピー (デフォルトターゲット)
# =====================================================================
FROM runtime-base AS marimo-runtime

COPY --from=marimo-builder /opt/conda/envs/py /opt/conda/envs/py

RUN find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

RUN echo "=== marimo-runtime Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')"
