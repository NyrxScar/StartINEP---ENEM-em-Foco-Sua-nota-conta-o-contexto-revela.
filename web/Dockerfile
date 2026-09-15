# syntax=docker/dockerfile:1

# ============================================================================
# Imagem do frontend Next.js do Radar ENEM (Req 7.1).
#
# Empacotada de forma **independente** da imagem da API: nada de Python,
# `radar_api` ou da camada silver entra aqui. O frontend so conhece a API pela
# URL base HTTP.
#
# Build (raiz do repositorio):
#     docker build -t radar-web:dev web/
#     docker build -t radar-web:prod --build-arg NEXT_PUBLIC_API_URL=https://api.exemplo.org web/
#
# Execucao:
#     docker run --rm -p 3000:3000 radar-web:dev
#     docker run --rm -p 8080:8080 -e PORT=8080 radar-web:dev
#
# ---------------------------------------------------------------------------
# DECISAO: `NEXT_PUBLIC_API_URL` e um ARG de **build**, nao de runtime.
#
# `web/lib/api.ts` le `process.env.NEXT_PUBLIC_API_URL`, e `PainelAnalise` /
# `FormularioAnalise` sao Client Components — ou seja, a chamada acontece no
# navegador. O Next **inlineia** qualquer `NEXT_PUBLIC_*` no bundle do cliente
# em tempo de `next build`; definir a variavel apenas em `docker run` NAO
# alteraria o codigo ja compilado que roda no browser.
#
# Consequencia operacional: a imagem e **especifica do ambiente**. Trocar a URL
# da API exige **reconstruir** a imagem com outro `--build-arg`. Na pratica,
# uma imagem por ambiente (dev/homolog/prod), com a URL como parte da tag.
#
# Alternativa considerada e descartada nesta task: mover a chamada para o
# servidor (Server Component ou rota `app/api/*` como proxy) e ler a URL do
# ambiente do processo — ai a variavel passaria a ser de runtime e uma unica
# imagem serviria todos os ambientes. Isso mudaria `web/lib/api.ts` e os
# componentes (fora do escopo desta task, que so empacota o que existe).
#
# O default abaixo aponta para o uvicorn local: e um valor de desenvolvimento,
# nao ha URL de producao nem segredo embutido na imagem.
# ============================================================================

ARG NODE_VERSION=22.13.0-alpine3.21

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
# Estagio 2 — builder: `next build` com `output: 'standalone'`.
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json next.config.ts tsconfig.json next-env.d.ts .eslintrc.json ./
COPY app ./app
COPY components ./components
COPY lib ./lib

# `public/` ainda nao existe no projeto; criado vazio para que o COPY do
# estagio de runtime seja estavel se/quando assets estaticos forem adicionados.
RUN mkdir -p public

# Inlineado no bundle do cliente aqui — ver a DECISAO no topo do arquivo.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# ---------------------------------------------------------------------------
# Estagio 3 — runner: imagem final enxuta.
#
# Recebe apenas o servidor standalone (com o subconjunto de node_modules que o
# tracing do Next considerou alcancavel), os assets estaticos e `public/`.
# Nao ha `npm`, codigo-fonte TypeScript, dependencias de desenvolvimento nem
# lockfile na imagem final.
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Porta configuravel; o servidor standalone le PORT e HOSTNAME do ambiente.
# HOSTNAME=0.0.0.0 e obrigatorio: em 127.0.0.1 o processo ficaria inalcancavel
# de fora do contêiner.
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Nao rodamos como root. A imagem oficial do Node ja traz o usuario `node`
# (uid/gid 1000); os arquivos copiados pertencem a ele.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node

EXPOSE 3000

# Health-check sem dependencias extras: `fetch` global do Node 22, nenhum
# curl/wget instalado. Usa a PORT efetiva do contêiner.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:' + (process.env.PORT || 3000) + '/').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
