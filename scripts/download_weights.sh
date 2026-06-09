#!/usr/bin/env bash
set -euo pipefail

MODEL_REPO="${MODEL_REPO:-microsoft/OmniParser-v2.0}"
MODEL_REVISION="${MODEL_REVISION:-main}"
TARGET_DIR="${TARGET_DIR:-/weights}"
EASYOCR_TARGET_DIR="${EASYOCR_TARGET_DIR:-/weights-easyocr}"

mkdir -p "${TARGET_DIR}"

echo "Downloading OmniParser weights"
echo "MODEL_REPO=${MODEL_REPO}"
echo "MODEL_REVISION=${MODEL_REVISION}"
echo "TARGET_DIR=${TARGET_DIR}"

for file in \
  icon_detect/train_args.yaml \
  icon_detect/model.pt \
  icon_detect/model.yaml \
  icon_caption/config.json \
  icon_caption/generation_config.json \
  icon_caption/model.safetensors
do
  hf download "${MODEL_REPO}" "${file}" \
    --revision "${MODEL_REVISION}" \
    --local-dir "${TARGET_DIR}"
done

if [ -d "${TARGET_DIR}/icon_caption" ] && [ ! -d "${TARGET_DIR}/icon_caption_florence" ]; then
  mv "${TARGET_DIR}/icon_caption" "${TARGET_DIR}/icon_caption_florence"
fi

echo "Weights ready in ${TARGET_DIR}"

# ---------------------------------------------------------------------------
# EasyOCR models
# ---------------------------------------------------------------------------
echo "Downloading EasyOCR models"
echo "EASYOCR_TARGET_DIR=${EASYOCR_TARGET_DIR}"

mkdir -p "${EASYOCR_TARGET_DIR}"

EASYOCR_MODULE_PATH="${EASYOCR_TARGET_DIR}" python - <<'PYEOF'
import easyocr
import os

target = os.environ["EASYOCR_MODULE_PATH"]
print(f"EasyOCR model_storage_directory → {target}/model")
# Initialising the Reader triggers model download; disable GPU to avoid
# requiring CUDA in the weights init container.
easyocr.Reader(["en"], gpu=False)
print("EasyOCR models ready.")
PYEOF

echo "EasyOCR models ready in ${EASYOCR_TARGET_DIR}"
