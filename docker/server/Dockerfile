FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY aura_link aura_link
COPY server server
RUN python3 -m pip install --no-cache-dir '.[server]'
USER 10001:10001
ENTRYPOINT ["python3", "-m", "server.inference_pipeline", "--config", "server/config.yaml"]

