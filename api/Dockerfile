# =============================================================================
# Radar ENEM — imagem da API de analise (Req 7.1, 7.3)
#
# Empacota o pacote `radar_api` (FastAPI + uvicorn + DuckDB) de forma
# INDEPENDENTE da imagem do frontend (`web/Dockerfile`).
#
# Contexto de build: o diretorio `api/` (nao a raiz do repositorio).
#
#   docker build -t radar-api:dev api/
#   docker run --rm -p 8000:8000 \
#     -v /caminho/para/data/silver:/data/silver:ro \
#     -e RADAR_AMBIENTE_REFERENCIA=prod-ref \
#     radar-api:dev
#
# -----------------------------------------------------------------------------
# NENHUM DADO EMBUTIDO (Req 7.3)
# -----------------------------------------------------------------------------
# A Camada_Silver e um contrato de entrada EXTERNO: os Parquet (hive-partitioned)
# NAO sao copiados para a imagem — sao montados em runtime (volume, bind mount ou
# bucket montado) e `RADAR_SILVER_ROOT` aponta para o ponto de montagem. Assim os
# dados podem ser atualizados sem reconstruir a imagem, e a imagem permanece
# pequena e livre de dados pessoais/derivados.
#
# Montagens esperadas:
#   /data/silver      (RADAR_SILVER_ROOT)      obrigatoria em producao, read-only
#   /data/manifestos  (RADAR_MANIFESTOS_ROOT)  opcional; padrao = silver_root
#   /data/ml/modelo.*  (RADAR_ML_ARTEFATO)     opcional, so com ML habilitado
#
# O diretorio `/data/silver` NAO e pre-criado de proposito: sem a montagem, o
# `/health` responde 503 (readiness vermelha) em vez de fingir uma silver vazia.
#
# -----------------------------------------------------------------------------
# Configuracao exclusivamente por variaveis de ambiente (Req 7.1)
# -----------------------------------------------------------------------------
#   RADAR_SILVER_ROOT        raiz da camada silver (Parquet particionado)
#   RADAR_MANIFESTOS_ROOT    raiz dos manifestos (padrao: = RADAR_SILVER_ROOT)
#   RADAR_LIMIAR_AGREGACAO   limiar de k-anonimato (padrao 25 — Req 1.6/9.3)
#   RADAR_ML_HABILITADO      habilita o Modelo_ML opcional (padrao false — Req 8.1)
#   RADAR_ML_ARTEFATO        caminho do artefato do Modelo_ML (opcional)
#   RADAR_TIMEOUT_CONSULTA_S timeout de consulta em segundos (padrao 30 — Req 6.3)
#   RADAR_AMBIENTE_REFERENCIA rotulo do ambiente de referencia (Req 6.3)
#   PORT                     porta HTTP do uvicorn (padrao 8000)
#
# Os defaults abaixo replicam os de `radar_api.config.Config`, exceto
# `RADAR_SILVER_ROOT`, que aqui aponta para o ponto de montagem do contêiner.
# Nenhum segredo e necessario (a API nao usa credenciais).
# =============================================================================

# -----------------------------------------------------------------------------
# Estagio 1 — builder: resolve dependencias e instala o pacote num venv isolado.
# Todo o ferramental de build (pip, setuptools, hatchling, caches) fica AQUI e
# nao chega a imagem final.
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# venv relocavel copiado inteiro para o estagio final.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# src-layout: `pyproject.toml` declara `packages = ["src/radar_api"]` (hatchling).
# Copiamos apenas o necessario para construir o wheel.
COPY pyproject.toml ./
COPY src ./src

# Instala SOMENTE as dependencias de runtime declaradas em [project.dependencies]
# (duckdb, fastapi, pydantic, pydantic-settings, uvicorn[standard]).
# O extra `dev` (ruff/pytest/hypothesis/httpx) NAO e instalado — a imagem de
# producao nao carrega ferramentas de teste/lint.
# Wheels manylinux cobrem duckdb e os extras do uvicorn em cp312; nao instalamos
# toolchain de compilacao — falta de wheel falha o build de forma explicita.
RUN pip install --no-cache-dir . \
    && python -c "import radar_api.app"

# -----------------------------------------------------------------------------
# Estagio 2 — runtime: mesma familia de base (Python 3.12 slim), apenas o venv.
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="radar-enem-api" \
      org.opencontainers.image.description="API de analise estatistica agregada do ENEM (camada silver)" \
      org.opencontainers.image.source="https://github.com/StartINEP/ENEM-em-Foco" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Defaults seguros de configuracao (todos sobrescreviveis por -e / env do orquestrador).
ENV RADAR_SILVER_ROOT=/data/silver \
    RADAR_LIMIAR_AGREGACAO=25 \
    RADAR_ML_HABILITADO=false \
    RADAR_TIMEOUT_CONSULTA_S=30 \
    RADAR_AMBIENTE_REFERENCIA=container \
    PORT=8000

# Usuario NAO-root dedicado (uid/gid fixos, sem shell de login, sem senha).
# Nada no contêiner precisa de root: a silver e montada read-only e o processo
# apenas le arquivos e escuta uma porta > 1024. Isso limita o impacto de uma
# eventual falha de seguranca no processo da API.
RUN groupadd --system --gid 1001 radar \
    && useradd --system --uid 1001 --gid 1001 \
        --home-dir /app --no-create-home --shell /usr/sbin/nologin radar \
    && mkdir -p /app \
    && chown radar:radar /app

# Unico artefato trazido do builder: o venv com radar_api + deps de runtime.
COPY --from=builder /opt/venv /opt/venv

# /app e um cwd vazio e legivel; serve tambem como local opcional para um `.env`
# montado (pydantic-settings le `.env` do diretorio de trabalho).
WORKDIR /app

USER radar

EXPOSE 8000

# -----------------------------------------------------------------------------
# HEALTHCHECK — semantica de LIVENESS (deliberada)
# -----------------------------------------------------------------------------
# `GET /health` distingue dois estados:
#   200 -> silver acessivel  (readiness verde)
#   503 -> silver inacessivel (readiness vermelha; o PROCESSO esta vivo)
#
# O healthcheck do Docker e consumido por politicas de restart/substituicao de
# contêiner, e reiniciar o processo NAO conserta uma montagem ausente. Portanto
# ele trata 200 e 503 como *healthy* e so marca *unhealthy* quando o HTTP nem
# responde (processo travado/morto). A distincao 200/503 deve ser usada pela
# READINESS probe do orquestrador (ex.: readinessProbe httpGet /health), que
# tira o contêiner do balanceador sem mata-lo enquanto a silver nao esta la.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,sys,http.client as h; c=h.HTTPConnection('127.0.0.1', int(os.environ.get('PORT','8000')), timeout=4); c.request('GET','/health'); sys.exit(0 if c.getresponse().status in (200,503) else 1)"]

# Entrypoint: uvicorn servindo o ASGI app de modulo `radar_api.app:app`.
# `sh -c ... exec` apenas expande ${PORT} e depois substitui o shell, para que o
# uvicorn continue sendo o PID 1 e receba SIGTERM/SIGINT do orquestrador.
# Variaveis `UVICORN_*` (ex.: UVICORN_LOG_LEVEL) tambem sao honradas pelo CLI.
CMD ["sh", "-c", "exec uvicorn radar_api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
