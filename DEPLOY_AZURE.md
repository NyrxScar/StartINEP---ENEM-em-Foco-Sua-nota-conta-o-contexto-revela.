> ## ✅ DEPLOY REALIZADO (atualizado)
> O sistema já está no ar no Azure (assinatura *Azure for Students*, região `southafricanorth`):
> - **Site:** https://radar-web.kindbeach-0c4857e4.southafricanorth.azurecontainerapps.io
> - **API:** https://radar-api.kindbeach-0c4857e4.southafricanorth.azurecontainerapps.io
> - **API docs:** a mesma URL da API + `/docs`
>
> O plano estudante tem restrições que mudaram o caminho em relação ao tutorial
> original abaixo. O que mudou na prática está em **"Notas do deploy real
> (Azure for Students)"**, logo após esta caixa. Para *refazer ou atualizar* o
> deploy, veja a seção **"Como atualizar / refazer"** no fim.

---

## Notas do deploy real (Azure for Students)

Três limites/bugs apareceram e foram resolvidos assim:

1. **`az acr build` é bloqueado** no plano estudante (`TasksOperationsNotAllowed`).
   → As imagens foram **buildadas localmente com Docker** e enviadas com `docker push`.
   (O `docker login` local usava o credential store `pass` quebrado; contornado
   com uma config isolada em `DOCKER_CONFIG=$PWD/.docker-deploy`.)

2. **O ambiente do Container Apps criado é "express"** e **não suporta montar
   Azure Files** (`ExpressEnvironmentResourceNotSupported`).
   → Em vez do File Share, a camada **silver (167 MB) foi embutida na imagem** da
   API, via `api/Dockerfile.comdados` + um `.dockerignore` na raiz que deixa
   passar só `data/silver`. O Storage/File Share criado no Passo 3 acabou **não
   sendo usado** (pode ser apagado para economizar).

3. **Bug real do projeto, exposto pelo deploy:** `pyproject.toml` fixava
   `duckdb>=1.1`, o que no build puxou **DuckDB 2.0**, que **removeu
   `Relation.fetchone()`** — usado em `catalogo.py`. Resultado: `/health` passava
   mas `/v1/edicoes` dava **500**. Corrigido fixando `duckdb>=1.1,<2` em
   `api/pyproject.toml` (série 1.x, a mesma do ambiente local).

Arquivos novos/alterados por este deploy:
`api/pyproject.toml`, `api/Dockerfile.comdados`, `.dockerignore`,
`.azure-deploy-vars.sh` (variáveis + chave do storage, no `.gitignore`).

### Imagens finais no ACR `radarenem2026.azurecr.io`
- `radar-api:v2` — API base (sem dados)
- `radar-api-comdados:v2` — API **com a silver embutida** (é a que roda)
- `radar-web:v1` — frontend (com `VITE_API_URL` da API embutido)

### Como atualizar / refazer
As variáveis do deploy estão em `.azure-deploy-vars.sh`. Carregue com
`source .azure-deploy-vars.sh` e use o fluxo abaixo (build local + push, porque
`az acr build` é bloqueado):

```bash
source .azure-deploy-vars.sh
export DOCKER_CONFIG="$PWD/.docker-deploy"
ACR_SERVER=$(az acr show -n "$ACR" --query loginServer -o tsv)

# --- API (com dados embutidos) ---
docker build -t "$ACR_SERVER/radar-api:v3" -f api/Dockerfile api/
docker build --build-arg BASE_IMAGE="$ACR_SERVER/radar-api:v3" \
  -t "$ACR_SERVER/radar-api-comdados:v3" -f api/Dockerfile.comdados .
docker push "$ACR_SERVER/radar-api-comdados:v3"
az containerapp update -n "$API_APP" -g "$RG" --image "$ACR_SERVER/radar-api-comdados:v3"

# --- Frontend (lembre do VITE_API_URL!) ---
docker build --build-arg VITE_API_URL="$API_URL" -t "$ACR_SERVER/radar-web:v2" -f web/Dockerfile web/
docker push "$ACR_SERVER/radar-web:v2"
az containerapp update -n "$WEB_APP" -g "$RG" --image "$ACR_SERVER/radar-web:v2"
```

> **Atualizar os dados (silver):** como a silver está *dentro* da imagem, basta
> rebuildar `radar-api-comdados` (o `COPY data/silver` pega a versão nova) e dar
> `update`. Não há File Share para sincronizar.

### Apagar tudo (parar de gastar crédito)
```bash
source .azure-deploy-vars.sh
az group delete --name "$RG" --yes --no-wait
```

