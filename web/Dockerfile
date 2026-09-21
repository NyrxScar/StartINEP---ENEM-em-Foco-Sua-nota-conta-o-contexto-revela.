# syntax=docker/dockerfile:1

# ============================================================================
# Imagem do frontend do Radar ENEM (Vite + React), Req 7.1.
#
# Empacotada de forma **independente** da imagem da API: nada de Python,
# `radar_api` ou da camada silver entra aqui. O frontend so conhece a API pela
# URL base HTTP.
#
# Build (raiz do repositorio):
#     docker build -t radar-web:dev web/
#     docker build -t radar-web:prod --build-arg VITE_API_URL=https://api.exemplo.org web/
#
# Execucao:
#     docker run --rm -p 8080:8080 radar-web:dev
#
# ---------------------------------------------------------------------------
# DECISAO: `VITE_API_URL` e um ARG de **build**, nao de runtime.
#
# `web/lib/api.ts` le `import.meta.env.VITE_API_URL`, e a chamada acontece no
# navegador. O Vite **substitui literalmente** qualquer `VITE_*` no bundle em
# tempo de `vite build`; definir a variavel apenas em `docker run` NAO alteraria
# o JavaScript ja compilado que roda no cliente.
#
# Consequencia operacional: a imagem e **especifica do ambiente**. Trocar a URL
# da API exige **reconstruir** com outro `--build-arg`. Na pratica, uma imagem
# por ambiente (dev/homolog/prod), com a URL como parte da tag.
#
# Alternativa considerada e nao adotada: servir um `config.json` ao lado do
# index e busca-lo no boot da aplicacao — uma unica imagem serviria todos os
# ambientes, ao custo de um ida-e-volta antes da primeira requisicao util e de
# uma segunda fonte de configuracao para manter. Com uma imagem por ambiente ja
# no pipeline, o ganho nao paga a complexidade.
#
# O default abaixo aponta para o uvicorn local: e um valor de desenvolvimento,
# nao ha URL de producao nem segredo embutido na imagem.
# ============================================================================

ARG NODE_VERSION=22.13.0-alpine3.21
ARG NGINX_VERSION=1.27-alpine

# ---------------------------------------------------------------------------
# Estagio 1 — deps: instala dependencias a partir do lockfile.
# Isolado para que o cache so seja invalidado quando package*.json mudarem.
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS deps

WORKDIR /app

# `npm ci` (e nao `npm install`): respeita exatamente o package-lock.json,
# tornando o build reproduzivel.
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# Estagio 2 — builder: typecheck + `vite build`.
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json vite.config.ts tsconfig.json index.html styles.css ./
COPY main.tsx App.tsx ./
COPY components ./components
COPY lib ./lib
COPY pages ./pages
COPY public ./public

# Substituido literalmente no bundle aqui — ver a DECISAO no topo do arquivo.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
ENV NODE_ENV=production

# `npm run build` roda `tsc --noEmit && vite build`: um erro de tipo falha a
# imagem em vez de produzir um bundle quebrado.
RUN npm run build

# ---------------------------------------------------------------------------
# Estagio 3 — runner: nginx servindo arquivos estaticos.
#
# O build do Vite e HTML/CSS/JS puro: nao ha processo Node em producao, nenhum
# `node_modules`, nenhum codigo-fonte TypeScript e nenhuma dependencia de
# desenvolvimento na imagem final — apenas o conteudo de `dist/`.
#
# A variante `nginx-unprivileged` ja roda como usuario nao-root na porta 8080,
# sem precisar remendar permissoes nem o arquivo de PID.
# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:${NGINX_VERSION} AS runner

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

# Health-check com o wget do BusyBox, ja presente na imagem alpine.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
