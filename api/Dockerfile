# Contexto de build e a RAIZ do repositorio, nao api/:
#   docker build -f api/Dockerfile -t radar-enem-api .
# A camada Prata precisa entrar na imagem, e ela vive fora de api/.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencias antes do codigo: o cache so invalida quando o lock muda.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api/src ./src

# Parquet assado na imagem. Sao ~52 MB para 13 milhoes de linhas -- cabe, e a leitura
# vira disco local em vez de rede. Trocar por download do object storage so se a
# imagem estourar o limite da plataforma.
COPY data/silver ./data/silver
ENV RADAR_PRATA=/app/data/silver

# 7860 e a porta que o Hugging Face Spaces expoe por padrao.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uv run --no-dev uvicorn radar_api.main:app --host 0.0.0.0 --port ${PORT}"]
