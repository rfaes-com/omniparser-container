# syntax=docker/dockerfile:1.7

ARG FLAVOR=cpu
ARG PYTHON_VERSION=3.12
ARG OMNIPARSER_REPO=https://github.com/microsoft/OmniParser.git
ARG OMNIPARSER_REF=master

FROM python:${PYTHON_VERSION}-slim AS cpu-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    TORCH_HOME=/models/torch

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    libgl1 libglib2.0-0 libgomp1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS cuda-base

ARG PYTHON_VERSION=3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    TORCH_HOME=/models/torch \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git curl ca-certificates \
    libgl1 libglib2.0-0 libgomp1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

FROM ${FLAVOR}-base AS runtime

ARG FLAVOR=cpu
ARG OMNIPARSER_REPO
ARG OMNIPARSER_REF
ARG TORCH_CPU_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_CUDA_INDEX=https://download.pytorch.org/whl/cu121

WORKDIR /app

COPY requirements.common.txt /opt/omniparser-container/requirements.common.txt
COPY requirements.cpu.txt /opt/omniparser-container/requirements.cpu.txt
COPY requirements.cuda.txt /opt/omniparser-container/requirements.cuda.txt

RUN python3 -m pip install --upgrade pip setuptools wheel

RUN if [ "$FLAVOR" = "cuda" ]; then \
      python3 -m pip install torch torchvision --index-url "${TORCH_CUDA_INDEX}"; \
    else \
      python3 -m pip install torch torchvision --index-url "${TORCH_CPU_INDEX}"; \
    fi \
    && find /usr/local/lib/python3.10/dist-packages \
      \( -type d -name __pycache__ -o -type d -name tests -o -type d -name test \) \
      -prune -exec rm -rf '{}' + \
    && rm -rf /root/.cache /tmp/*

RUN python3 -m pip install -r /opt/omniparser-container/requirements.common.txt \
    && find /usr/local/lib/python3.10/dist-packages \
      \( -type d -name __pycache__ -o -type d -name tests -o -type d -name test \) \
      -prune -exec rm -rf '{}' + \
    && rm -rf /root/.cache /tmp/*

RUN if [ "$FLAVOR" = "cuda" ]; then \
      python3 -m pip install -r /opt/omniparser-container/requirements.cuda.txt; \
    else \
      python3 -m pip install -r /opt/omniparser-container/requirements.cpu.txt; \
    fi \
    && find /usr/local/lib/python3.10/dist-packages \
      \( -type d -name __pycache__ -o -type d -name tests -o -type d -name test \) \
      -prune -exec rm -rf '{}' + \
    && rm -rf /root/.cache /tmp/*

RUN git clone --depth 1 --branch "${OMNIPARSER_REF}" "${OMNIPARSER_REPO}" /app/OmniParser

WORKDIR /app/OmniParser

RUN python3 - <<'PY'
from pathlib import Path

path = Path("gradio_demo.py")
text = path.read_text()
old = "demo.launch(share=True, server_port=7861, server_name='127.0.0.1')"
new = "demo.launch(share=False, server_port=7861, server_name='0.0.0.0')"
if old not in text:
    raise SystemExit(f"Expected Gradio launch line not found in {path}")
path.write_text(text.replace(old, new))
PY

RUN mkdir -p weights

EXPOSE 7861

CMD ["python3", "gradio_demo.py"]