---

# Deploy no Azure — Radar ENEM (Backend + Frontend)

Tutorial passo a passo para colocar o sistema **inteiro** (API FastAPI + site
React/Vite) rodando no Microsoft Azure, acessível de qualquer máquina.

> **Perfil do projeto (o que estamos subindo):**
> - **Backend**: FastAPI + DuckDB, já tem `Dockerfile` em `api/`, escuta na porta `8000`, lê os Parquet da *camada silver* pelo caminho em `RADAR_SILVER_ROOT`.
> - **Dados (silver)**: ~167 MB em `data/silver/` (particionado por `ano=`/`uf_prova=`). **Não** ficam dentro da imagem; precisam ser montados.
> - **Frontend**: React + Vite (estático), já tem `Dockerfile` em `web/` servindo via nginx na porta `8080`. A URL da API (`VITE_API_URL`) é fixada **no momento do build**, não em runtime.
> - A API é **pública e sem autenticação** por design (só serve estatísticas agregadas).

## Arquitetura escolhida no Azure

Para esse tamanho/perfil, o caminho mais simples e barato é:

| Peça | Serviço Azure | Por quê |
|------|---------------|---------|
| Guardar as imagens Docker | **Azure Container Registry (ACR)** | Registry privado, integra direto com Container Apps |
| Rodar a API | **Azure Container Apps (ACA)** | Roda contêineres sem gerenciar servidor, escala sozinho, HTTPS grátis |
| Rodar o site | **Azure Container Apps (ACA)** | Mesma coisa; usa a imagem nginx do `web/` |
| Guardar os dados silver | **Azure Files (File Share)** | 167 MB montados como volume read-only na API |

```
Navegador  ──►  [ ACA: web (nginx:8080) ]
                       │  chama VITE_API_URL
                       ▼
                [ ACA: api (uvicorn:8000) ]
                       │  lê /data/silver
                       ▼
                [ Azure Files: silver 167MB ]

Imagens ficam no  [ ACR ]
```

> **Alternativa mais simples ainda (sem Azure Files):** como a silver tem só 167 MB, dá para copiá-la **para dentro da imagem da API** e dispensar o File Share. É menos "correto" arquiteturalmente (o Dockerfile foi feito pra manter dados fora), mas é o deploy mais rápido possível. No fim deste guia há a seção **"Atalho: silver dentro da imagem"** com essa variante.

---

## Pré-requisitos (na sua máquina Linux)

1. Uma conta no Azure com assinatura ativa (o free tier serve para testar).
2. **Azure CLI** instalado:
   ```bash
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   az version
   ```
3. **Docker** instalado e funcionando (`docker ps` sem erro).
4. Logar no Azure:
   ```bash
   az login
   ```
   Abre o navegador. Se estiver em servidor sem navegador: `az login --use-device-code`.

---

## Passo 0 — Variáveis que vamos reutilizar

Defina uma vez no terminal (ajuste o que quiser). Tudo abaixo usa essas variáveis.

```bash
# Nome do grupo de recursos (tudo vive dentro dele; apagar = apagar tudo)
export RG=rg-radar-enem
# Região (brazilsouth = São Paulo)
export LOC=brazilsouth
# Nome do registry — PRECISA ser único no mundo e só letras/números minúsculos
export ACR=radarenem$RANDOM
# Ambiente do Container Apps
export ENV=env-radar-enem
# Nomes dos apps
export API_APP=radar-api
export WEB_APP=radar-web
```

> Guarde o valor que saiu em `echo $ACR` — você vai precisar dele depois.
> ```bash
> echo $ACR
> ```

---

## Passo 1 — Criar o grupo de recursos

```bash
az group create --name "$RG" --location "$LOC"
```

---

## Passo 2 — Criar o Container Registry (ACR) e enviar as imagens

Crie o registry:

```bash
az acr create --resource-group "$RG" --name "$ACR" --sku Basic --admin-enabled true
```

Em vez de buildar no seu PC e dar `push`, o jeito mais fácil é mandar o Azure
**buildar a imagem lá dentro** a partir do seu código (`az acr build`). Ele usa
o `Dockerfile` de cada pasta.

### 2.1 — Buildar a imagem da API

O contexto de build da API é a pasta `api/`:

```bash
az acr build \
  --registry "$ACR" \
  --image radar-api:v1 \
  --file api/Dockerfile \
  api/
```

### 2.2 — Buildar a imagem do Frontend

