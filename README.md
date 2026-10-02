# StartINEP - ENEM emFoco: Sua nota conta, o contexto revela.

Sistema para processamento e análise dos dados públicos do ENEM, permitindo comparações de desempenho entre diferentes edições.

---

## 🚀 Como Rodar Localmente

Abra dois terminais (um para o backend e outro para o frontend):

### 1. Backend (API)
```bash
cd api
source .venv/bin/activate
uvicorn radar_api.app:app --reload --port 8000
```
- Acesse a API e documentação em: [http://localhost:8000/docs](http://localhost:8000/docs)
- Status do serviço: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Frontend (Interface Web)
```bash
cd web
npm run dev
```
- Acesse no navegador: [http://localhost:5173](http://localhost:5173)

---

> 💡 Se for a primeira vez configurando o projeto ou precisar de mais detalhes, consulte o arquivo [COMO_RODAR.md](COMO_RODAR.md).
