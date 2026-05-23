#!/bin/bash
# OmniParser container entrypoint.
# Performs pre-flight checks before handing off to uvicorn so that startup
# failures produce a clear, actionable error message instead of a silent exit.

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() { echo -e "${RED}[entrypoint] ERROR: $*${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}[entrypoint] WARNING: $*${NC}" >&2; }
info() { echo "[entrypoint] $*"; }

# ---------------------------------------------------------------------------
# 1. GPU / CUDA diagnostics
# ---------------------------------------------------------------------------
info "---- GPU diagnostics ----"
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free \
               --format=csv,noheader 2>/dev/null \
      || warn "nvidia-smi query failed — driver may be unavailable"
else
    warn "nvidia-smi not found — running without NVIDIA GPU support"
fi

# ---------------------------------------------------------------------------
# 2. Weights pre-flight check
# ---------------------------------------------------------------------------
WEIGHTS_DIR="${OMNI_WEIGHTS_DIR:-weights}"
YOLO_MODEL_FILE="${OMNI_YOLO_MODEL_FILE:-model.pt}"
CAPTION_MODEL="${OMNI_CAPTION_MODEL:-florence2}"

case "$CAPTION_MODEL" in
    florence2) CAPTION_DIR="icon_caption_florence" ;;
    blip2)     CAPTION_DIR="icon_caption_blip2" ;;
    *)         CAPTION_DIR="icon_caption_${CAPTION_MODEL}" ;;
esac

YOLO_PATH="${WEIGHTS_DIR}/icon_detect/${YOLO_MODEL_FILE}"
CAPTION_PATH="${WEIGHTS_DIR}/${CAPTION_DIR}"

info "---- Weights check ----"
info "  YOLO model    : ${YOLO_PATH}"
info "  Caption model : ${CAPTION_PATH}"

[ -f "$YOLO_PATH" ]   || fail "YOLO model not found at '${YOLO_PATH}'. Mount your weights with -v <host-path>/weights:/app/OmniParser/weights"
[ -d "$CAPTION_PATH" ] || fail "Caption model directory not found at '${CAPTION_PATH}'. Mount your weights with -v <host-path>/weights:/app/OmniParser/weights"

info "Weights check passed."
info "---- Starting uvicorn ----"

# exec replaces the shell so uvicorn receives signals (SIGTERM) directly.
exec uvicorn server:app \
    --host  "${OMNI_HOST:-0.0.0.0}" \
    --port  "${OMNI_PORT:-8000}" \
    --log-level info