> **Atenção, esse é o detalhe que mais confunde:** o frontend grava a URL da API
> **dentro do bundle no momento do build** (`VITE_API_URL`). Como só vamos saber
> a URL pública da API depois de criá-la (Passo 4), a ordem correta é:
> **primeiro cria a API, pega a URL dela, e só então builda o frontend.**
>
> Por isso o build do frontend está mais abaixo, no **Passo 5**. Siga a ordem do guia.

---

## Passo 3 — Criar o Azure Files e enviar a camada silver

Crie uma conta de armazenamento (nome só minúsculas/números, único no mundo):

```bash
export STG=stradarenem$RANDOM
echo "Storage account: $STG"   # anote

az storage account create \
  --name "$STG" \
  --resource-group "$RG" \
  --location "$LOC" \
  --sku Standard_LRS \
  --kind StorageV2
```

Pegue a chave e crie o file share:

```bash
export STG_KEY=$(az storage account keys list \
  --account-name "$STG" --resource-group "$RG" \
  --query "[0].value" -o tsv)

az storage share create \
  --name silver \
  --account-name "$STG" \
  --account-key "$STG_KEY" \
  --quota 1
```

Envie a pasta `data/silver` inteira para o share (preserva as partições `ano=`/`uf_prova=`):

```bash
az storage file upload-batch \
  --account-name "$STG" \
  --account-key "$STG_KEY" \
  --destination silver \
  --source data/silver
```

> Isso sobe ~167 MB; leva alguns minutos. Confira depois:
> ```bash
> az storage file list --account-name "$STG" --account-key "$STG_KEY" --share-name silver -o table
> ```

---

## Passo 4 — Criar o ambiente do Container Apps e subir a API

Instale/atualize a extensão de Container Apps e registre os provedores:

```bash
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

Crie o ambiente:

```bash
az containerapp env create \
  --name "$ENV" \
  --resource-group "$RG" \
  --location "$LOC"
```

### 4.1 — Conectar o Azure Files ao ambiente

O volume do File Share é registrado no **ambiente**, depois referenciado pelo app:

```bash
az containerapp env storage set \
  --name "$ENV" \
  --resource-group "$RG" \
  --storage-name silvershare \
  --azure-file-account-name "$STG" \
  --azure-file-account-key "$STG_KEY" \
  --azure-file-share-name silver \
  --access-mode ReadOnly
```

### 4.2 — Criar o app da API

Credenciais do ACR (admin habilitado no Passo 2):

```bash
export ACR_SERVER=$(az acr show -n "$ACR" --query loginServer -o tsv)
export ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
export ACR_PASS=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)
```

Crie o app (ainda sem o volume — adicionamos no próximo subpasso via YAML):

```bash
az containerapp create \
  --name "$API_APP" \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$ACR_SERVER/radar-api:v1" \
  --registry-server "$ACR_SERVER" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 2 \
  --cpu 0.5 --memory 1.0Gi \
  --env-vars \
      RADAR_SILVER_ROOT=/data/silver \
      RADAR_AMBIENTE_REFERENCIA=azure \
      PORT=8000
```

### 4.3 — Montar o volume silver na API

A montagem de volume não cabe inteira no `create`; o jeito confiável é exportar
a config do app em YAML, acrescentar o volume e reaplicar.

```bash
az containerapp show --name "$API_APP" --resource-group "$RG" -o yaml > api-app.yaml
```

Abra `api-app.yaml` e, dentro de `properties.template`, garanta estes dois trechos:

```yaml
    template:
      containers:
      - name: radar-api
        image: <seu-acr>.azurecr.io/radar-api:v1
        # ... env já existente ...
        volumeMounts:
        - volumeName: silver
          mountPath: /data/silver
      volumes:
      - name: silver
        storageType: AzureFile
        storageName: silvershare
```

Reaplique:

```bash
az containerapp update --name "$API_APP" --resource-group "$RG" --yaml api-app.yaml
```

### 4.4 — Pegar a URL pública da API e testar

```bash
export API_URL="https://$(az containerapp show -n "$API_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "$API_URL"

# Deve responder 200 (silver montada) ou 503 (silver ainda não visível)
curl -i "$API_URL/health"
# Documentação interativa:
echo "$API_URL/docs"
```

> Se o `/health` der 503, quase sempre é a montagem do volume. Veja os logs:
> ```bash
> az containerapp logs show -n "$API_APP" -g "$RG" --follow
> ```

---

## Passo 5 — Buildar e subir o Frontend apontando para a API

Agora que você tem `API_URL`, builde o frontend com essa URL embutida:

```bash
az acr build \
  --registry "$ACR" \
  --image radar-web:v1 \
  --file web/Dockerfile \
  --build-arg VITE_API_URL="$API_URL" \
  web/
