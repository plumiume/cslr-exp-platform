# =============================================================================
# PyG + Ray + Marimo  |  CUDA 13.x + Python 3.14
# =============================================================================
# ステージツリー:
#   devel  ─→ ray-devel  ─→ marimo-devel   (開発・ビルド用)
#   runtime ─→ ray-runtime ─→ marimo-runtime (デプロイ用)
#
# devel   : nvidia/cuda CUDNN devel   + Miniforge + PyTorch + PyG (ソースビルド)
# runtime : nvidia/cuda CUDNN runtime + conda 環境コピー (軽量)
# ray-*   : + ray[data,train,tune,serve]
# marimo-*: + marimo
# =============================================================================

# --- グローバル ARG (全ステージから参照可能) ---
ARG CUDA_VERSION=13.1.1
ARG PYTHON_VERSION=3.14
ARG CUDA_TAG=cu130

# =====================================================================
#  devel : フルビルドステージ (nvcc + cmake あり)
# =====================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04 AS devel

ARG PYTHON_VERSION
ARG CUDA_TAG
ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

# ビルドに必要なパッケージ
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget ca-certificates git build-essential curl \
        cmake ninja-build \
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

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

# --- PyTorch ---
RUN pip install --no-cache-dir \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/${CUDA_TAG} \
    && rm -rf ~/.cache/pip /tmp/*

RUN python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA {torch.version.cuda}, cuDNN {torch.backends.cudnn.version()}')"

# --- torch_geometric 本体 ---
RUN pip install --no-cache-dir torch_geometric \
    && rm -rf ~/.cache/pip /tmp/*

# --- PyG 拡張: wheel → ソースビルド ---
RUN TORCH_VERSION=$(python -c "import torch; print(torch.__version__.split('+')[0])") \
    && echo "=== [Step A] Trying wheels: torch-${TORCH_VERSION}+${CUDA_TAG} ===" \
    && pip install --no-cache-dir \
        pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv \
        -f "https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA_TAG}.html" \
    || echo "=== [Step A] Wheel install failed, will try source build ==="

RUN python -c "import torch_scatter" 2>/dev/null \
    && echo "=== torch_scatter already installed ===" \
    || ( echo "=== [Step B] Source building scatter/sparse/cluster/spline_conv ===" \
        && pip install --no-cache-dir --no-build-isolation torch_scatter \
        && pip install --no-cache-dir --no-build-isolation torch_sparse \
        && pip install --no-cache-dir --no-build-isolation torch_cluster \
        && pip install --no-cache-dir --no-build-isolation torch_spline_conv )

RUN python -c "import pyg_lib" 2>/dev/null \
    && echo "=== pyg_lib already installed ===" \
    || ( echo "=== [Step C] Source building pyg_lib ===" \
        && pip install --no-cache-dir --no-build-isolation ninja \
        && pip install --no-cache-dir --no-build-isolation git+https://github.com/pyg-team/pyg-lib.git ) \
    && rm -rf ~/.cache/pip /tmp/* /root/.cargo

# 確認 & 最終クリーニング
RUN echo "=== devel Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')" \
    && python -c "exec('try:\n import pyg_lib\n print(f\"pyg_lib={pyg_lib.__version__}\")\nexcept Exception:\n print(\"pyg_lib: NOT AVAILABLE\")')" \
    && conda clean -afy \
    && rm -rf ~/.cache /tmp/* /var/tmp/*

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]

# =====================================================================
#  runtime : devel から conda 環境をコピー (軽量)
# =====================================================================
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=devel ${CONDA_DIR} ${CONDA_DIR}

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN echo "=== runtime Verification ===" \
    && python -c "import sys; print(f'Python={sys.version}')" \
    && python -c "import torch; print(f'torch={torch.__version__}, CUDA={torch.version.cuda}')" \
    && python -c "import torch_geometric; print(f'torch_geometric={torch_geometric.__version__}')"

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]

# =====================================================================
#  ray-devel : devel + Ray  (nightly wheel → ソースビルド チャレンジ)
# =====================================================================
FROM devel AS ray-devel

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

# Bazelisk (Ray ソースビルドに必要 — nightly が使えなかった場合)
RUN apt-get update && apt-get install -y --no-install-recommends \
        pkg-config psmisc unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && wget -qO /usr/local/bin/bazel \
        "https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64" \
    && chmod +x /usr/local/bin/bazel

# --- Try 1: nightly wheel (高速) ---
# --- Try 2: master ソースビルド (SUPPORTED_PYTHONS に 3.14 追加済み) ---
RUN pip install --no-cache-dir \
        "https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-3.0.0.dev0-cp314-cp314-manylinux2014_x86_64.whl" \
    && echo "=== Ray nightly wheel installed ===" \
    || ( echo "=== Nightly not found – building Ray from source ===" \
        && git clone --depth 1 https://github.com/ray-project/ray.git /tmp/ray \
        && cd /tmp/ray/python \
        && pip install --no-cache-dir -r requirements.txt \
        && RAY_INSTALL_JAVA=0 pip install --no-cache-dir . --verbose \
        && cd / && rm -rf /tmp/ray ) \
    && rm -rf ~/.cache/pip ~/.cache/bazel /tmp/* /var/tmp/*

# Ray extras (既にインストール済みなら依存のみ追加)
RUN pip install --no-cache-dir "ray[data,train,tune,serve]" \
    || echo "=== Note: some Ray extras may not be resolved ===" \
    && rm -rf ~/.cache/pip /tmp/*

RUN echo "=== ray-devel Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')" \
    && conda clean -afy \
    && rm -rf ~/.cache /tmp/* /var/tmp/*

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]

# =====================================================================
#  ray-runtime : runtime + Ray (ray-devel から conda コピー)
# =====================================================================
FROM runtime AS ray-runtime

# ray-devel の conda を上書きコピー (PyG + Ray を含む)
COPY --from=ray-devel /opt/conda /opt/conda

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN echo "=== ray-runtime Verification ===" \
    && python -c "import ray; print(f'ray={ray.__version__}')"

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]

# =====================================================================
#  marimo-devel : ray-devel + Marimo
# =====================================================================
FROM ray-devel AS marimo-devel

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN pip install --no-cache-dir marimo \
    && rm -rf ~/.cache/pip /tmp/*

RUN echo "=== marimo-devel Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')" \
    && conda clean -afy \
    && rm -rf ~/.cache /tmp/* /var/tmp/*

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]

# =====================================================================
#  marimo-runtime : ray-runtime + Marimo  (デフォルトターゲット)
# =====================================================================
FROM ray-runtime AS marimo-runtime

# marimo-devel の conda を上書きコピー (PyG + Ray + Marimo を含む)
COPY --from=marimo-devel /opt/conda /opt/conda

SHELL ["conda", "run", "-n", "py", "/bin/bash", "-c"]

RUN echo "=== marimo-runtime Verification ===" \
    && python -c "import marimo; print(f'marimo={marimo.__version__}')"

WORKDIR /workspace
CMD ["conda", "run", "-n", "py", "bash"]