# omniparser-container

Public container builds for Microsoft OmniParser.

This repository builds OCI images for CPU and CUDA runtimes.

Recommended moving tags:

- `ghcr.io/rfaes-com/omniparser-container:cpu`
- `ghcr.io/rfaes-com/omniparser-container:cuda`

Architecture-specific moving tags:

- `ghcr.io/rfaes-com/omniparser-container:cpu-amd64`
- `ghcr.io/rfaes-com/omniparser-container:cpu-arm64`
- `ghcr.io/rfaes-com/omniparser-container:cuda-cu121-amd64`

Release builds publish both moving tags and versioned tags. For a repository tag such as `v1.2.3`, CI publishes:

- `ghcr.io/rfaes-com/omniparser-container:cpu-v1.2.3`
- `ghcr.io/rfaes-com/omniparser-container:cpu-amd64-v1.2.3`
- `ghcr.io/rfaes-com/omniparser-container:cpu-arm64-v1.2.3`
- `ghcr.io/rfaes-com/omniparser-container:cuda-v1.2.3`
- `ghcr.io/rfaes-com/omniparser-container:cuda-cu121-amd64-v1.2.3`

Every CI build also publishes commit-addressed tags such as `cpu-<git-sha>`, `cpu-amd64-<git-sha>`, `cpu-arm64-<git-sha>`, `cuda-<git-sha>`, and `cuda-cu121-amd64-<git-sha>`.

The CPU image is intended for both `linux/amd64` and `linux/arm64`.

The CUDA image is intended for `linux/amd64` NVIDIA GPU hosts.

## What this image contains

The image clones the upstream OmniParser repository at build time:

```text
https://github.com/microsoft/OmniParser.git
```

By default it uses:

```text
OMNIPARSER_REF=master
```

You can override this during build. For reproducible production images, pin `OMNIPARSER_REF` to an upstream commit SHA instead of using `master`.

## Model weights

OmniParser V2 weights are not baked into the image by default.

Download the weights on the host and mount them into the container at:

```text
/app/OmniParser/weights
```

With the helper image:

```bash
docker buildx build -f Dockerfile.weights -t localhost/omniparser-weights --load .

docker run --rm \
  -v "$(pwd)/weights:/weights" \
  localhost/omniparser-weights
```

Equivalent host command:

```bash
mkdir -p weights

for f in \
  icon_detect/train_args.yaml \
  icon_detect/model.pt \
  icon_detect/model.yaml \
  icon_caption/config.json \
  icon_caption/generation_config.json \
  icon_caption/model.safetensors
do
  hf download microsoft/OmniParser-v2.0 "$f" --local-dir weights
done

mv weights/icon_caption weights/icon_caption_florence
```

## Local CPU build

```bash
docker buildx build \
  --platform linux/amd64 \
  --build-arg FLAVOR=cpu \
  -t localhost/omniparser-container:cpu-amd64 \
  --load \
  .
```

ARM64:

```bash
docker buildx build \
  --platform linux/arm64 \
  --build-arg FLAVOR=cpu \
  -t localhost/omniparser-container:cpu-arm64 \
  --load \
  .
```

## Local CUDA build

```bash
docker buildx build \
  --platform linux/amd64 \
  --build-arg FLAVOR=cuda \
  -t localhost/omniparser-container:cuda-cu121-amd64 \
  --load \
  .
```

## Run CPU

```bash
mkdir -p weights model-cache/easyocr model-cache/paddleocr model-cache/huggingface model-cache/torch

docker run --rm -it \
  -p 7861:7861 \
  -v "$(pwd)/weights:/app/OmniParser/weights" \
  -v "$(pwd)/model-cache/easyocr:/root/.EasyOCR" \
  -v "$(pwd)/model-cache/paddleocr:/root/.paddleocr" \
  -v "$(pwd)/model-cache/huggingface:/models/huggingface" \
  -v "$(pwd)/model-cache/torch:/models/torch" \
  localhost/omniparser-container:cpu-amd64
```

## Run CUDA

The host needs NVIDIA drivers and NVIDIA Container Toolkit.

