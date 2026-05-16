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
  -t omniparser-container:cpu-amd64 \
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

## Development container

This repository includes a devcontainer for build and release tooling. It uses the host Docker engine through the Docker-outside-of-Docker devcontainer feature and includes GitHub CLI, ShellCheck, and Hadolint.

## Notes

CUDA images are AMD64 only.

CPU ARM64 works for container compatibility, but performance depends heavily on the host CPU and Python package wheel availability.

Runtime Python dependencies are intentionally installed from the current package indexes at image build time. Use versioned image tags or commit-addressed image tags when you need to roll deployments forward deliberately.
