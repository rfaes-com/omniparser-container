FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG HADOLINT_VERSION=2.12.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        httpie \
        jq \
        make \
        shellcheck \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) hadolint_arch="x86_64" ;; \
      arm64) hadolint_arch="arm64" ;; \
      *) echo "Unsupported architecture for hadolint" >&2; exit 1 ;; \
    esac; \
    curl -fsSL \
      -o /usr/local/bin/hadolint \
      "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-Linux-${hadolint_arch}"; \
    chmod +x /usr/local/bin/hadolint