```

Crie o app do site:

```bash
az containerapp create \
  --name "$WEB_APP" \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$ACR_SERVER/radar-web:v1" \
  --registry-server "$ACR_SERVER" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 --max-replicas 2 \
  --cpu 0.25 --memory 0.5Gi
```

Pegue a URL do site:

```bash
export WEB_URL="https://$(az containerapp show -n "$WEB_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "Site: $WEB_URL"
```

---

## Passo 6 — Liberar o CORS na API para o domínio do site

O navegador vai bloquear as chamadas do site para a API se o CORS não permitir a
origem do frontend. Atualize a variável `RADAR_CORS_ORIGENS` da API com a URL do site:

```bash
az containerapp update \
  --name "$API_APP" \
  --resource-group "$RG" \
  --set-env-vars RADAR_CORS_ORIGENS="$WEB_URL"
```

Pronto. Abra `$WEB_URL` no navegador — o site deve carregar e conseguir falar com a API.

---

## Testes finais

```bash
echo "Frontend: $WEB_URL"
echo "API:      $API_URL"
echo "Swagger:  $API_URL/docs"
curl -s "$API_URL/v1/edicoes"     # deve listar as edições (2020..2025)
```

---

## Atualizar depois (novo deploy)

Quando mudar o código:

```bash
# API
az acr build --registry "$ACR" --image radar-api:v2 --file api/Dockerfile api/
az containerapp update -n "$API_APP" -g "$RG" --image "$ACR_SERVER/radar-api:v2"

# Frontend (lembre do VITE_API_URL!)
az acr build --registry "$ACR" --image radar-web:v2 --file web/Dockerfile \
  --build-arg VITE_API_URL="$API_URL" web/
az containerapp update -n "$WEB_APP" -g "$RG" --image "$ACR_SERVER/radar-web:v2"
```

Para atualizar os **dados** (silver), basta reenviar os arquivos para o File Share
(`az storage file upload-batch ...`) — não precisa rebuildar a API.

---

## Custos e como desligar

- Container Apps cobra por uso; com `min-replicas 1` há um custo base contínuo.
  Para economizar em ambiente de teste, pode usar `--min-replicas 0` (o app
  "dorme" sem tráfego, mas a primeira requisição fica lenta — cold start).
- **Apagar tudo** (para não gastar) é só apagar o grupo de recursos:
  ```bash
  az group delete --name "$RG" --yes --no-wait
  ```

---

## Atalho: silver dentro da imagem (dispensa Azure Files)

Se quiser o caminho mais curto e não ligar para a separação dados/imagem,
você pode embutir a silver na imagem da API. Assim o **Passo 3** e os
subpassos **4.1 / 4.3** ficam desnecessários.

1. Crie um `Dockerfile` alternativo, por exemplo `api/Dockerfile.comdados`, que
   parte da imagem normal e só adiciona a silver:

   ```dockerfile
   # api/Dockerfile.comdados
   FROM radar-api:v1
   # copia a silver para dentro da imagem (contexto = raiz do repo)
   COPY data/silver /data/silver
   ```

   Como esse `COPY` precisa enxergar `data/silver`, o build tem de rodar com a
   **raiz do repositório** como contexto e a imagem base precisa existir no ACR.
   O mais prático é fazer tudo num Dockerfile único multiestágio; se preferir,
   me peça que eu gero esse Dockerfile pronto.

2. Builde com contexto na raiz e sem montar volume:
   ```bash
   az acr build --registry "$ACR" --image radar-api-comdados:v1 \
     --file api/Dockerfile.comdados .
   ```
3. No `az containerapp create` da API, use essa imagem e **não** inclua
   `volumeMounts`/`volumes`. Mantenha `RADAR_SILVER_ROOT=/data/silver`.

Trade-off: a imagem fica ~167 MB maior e, para trocar os dados, você precisa
rebuildar e redeployar a API (em vez de só reenviar arquivos ao File Share).

---

## Resumo da ordem correta

1. `az login` e variáveis (Passo 0)
2. Grupo de recursos (Passo 1)
3. ACR + build da **API** (Passo 2.1)
4. Storage + upload da **silver** (Passo 3)
5. Ambiente ACA + volume + **API** no ar (Passo 4)
6. Pegar `API_URL` → build do **frontend** com `VITE_API_URL` → site no ar (Passo 5)
7. Ajustar **CORS** com a URL do site (Passo 6)
```
