# =============================================================================
# PyG + Ray + Marimo  |  CUDA 13.x + Python 3.14
# =============================================================================
# ステージツリー:
#   devel  ─→ ray-devel  ─→ marimo-devel   (開発・ビルド用; conda あり)
#   runtime-base ─→ runtime (from devel)
#                ─→ ray-runtime (from ray-devel)
#                ─→ marimo-runtime (from marimo-devel)
#
# 最適化施策:
#   A) /opt/conda/envs/py のみ直接コピー (base env/conda 本体を排除)
#   B) Docker BuildKit キャッシュマウントでビルド高速化
#   C) 最小限のクリーンアップ（__pycache__/.pyc のみ）
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
ARG CUDA_TAG=cu130

# =====================================================================
#  simple-devel : フルビルドステージ (nvcc + cmake あり)
# =====================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04 AS simple-devel

ARG PYTHON_VERSION
ARG CUDA_TAG
ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

# ビルドに必要なパッケージ + ccache (ビルド高速化)
# ray-devel で必要な pkg-config/psmisc/unzip も含めて統合
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
    && rm /tmp/miniforge.sh \
    && conda clean -afy

# Python 環境
RUN conda create -n py python=${PYTHON_VERSION} -y \
    && conda clean -afy

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
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/${CUDA_TAG}

RUN python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA {torch.version.cuda}, cuDNN {torch.backends.cudnn.version()}')"

# --- Ninja (PyG拡張ビルドに必須) ---
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir ninja

# --- torch_geometric 本体 ---
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir torch_geometric

# --- PyG 拡張: wheel → ソースビルド (統合版: キャッシュ効率化) ---
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/tmp/ccache \
    TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])") \
    && echo "=== [Step A] Trying wheels: torch-${TORCH_VERSION}+${CUDA_TAG} ===" \
    && pip install --no-cache-dir \
        pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv \
        -f "https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html" \
    || ( echo "=== [Step A] Wheel install failed, will try source build ===" \
        && echo "=== [Step B] Source building scatter/sparse/cluster/spline_conv ===" \
        && pip install --no-cache-dir --no-build-isolation torch_scatter \
        && pip install --no-cache-dir --no-build-isolation torch_sparse \
        && pip install --no-cache-dir --no-build-isolation torch_cluster \
        && pip install --no-cache-dir --no-build-isolation torch_spline_conv \
        && echo "=== [Step C] Source building pyg_lib (最も時間がかかるステップ) ===" \
        && pip install --no-cache-dir --no-build-isolation git+https://github.com/pyg-team/pyg-lib.git )

# --- devel: 最小限のクリーンアップ（プロファイラ・拡張ビルド・functorch 保持） ---
RUN echo "=== devel Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')" \
    && python -c "exec('try:\n import pyg_lib\n print(f\"pyg_lib={pyg_lib.__version__}\")\nexcept Exception:\n print(\"pyg_lib: NOT AVAILABLE\")')" \
    # --- 最小限のクリーンアップ: .pyc/__pycache__ のみ ---
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && conda clean -afy

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
#  simple-runtime : env 直接コピー (conda 本体不要 — 軽量)
# =====================================================================
FROM runtime-base AS simple-runtime

# 施策 A: /opt/conda/envs/py のみコピー (base env/conda 本体を排除)
COPY --from=simple-devel /opt/conda/envs/py /opt/conda/envs/py

RUN echo "=== simple-runtime Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')"

# =====================================================================
#  ray-devel : simple-devel + Ray  (nightly wheel → ソースビルド)
# =====================================================================
FROM simple-devel AS ray-devel

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

# Bazelisk (Ray ソースビルドに必要 — nightly が使えなかった場合)
# BuildKit キャッシュを使ってダウンロードを高速化
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
    && pip install --no-cache-dir \
        "https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-3.0.0.dev0-${PYTHON_CP_VERSION}-${PYTHON_CP_VERSION}-manylinux2014_x86_64.whl" \
    && echo "=== Ray nightly wheel installed ===" \
    || ( echo "=== Nightly not found – building Ray from source ===" \
        && git clone --depth 1 https://github.com/ray-project/ray.git /tmp/ray \
        && cd /tmp/ray/python \
        && pip install --no-cache-dir -r requirements.txt \
        && RAY_INSTALL_JAVA=0 pip install --no-cache-dir . --verbose \
        && cd / && rm -rf /tmp/ray )

# Ray extras
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir "ray[data,train,tune,serve]" \
    || echo "=== Note: some Ray extras may not be resolved ==="

# クリーニング（最小限）
RUN echo "=== ray-devel Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')" \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && conda clean -afy

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  ray-runtime : env 直接コピー (軽量)
# =====================================================================
FROM runtime-base AS ray-runtime

COPY --from=ray-devel /opt/conda/envs/py /opt/conda/envs/py

RUN echo "=== ray-runtime Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')"

# =====================================================================
#  marimo-devel : ray-devel + Marimo
# =====================================================================
FROM ray-devel AS marimo-devel

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir marimo

# クリーニング（最小限）
RUN echo "=== marimo-devel Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')" \
    && find /opt/conda/envs/py -type f -name "*.pyc" -delete \
    && find /opt/conda/envs/py -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && conda clean -afy

WORKDIR /workspace
CMD ["bash"]

# =====================================================================
#  marimo-runtime : env 直接コピー (デフォルトターゲット)
# =====================================================================
FROM runtime-base AS marimo-runtime

COPY --from=marimo-devel /opt/conda/envs/py /opt/conda/envs/py

RUN echo "=== marimo-runtime Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')"