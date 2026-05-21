"""OmniParser FastAPI inference server.

Environment variables (all optional, defaults shown):

  OMNI_MAX_CONCURRENCY   Max simultaneous in-flight inference jobs.
                          -1 = unlimited (default). Positive integer queues
                          excess requests until a slot is free.

  OMNI_BOX_THRESHOLD     Default detection confidence threshold (0.05).
                          Overridable per request.

  OMNI_IOU_THRESHOLD     Default IoU threshold for NMS (0.1).
                          Overridable per request.

  OMNI_USE_PADDLEOCR     Use PaddleOCR instead of EasyOCR ("true").

  OMNI_TEXT_THRESHOLD    OCR text confidence threshold (0.9).

  OMNI_CAPTION_MODEL     Caption model: florence2 | blip2 ("florence2").

  OMNI_WEIGHTS_DIR       Path to the weights directory ("weights").

  OMNI_YOLO_MODEL_FILE   YOLO weights filename under icon_detect/ ("model.pt").

  OMNI_HOST              Bind host ("0.0.0.0").

  OMNI_PORT              Bind port (8000).
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

# Ensure OmniParser's utils module (utils.py, etc.) is importable regardless
# of working directory or how uvicorn is invoked.
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field
from util.utils import (  # type: ignore[import-not-found]
    check_ocr_box,
    get_caption_model_processor,
    get_som_labeled_img,
    get_yolo_model,
)

# ---------------------------------------------------------------------------
# Configuration (read once at import time)
# ---------------------------------------------------------------------------

MAX_CONCURRENCY: int = int(os.environ.get("OMNI_MAX_CONCURRENCY", "-1"))
DEFAULT_BOX_THRESHOLD: float = float(os.environ.get("OMNI_BOX_THRESHOLD", "0.05"))
DEFAULT_IOU_THRESHOLD: float = float(os.environ.get("OMNI_IOU_THRESHOLD", "0.1"))
USE_PADDLEOCR: bool = os.environ.get("OMNI_USE_PADDLEOCR", "true").lower() == "true"
TEXT_THRESHOLD: float = float(os.environ.get("OMNI_TEXT_THRESHOLD", "0.9"))
CAPTION_MODEL: str = os.environ.get("OMNI_CAPTION_MODEL", "florence2")
WEIGHTS_DIR: str = os.environ.get("OMNI_WEIGHTS_DIR", "weights")
YOLO_MODEL_FILE: str = os.environ.get("OMNI_YOLO_MODEL_FILE", "model.pt")

# Caption model directory name mapping:
#   florence2 → weights/icon_caption_florence
#   blip2     → weights/icon_caption_blip2
_CAPTION_DIR_MAP: dict[str, str] = {
    "florence2": "icon_caption_florence",
    "blip2": "icon_caption_blip2",
}
CAPTION_MODEL_PATH: str = os.path.join(
    WEIGHTS_DIR,
    _CAPTION_DIR_MAP.get(CAPTION_MODEL, f"icon_caption_{CAPTION_MODEL}"),
)
YOLO_MODEL_PATH: str = os.path.join(WEIGHTS_DIR, "icon_detect", YOLO_MODEL_FILE)

# ---------------------------------------------------------------------------
# Module-level state (populated during lifespan startup)
# ---------------------------------------------------------------------------

_yolo_model = None
_caption_model_processor: dict | None = None
_semaphore: asyncio.Semaphore | None = None
_executor: ThreadPoolExecutor | None = None
_device: str = "cpu"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _yolo_model, _caption_model_processor, _semaphore, _executor, _device

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[startup] device={_device}  caption_model={CAPTION_MODEL}")

    _yolo_model = get_yolo_model(model_path=YOLO_MODEL_PATH)
    if _device == "cuda":
        _yolo_model.to("cuda")

    _caption_model_processor = get_caption_model_processor(
        model_name=CAPTION_MODEL,
        model_name_or_path=CAPTION_MODEL_PATH,
        device=_device,
    )

    _semaphore = asyncio.Semaphore(MAX_CONCURRENCY) if MAX_CONCURRENCY > 0 else None
    _executor = ThreadPoolExecutor(
        max_workers=None if MAX_CONCURRENCY < 1 else MAX_CONCURRENCY
    )

    print("[startup] models loaded — server ready")
    yield

    if _executor:
        _executor.shutdown(wait=True)
    print("[shutdown] done")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OmniParser API",
    description=(
        "Screen parsing via YOLO detection + Florence2/BLIP2 captioning. "
        "POST a screenshot to /parse and receive annotated image + element list."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ParseResponse(BaseModel):
    image: str = Field(description="Base64-encoded annotated PNG")
    parsed_content_list: list[str] = Field(
        description="Human-readable description for each detected element"
    )
    label_coordinates: dict = Field(
        description="Label index → [x1, y1, x2, y2] in ratio coordinates"
    )


# ---------------------------------------------------------------------------
# Blocking inference helper (runs in thread-pool executor)
# ---------------------------------------------------------------------------


def _run_inference(
    image: Image.Image,
    box_threshold: float,
    iou_threshold: float,
) -> ParseResponse:
    """Run OmniParser inference synchronously (called from thread pool)."""
    # Each concurrent call gets its own temp file to avoid race conditions.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        image.save(tmp_path)

        box_overlay_ratio = max(image.size) / 3200
        draw_bbox_config = {
            "text_scale": 0.8 * box_overlay_ratio,
            "text_thickness": max(int(2 * box_overlay_ratio), 1),
            "text_padding": max(int(3 * box_overlay_ratio), 1),
            "thickness": max(int(3 * box_overlay_ratio), 1),
        }

        ocr_bbox_rslt, _ = check_ocr_box(
            tmp_path,
            display_img=False,
            output_bb_format="xyxy",
            goal_filtering=None,
            easyocr_args={"paragraph": False, "text_threshold": TEXT_THRESHOLD},
            use_paddleocr=USE_PADDLEOCR,
        )
        text, ocr_bbox = ocr_bbox_rslt

        dino_labeled_img, label_coordinates, parsed_content_list = get_som_labeled_img(
            tmp_path,
            _yolo_model,
            BOX_TRESHOLD=box_threshold,
            output_coord_in_ratio=True,
            ocr_bbox=ocr_bbox,
            draw_bbox_config=draw_bbox_config,
            caption_model_processor=_caption_model_processor,
            ocr_text=text,
            iou_threshold=iou_threshold,
        )

        annotated = Image.open(io.BytesIO(base64.b64decode(dino_labeled_img)))
        buf = io.BytesIO()
        annotated.save(buf, format="PNG")

        return ParseResponse(
            image=base64.b64encode(buf.getvalue()).decode(),
            parsed_content_list=list(parsed_content_list),
            label_coordinates=label_coordinates,
        )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/parse", response_model=ParseResponse, summary="Parse a screenshot")
async def parse_image(
    image: Annotated[UploadFile, File(description="Screenshot to parse (any common raster format)")],
    box_threshold: Annotated[
        float,
        Form(ge=0.0, le=1.0, description="Detection confidence threshold"),
    ] = DEFAULT_BOX_THRESHOLD,
    iou_threshold: Annotated[
        float,
        Form(ge=0.0, le=1.0, description="IoU threshold for NMS deduplication"),
    ] = DEFAULT_IOU_THRESHOLD,
) -> ParseResponse:
    try:
        data = await image.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc

    loop = asyncio.get_event_loop()

    async def _infer() -> ParseResponse:
        try:
            return await loop.run_in_executor(
                _executor, _run_inference, img, box_threshold, iou_threshold
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if _semaphore is not None:
        async with _semaphore:
            return await _infer()
    return await _infer()


@app.get("/health", summary="Health check")
async def health() -> dict:
    return {"status": "ok", "device": _device}


# ---------------------------------------------------------------------------
# Entry point (local dev: python server.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("OMNI_HOST", "0.0.0.0"),
        port=int(os.environ.get("OMNI_PORT", "8000")),
    )
