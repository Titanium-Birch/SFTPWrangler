ARG FUNCTION_DIR="/opt/function"

# Stage 1: Builder
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS builder

COPY layers/appconfig-extension.zip appconfig-extension.zip

RUN apt-get update && \
    apt-get -y install --no-install-recommends unzip && \
    unzip appconfig-extension.zip -d /opt && \
    rm -f appconfig-extension.zip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Stage 2: Final Image
FROM --platform=linux/amd64 python:3.12-slim-bookworm

ARG FUNCTION_DIR

RUN apt-get update && \
    apt-get -y install --no-install-recommends gnupg2 curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

RUN mkdir -p ${FUNCTION_DIR}

COPY src/requirements.txt ${FUNCTION_DIR}

WORKDIR ${FUNCTION_DIR}

RUN /root/.local/bin/uv pip install --system --no-cache -r requirements.txt && \
    /root/.local/bin/uv pip install --system --no-cache boto3 awslambdaric

COPY src/ ${FUNCTION_DIR}

COPY --from=builder /opt /opt

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
