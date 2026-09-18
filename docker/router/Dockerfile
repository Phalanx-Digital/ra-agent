FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY aura_link aura_link
COPY router router
COPY configs configs
RUN pip install --no-cache-dir .
USER 65532:65532
ENTRYPOINT ["python", "-m", "router.gateway", "--config", "configs/router.yaml"]