```bash
mkdir -p weights model-cache/easyocr model-cache/paddleocr model-cache/huggingface model-cache/torch

docker run --rm -it \
  --gpus all \
  --device nvidia.com/gpu=all \
  -p 7861:7861 \
  -v "$(pwd)/weights:/app/OmniParser/weights" \
  -v "$(pwd)/model-cache/easyocr:/root/.EasyOCR" \
  -v "$(pwd)/model-cache/paddleocr:/root/.paddleocr" \
  -v "$(pwd)/model-cache/huggingface:/models/huggingface" \
  -v "$(pwd)/model-cache/torch:/models/torch" \
  localhost/omniparser-container:cuda-cu121-amd64
```

Open:

```text
http://localhost:7861
```

## API

The server exposes a REST API on port **8000** (default). Interactive docs are available at:

```text
http://localhost:8000/docs
```

### `GET /health`

Returns the server status and the active compute device.

**Response**

```json
{
  "status": "ok",
  "device": "cpu"
}
```

`device` is `"cpu"` or `"cuda"`.

### `POST /parse`

Parse a screenshot. Accepts a `multipart/form-data` request.

**Request fields**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | file | yes | — | Screenshot to parse (PNG, JPEG, or any common raster format) |
| `box_threshold` | float (0–1) | no | `0.05` | Detection confidence threshold |
| `iou_threshold` | float (0–1) | no | `0.1` | IoU threshold for NMS deduplication |

**Response**

```json
{
  "image": "<base64-encoded annotated PNG>",
  "parsed_content_list": [
    "text: File",
    {
      "type": "icon",
      "content": "settings gear"
    }
  ],
  "label_coordinates": {
    "0": [0.12, 0.34, 0.18, 0.40],
    "1": [0.55, 0.02, 0.63, 0.06]
  }
}
```

| Field | Description |
|-------|-------------|
| `image` | Base64-encoded PNG with bounding-box annotations drawn on the original screenshot |
| `parsed_content_list` | Detected element descriptions. Depending on OmniParser version, items may be strings or structured dictionaries |
| `label_coordinates` | Label index → `[x1, y1, x2, y2]` in ratio coordinates (0–1) |

## Testing the API

Start the container (replace the image tag as needed):

```bash
docker run --rm -it \
  -p 8000:8000 \
  -v "$(pwd)/weights:/app/OmniParser/weights" \
  localhost/omniparser-container:cpu-amd64
```

**Health check**

```bash
curl http://localhost:8000/health
```

**Parse a screenshot with curl**

```bash
curl -X POST http://localhost:8000/parse \
  -F "image=@/path/to/screenshot.png" \
  -F "box_threshold=0.05" \
  -F "iou_threshold=0.1" \
  -o response.json
```

Decode the annotated image from the response:

```bash
python3 -c "
import json, base64
data = json.load(open('response.json'))
with open('annotated.png', 'wb') as f:
    f.write(base64.b64decode(data['image']))
print('Elements:')
for i, el in enumerate(data['parsed_content_list']):
    print(f'  [{i}] {el}')
"
```

**Parse a screenshot with Python**

```python
import base64
import requests

with open("screenshot.png", "rb") as f:
    response = requests.post(
        "http://localhost:8000/parse",
        files={"image": ("screenshot.png", f, "image/png")},
        data={"box_threshold": 0.05, "iou_threshold": 0.1},
    )

response.raise_for_status()
result = response.json()

# Save annotated image
with open("annotated.png", "wb") as f:
    f.write(base64.b64decode(result["image"]))

# Print detected elements
for i, element in enumerate(result["parsed_content_list"]):
    coords = result["label_coordinates"][str(i)]
    print(f"[{i}] {element}  coords={coords}")
```

## Development container

This repository includes a devcontainer for build and release tooling. It uses the host Docker engine through the Docker-outside-of-Docker devcontainer feature and includes GitHub CLI, ShellCheck, and Hadolint.

## Notes

CUDA images are AMD64 only.

CPU ARM64 works for container compatibility, but performance depends heavily on the host CPU and Python package wheel availability.

Runtime Python dependencies are intentionally installed from the current package indexes at image build time. Use versioned image tags or commit-addressed image tags when you need to roll deployments forward deliberately.
