# Como Rodar o Projeto Localmente

Guia rápido e direto para executar o **Backend** e o **Frontend** na sua máquina.

---

## 📋 Pré-requisitos

- **Python 3.12+**
- **Node.js 20+** e **npm**

---

## ⚡ Passo a Passo Rápido

Você precisará de **dois terminais** abertos.

### 1️⃣ Terminal 1: Backend (API)

Acesse a pasta `api`, ative o ambiente virtual e suba o servidor:

```bash
cd api
source .venv/bin/activate
uvicorn radar_api.app:app --reload --port 8000
```

> 🟢 **Backend rodando em:** [http://localhost:8000](http://localhost:8000)  
> 📖 **Swagger / Documentação:** [http://localhost:8000/docs](http://localhost:8000/docs)  
> 🩺 **Verificar status:** [http://localhost:8000/health](http://localhost:8000/health)

---

### 2️⃣ Terminal 2: Frontend (Interface Web)

Em uma nova aba ou janela de terminal, acesse a pasta `web` e inicie:

```bash
cd web
npm run dev
```

> 🌐 **Frontend rodando em:** [http://localhost:5173](http://localhost:5173) (abra no seu navegador)

---

## 🛠️ Primeira vez rodando? (Instalação das dependências)

Se ainda não tiver as dependências instaladas na sua máquina, execute antes:

### Configurar o Backend:
```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Configurar o Frontend:
```bash
cd web
npm install
cp .env.example .env.local
```
