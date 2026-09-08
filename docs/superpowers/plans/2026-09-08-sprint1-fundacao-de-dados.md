# Sprint 1 — Fundação de Dados (Bronze → Prata) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar os ZIPs de microdados do ENEM 2024 e 2025 em Parquet particionado, comprimido e confiável, com pipeline idempotente, portões de qualidade e volumetria medida.

**Architecture:** CLI Python (`radar-etl`) executando localmente (on-premises). Extração baixa e verifica o ZIP por SHA-256; a camada Bronze guarda o CSV bruto intocado; um **contrato YAML por edição** mapeia colunas de origem para um schema canônico único; DuckDB faz a projeção e a conversão por *streaming*, sem carregar a base em RAM; três portões de qualidade (schema, volume, freshness) decidem a promoção; a escrita produz Parquet+Snappy particionado por `ano=/uf_prova=`. Um manifesto JSON versionado registra hashes, contagens e volumetria de cada execução.

**Tech Stack:** Python 3.12 · uv · DuckDB · PyArrow · Pydantic v2 · PyYAML · Typer · pytest · Hypothesis · Ruff

**Spec:** [`PLANO_IMPLEMENTACAO.md`](../../../PLANO_IMPLEMENTACAO.md) — §1-D1, §3, §4, §7 (Sprint 1), §8 (R1, R2, R3), §9.4

---

## Global Constraints

- **Python ≥ 3.12**; gestão de dependências e execução exclusivamente por **`uv`**. Todo comando roda de `pipeline/`.
- **Nenhum dado do INEP é versionado.** `data/bronze/`, `data/silver/`, `data/gold/`, `*.csv`, `*.parquet`, `*.zip` no `.gitignore`. Exceção versionada: `data/_manifests/`.
- **Nenhum teste acessa a rede.** Toda fixture é construída em disco pelo próprio teste. Download é testado por injeção de dependência, nunca por chamada real.
- **Idempotência é requisito, não otimização.** Fonte inalterada ⟹ mesmo resultado byte a byte; reexecução detectada e pulada.
- **Determinismo da escrita** garantido por `SET threads TO 1`, `SET preserve_insertion_order TO true` e `ORDER BY ALL` explícito antes do `COPY`.
- **Sem `NU_INSCRICAO` na camada Prata.** O identificador do participante não é necessário para nenhuma estatística do produto; descartá-lo reduz volumetria e superfície LGPD (§4-Valor, §1-D2).
- **Commits:** Conventional Commits, escopo `etl`, descrição no imperativo, ≤ 72 caracteres (§9.2).
- **Branch de trabalho:** `feat/etl-fundacao-de-dados`.
- **Nomes de código em português**, coerentes com o restante do repositório.

---

## Estrutura de Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `pipeline/pyproject.toml` | Dependências, entry point `radar-etl`, config de ruff/pytest |
| `pipeline/src/radar_etl/manifesto.py` | Hash SHA-256 por streaming; modelo e persistência do manifesto |
| `pipeline/src/radar_etl/extract/fonte.py` | Metadados remotos, download, verificação de integridade |
| `pipeline/src/radar_etl/extract/descompactar.py` | Localiza e extrai o CSV do ZIP |
| `pipeline/src/radar_etl/contracts/modelos.py` | Modelos Pydantic do schema canônico e do contrato de edição |
| `pipeline/src/radar_etl/contracts/canonical.yml` | Schema canônico único do projeto |
| `pipeline/src/radar_etl/contracts/enem_2024.yml` · `enem_2025.yml` | Mapeamento origem → canônico por edição |
| `pipeline/src/radar_etl/transform/regioes.py` | UF → macrorregião |
| `pipeline/src/radar_etl/transform/sql.py` | Geração do SELECT canônico a partir do contrato |
| `pipeline/src/radar_etl/quality/portoes.py` | Portões de schema, volume e freshness |
| `pipeline/src/radar_etl/load/parquet.py` | Escrita Parquet particionada e medição de volumetria |
| `pipeline/src/radar_etl/cli.py` | Comandos `inspecionar` e `ingest`, orquestração e idempotência |

Cada módulo tem uma responsabilidade e é testável isoladamente. `transform/sql.py` e `quality/portoes.py` são **funções puras** — recebem contrato e números, devolvem SQL e veredito, sem tocar em disco. É isso que permite testá-los sem fixture de gigabytes.

---

## Task 1: Esqueleto do pacote e ferramental

**Files:**
- Create: `pipeline/pyproject.toml`, `pipeline/src/radar_etl/__init__.py`, `pipeline/src/radar_etl/cli.py`, `pipeline/tests/test_cli.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nada
- Produces: pacote `radar_etl` instalável; `radar_etl.__version__: str`; app Typer `radar_etl.cli.app`; comando de console `radar-etl`

- [ ] **Step 1: Corrigir o `.gitignore` (§9.4 da spec)**

Acrescentar ao final de `.gitignore` na raiz do repositório:

```gitignore

# ---- Radar ENEM: dados do INEP nunca sao versionados ----
data/bronze/
data/silver/
data/gold/
*.csv
*.parquet
*.zip
# Manifestos SAO versionados: sao a linhagem auditavel
!data/_manifests/
!data/_manifests/**
```

- [ ] **Step 2: Criar `pipeline/pyproject.toml`**

```toml
[project]
name = "radar-etl"
version = "0.1.0"
description = "Pipeline de ingestao dos microdados do ENEM - Radar ENEM"
requires-python = ">=3.12"
dependencies = [
    "duckdb>=1.1",
    "pyarrow>=17",
    "pydantic>=2.8",
    "pyyaml>=6.0",
    "typer>=0.12",
    "httpx>=0.27",
]

[project.scripts]
radar-etl = "radar_etl.cli:app"

[dependency-groups]
dev = ["pytest>=8.3", "hypothesis>=6.100", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/radar_etl"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Escrever o teste que falha**

`pipeline/tests/test_cli.py`:

```python
from typer.testing import CliRunner

from radar_etl import __version__
from radar_etl.cli import app

runner = CliRunner()


def test_versao_e_exposta_pelo_pacote():
    assert __version__ == "0.1.0"


def test_cli_responde_ao_help():
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    assert "ingest" in resultado.stdout
```

- [ ] **Step 4: Rodar o teste e confirmar que falha**

```bash
cd pipeline && uv sync && uv run pytest tests/test_cli.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl'`.

- [ ] **Step 5: Implementar o mínimo**

`pipeline/src/radar_etl/__init__.py`:

```python
__version__ = "0.1.0"
```

`pipeline/src/radar_etl/cli.py`:

```python
import typer

app = typer.Typer(help="Pipeline de ingestao dos microdados do ENEM.", no_args_is_help=True)


@app.command()
def ingest(edicao: int = typer.Option(..., help="Ano da edicao do ENEM.")) -> None:
    """Executa a ingestao de uma edicao (implementado na Task 10)."""
    raise NotImplementedError
```

- [ ] **Step 6: Rodar o teste e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_cli.py -v
```

Esperado: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add .gitignore pipeline/
git commit -m "chore(etl): criar esqueleto do pacote radar-etl"
```

---

## Task 2: Manifesto e hashing por streaming

O manifesto é o que sustenta o risco **R1** da spec: sem hash da fonte, uma retificação do INEP altera as estatísticas em silêncio.

**Files:**
- Create: `pipeline/src/radar_etl/manifesto.py`, `pipeline/tests/test_manifesto.py`

**Interfaces:**
- Consumes: nada
- Produces: `sha256_arquivo(caminho: Path) -> str`; `agora_iso() -> str`; classe `Manifesto` (Pydantic) com campos `edicao: int`, `fonte_url: str`, `fonte_sha256: str`, `fonte_bytes: int`, `fonte_last_modified: str | None`, `baixado_em: str`, `csv_bytes: int | None`, `linhas_bronze: int | None`, `linhas_prata: int | None`, `bytes_prata: int | None`, `versao_contrato: int | None`, `processado_em: str | None`, e métodos `salvar(caminho: Path) -> None` / `carregar(caminho: Path) -> Manifesto | None` (classmethod)

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_manifesto.py`:

```python
import hashlib

from radar_etl.manifesto import Manifesto, agora_iso, sha256_arquivo


def test_sha256_confere_com_hashlib(tmp_path):
    arquivo = tmp_path / "dados.csv"
    conteudo = b"NU_ANO;SG_UF_PROVA\n2025;SC\n" * 5000
    arquivo.write_bytes(conteudo)

    assert sha256_arquivo(arquivo) == hashlib.sha256(conteudo).hexdigest()


def test_sha256_nao_carrega_arquivo_inteiro_em_memoria(tmp_path):
    # 8 MB com blocos de 1 MB: exercita o laco de streaming mais de uma vez.
    arquivo = tmp_path / "grande.bin"
    with open(arquivo, "wb") as f:
        for _ in range(8):
            f.write(b"x" * 1024 * 1024)

    esperado = hashlib.sha256(b"x" * 1024 * 1024 * 8).hexdigest()
    assert sha256_arquivo(arquivo) == esperado


def test_manifesto_sobrevive_a_ida_e_volta_do_disco(tmp_path):
    destino = tmp_path / "_manifests" / "enem_2025.json"
    original = Manifesto(
        edicao=2025,
        fonte_url="https://exemplo.invalido/microdados_enem_2025.zip",
        fonte_sha256="abc123",
        fonte_bytes=1024,
        fonte_last_modified="Mon, 01 Sep 2026 12:00:00 GMT",
        baixado_em=agora_iso(),
    )
    original.salvar(destino)

    recarregado = Manifesto.carregar(destino)
    assert recarregado == original
    assert recarregado.linhas_prata is None


def test_carregar_manifesto_inexistente_devolve_none(tmp_path):
    assert Manifesto.carregar(tmp_path / "nao_existe.json") is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_manifesto.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.manifesto'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/manifesto.py`:

```python
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

BLOCO = 1024 * 1024


def sha256_arquivo(caminho: Path) -> str:
    """Calcula o SHA-256 lendo em blocos de 1 MB, sem carregar o arquivo em RAM."""
    digest = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            digest.update(bloco)
    return digest.hexdigest()


def agora_iso() -> str:
    return datetime.now(UTC).isoformat()


class Manifesto(BaseModel):
    """Linhagem de uma edicao: o que foi baixado, o que foi processado, e com que resultado."""

    edicao: int
    fonte_url: str
    fonte_sha256: str
    fonte_bytes: int
    fonte_last_modified: str | None = None
    baixado_em: str

    csv_bytes: int | None = None
    linhas_bronze: int | None = None
    linhas_prata: int | None = None
    bytes_prata: int | None = None
    versao_contrato: int | None = None
    processado_em: str | None = None

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def carregar(cls, caminho: Path) -> Manifesto | None:
        if not caminho.exists():
            return None
        return cls.model_validate_json(caminho.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_manifesto.py -v
```

Esperado: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/manifesto.py pipeline/tests/test_manifesto.py
git commit -m "feat(etl): adicionar manifesto de linhagem e hash por streaming"
```

---

## Task 3: Extração — metadados remotos, download e descompactação

**Files:**
- Create: `pipeline/src/radar_etl/extract/__init__.py`, `pipeline/src/radar_etl/extract/fonte.py`, `pipeline/src/radar_etl/extract/descompactar.py`, `pipeline/tests/test_extract.py`

**Interfaces:**
- Consumes: `sha256_arquivo` (Task 2)
- Produces:
  - `MetadadosRemotos` (dataclass): `bytes_totais: int | None`, `last_modified: str | None`, `etag: str | None`
  - `consultar_metadados(url: str, cliente: httpx.Client | None = None) -> MetadadosRemotos`
  - `baixar(url: str, destino: Path, cliente: httpx.Client | None = None) -> Path`
  - `extrair_csv(zip_path: Path, nome_interno: str, destino_dir: Path) -> Path`
  - `ArquivoInternoAusente(Exception)`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_extract.py`:

```python
import zipfile

import httpx
import pytest

from radar_etl.extract.descompactar import ArquivoInternoAusente, extrair_csv
from radar_etl.extract.fonte import baixar, consultar_metadados


def _cliente_falso(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_consultar_metadados_le_cabecalhos_sem_baixar_corpo():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(
            200,
            headers={
                "content-length": "734003200",
                "last-modified": "Mon, 01 Sep 2026 12:00:00 GMT",
                "etag": '"abc-123"',
            },
        )

    meta = consultar_metadados("https://exemplo.invalido/a.zip", cliente=_cliente_falso(handler))

    assert meta.bytes_totais == 734003200
    assert meta.last_modified == "Mon, 01 Sep 2026 12:00:00 GMT"
    assert meta.etag == '"abc-123"'


def test_baixar_grava_o_corpo_no_destino(tmp_path):
    corpo = b"conteudo-do-zip" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=corpo)

    destino = tmp_path / "microdados.zip"
    resultado = baixar("https://exemplo.invalido/a.zip", destino, cliente=_cliente_falso(handler))

    assert resultado == destino
    assert destino.read_bytes() == corpo


def test_baixar_propaga_erro_http(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        baixar("https://exemplo.invalido/a.zip", tmp_path / "x.zip", cliente=_cliente_falso(handler))


def test_extrair_csv_recupera_o_arquivo_pedido(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("DADOS/MICRODADOS_ENEM_2025.csv", "NU_ANO;SG_UF_PROVA\n2025;SC\n")
        z.writestr("LEIA-ME.txt", "documentacao")

    destino = extrair_csv(zip_path, "DADOS/MICRODADOS_ENEM_2025.csv", tmp_path / "bronze")

    assert destino.name == "MICRODADOS_ENEM_2025.csv"
    assert destino.read_text(encoding="utf-8").startswith("NU_ANO;SG_UF_PROVA")


def test_extrair_csv_falha_com_mensagem_util_quando_o_nome_nao_existe(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("DADOS/OUTRO_NOME.csv", "a;b\n")

    with pytest.raises(ArquivoInternoAusente) as erro:
        extrair_csv(zip_path, "DADOS/MICRODADOS_ENEM_2025.csv", tmp_path / "bronze")

    # A mensagem precisa listar o que existe: o nome interno muda entre edicoes (risco R3).
    assert "DADOS/OUTRO_NOME.csv" in str(erro.value)
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_extract.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.extract'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/extract/__init__.py`: arquivo vazio.

`pipeline/src/radar_etl/extract/fonte.py`:

```python
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import httpx

TIMEOUT = httpx.Timeout(30.0, read=300.0)


@dataclass(frozen=True)
class MetadadosRemotos:
    """O que o INEP publica hoje, sem baixar o corpo do arquivo."""

    bytes_totais: int | None
    last_modified: str | None
    etag: str | None


def _contexto(cliente: httpx.Client | None):
    if cliente is not None:
        return nullcontext(cliente)
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)


def consultar_metadados(url: str, cliente: httpx.Client | None = None) -> MetadadosRemotos:
    with _contexto(cliente) as c:
        resposta = c.head(url)
        resposta.raise_for_status()
        tamanho = resposta.headers.get("content-length")
        return MetadadosRemotos(
            bytes_totais=int(tamanho) if tamanho is not None else None,
            last_modified=resposta.headers.get("last-modified"),
            etag=resposta.headers.get("etag"),
        )


def baixar(url: str, destino: Path, cliente: httpx.Client | None = None) -> Path:
    """Baixa em streaming para nao materializar o ZIP inteiro em memoria."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with _contexto(cliente) as c:
        with c.stream("GET", url) as resposta:
            resposta.raise_for_status()
            with open(destino, "wb") as f:
                for bloco in resposta.iter_bytes(chunk_size=1024 * 1024):
                    f.write(bloco)
    return destino
```

`pipeline/src/radar_etl/extract/descompactar.py`:

```python
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


class ArquivoInternoAusente(Exception):
    """O nome esperado dentro do ZIP nao existe nesta edicao."""


def extrair_csv(zip_path: Path, nome_interno: str, destino_dir: Path) -> Path:
    """Extrai um unico arquivo do ZIP para `destino_dir`, preservando apenas o nome base."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        disponiveis = z.namelist()
        if nome_interno not in disponiveis:
            raise ArquivoInternoAusente(
                f"'{nome_interno}' nao existe em {zip_path.name}. "
                f"Arquivos disponiveis: {disponiveis}"
            )
        destino = destino_dir / Path(nome_interno).name
        with z.open(nome_interno) as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida, length=1024 * 1024)
    return destino
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_extract.py -v
```

Esperado: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/extract/ pipeline/tests/test_extract.py
git commit -m "feat(etl): adicionar download em streaming e extracao do csv"
```

---

## Task 4: Contratos de schema

É o mecanismo que sustenta o risco **R3** e o objetivo específico #8 da spec: incorporar edição nova deve ser **escrever um YAML**, não alterar código.

**Files:**
- Create: `pipeline/src/radar_etl/contracts/__init__.py`, `pipeline/src/radar_etl/contracts/modelos.py`, `pipeline/src/radar_etl/contracts/canonical.yml`, `pipeline/tests/test_contracts.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `ColunaCanonica` (Pydantic): `tipo: str`, `descricao: str`
  - `SchemaCanonico` (Pydantic): `versao: int`, `particoes: list[str]`, `colunas: dict[str, ColunaCanonica]`
  - `FonteEdicao` (Pydantic): `url: str`, `arquivo_csv: str`, `separador: str`, `encoding: str`
  - `ContratoEdicao` (Pydantic): `edicao: int`, `versao_contrato: int`, `fonte: FonteEdicao`, `mapeamento: dict[str, str]`, `derivadas: dict[str, str]`
  - `carregar_canonico(caminho: Path | None = None) -> SchemaCanonico`
  - `carregar_contrato(edicao: int, canonico: SchemaCanonico, diretorio: Path | None = None) -> ContratoEdicao`
  - `ContratoInvalido(Exception)`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_contracts.py`:

```python
import pytest
import yaml

from radar_etl.contracts.modelos import (
    ContratoInvalido,
    carregar_canonico,
    carregar_contrato,
)

CANONICO_MINIMO = {
    "versao": 1,
    "particoes": ["ano", "uf_prova"],
    "colunas": {
        "ano": {"tipo": "SMALLINT", "descricao": "Ano da edicao"},
        "uf_prova": {"tipo": "VARCHAR", "descricao": "UF de aplicacao da prova"},
        "regiao": {"tipo": "VARCHAR", "descricao": "Macrorregiao derivada de uf_prova"},
        "nota_mt": {"tipo": "FLOAT", "descricao": "Nota de Matematica"},
    },
}


def _escrever(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")


def test_carrega_o_schema_canonico(tmp_path):
    caminho = tmp_path / "canonical.yml"
    _escrever(caminho, CANONICO_MINIMO)

    canonico = carregar_canonico(caminho)

    assert canonico.versao == 1
    assert canonico.particoes == ["ano", "uf_prova"]
    assert canonico.colunas["nota_mt"].tipo == "FLOAT"


def test_carrega_contrato_de_edicao_valido(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2025.yml",
        {
            "edicao": 2025,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/microdados_enem_2025.zip",
                "arquivo_csv": "DADOS/MICRODADOS_ENEM_2025.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {"ano": "NU_ANO", "uf_prova": "SG_UF_PROVA", "nota_mt": "NU_NOTA_MT"},
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    contrato = carregar_contrato(2025, canonico, diretorio=tmp_path)

    assert contrato.edicao == 2025
    assert contrato.fonte.encoding == "latin-1"
    assert contrato.mapeamento["nota_mt"] == "NU_NOTA_MT"


def test_contrato_que_deixa_coluna_canonica_sem_origem_e_rejeitado(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2024.yml",
        {
            "edicao": 2024,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/a.zip",
                "arquivo_csv": "D/A.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {"ano": "NU_ANO", "uf_prova": "SG_UF_PROVA"},  # falta nota_mt
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(2024, canonico, diretorio=tmp_path)

    assert "nota_mt" in str(erro.value)


def test_contrato_que_inventa_coluna_fora_do_canonico_e_rejeitado(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2023.yml",
        {
            "edicao": 2023,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/a.zip",
                "arquivo_csv": "D/A.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {
                "ano": "NU_ANO",
                "uf_prova": "SG_UF_PROVA",
                "nota_mt": "NU_NOTA_MT",
                "coluna_fantasma": "TP_QUALQUER",
            },
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(2023, canonico, diretorio=tmp_path)

    assert "coluna_fantasma" in str(erro.value)


def test_contrato_inexistente_falha_apontando_o_caminho(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(1998, canonico, diretorio=tmp_path)

    assert "enem_1998.yml" in str(erro.value)
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_contracts.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.contracts'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/contracts/__init__.py`: arquivo vazio.

`pipeline/src/radar_etl/contracts/modelos.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

DIRETORIO_PADRAO = Path(__file__).parent


class ContratoInvalido(Exception):
    """O contrato da edicao nao existe, esta malformado, ou nao fecha com o schema canonico."""


class ColunaCanonica(BaseModel):
    tipo: str
    descricao: str


class SchemaCanonico(BaseModel):
    versao: int
    particoes: list[str]
    colunas: dict[str, ColunaCanonica]


class FonteEdicao(BaseModel):
    url: str
    arquivo_csv: str
    separador: str
    encoding: str


class ContratoEdicao(BaseModel):
    edicao: int
    versao_contrato: int
    fonte: FonteEdicao
    mapeamento: dict[str, str]
    derivadas: dict[str, str] = {}


def carregar_canonico(caminho: Path | None = None) -> SchemaCanonico:
    caminho = caminho or DIRETORIO_PADRAO / "canonical.yml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return SchemaCanonico.model_validate(dados)


def carregar_contrato(
    edicao: int,
    canonico: SchemaCanonico,
    diretorio: Path | None = None,
) -> ContratoEdicao:
    """Carrega e valida o contrato de uma edicao contra o schema canonico.

    A validacao cruzada e o ponto do exercicio: um contrato so e valido se cobre
    exatamente as colunas canonicas, sem faltar nenhuma e sem inventar nenhuma.
    """
    diretorio = diretorio or DIRETORIO_PADRAO
    caminho = diretorio / f"enem_{edicao}.yml"
    if not caminho.exists():
        raise ContratoInvalido(
            f"Contrato ausente: {caminho}. "
            f"Para incorporar a edicao {edicao}, crie esse arquivo YAML."
        )

    try:
        contrato = ContratoEdicao.model_validate(
            yaml.safe_load(caminho.read_text(encoding="utf-8"))
        )
    except ValidationError as erro:
        raise ContratoInvalido(f"Contrato malformado em {caminho}:\n{erro}") from erro

    cobertas = set(contrato.mapeamento) | set(contrato.derivadas)
    esperadas = set(canonico.colunas)

    faltando = esperadas - cobertas
    if faltando:
        raise ContratoInvalido(
            f"{caminho.name} nao cobre colunas canonicas: {sorted(faltando)}"
        )

    sobrando = cobertas - esperadas
    if sobrando:
        raise ContratoInvalido(
            f"{caminho.name} declara colunas fora do schema canonico: {sorted(sobrando)}"
        )

    return contrato
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_contracts.py -v
```

Esperado: 5 passed.

- [ ] **Step 5: Escrever o schema canônico definitivo**

`pipeline/src/radar_etl/contracts/canonical.yml`:

```yaml
# Schema canonico unico do Radar ENEM.
# Toda edicao do ENEM e traduzida para ESTE vocabulario por um contrato proprio.
# Alterar este arquivo obriga a revisar todos os contratos de edicao.
versao: 1
particoes: [ano, uf_prova]

colunas:
  ano:
    tipo: SMALLINT
    descricao: "Ano da edicao do ENEM. Coluna de particao."
  uf_prova:
    tipo: VARCHAR
    descricao: "Sigla da UF onde o participante realizou a prova. Coluna de particao."
  regiao:
    tipo: VARCHAR
    descricao: "Macrorregiao (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) derivada de uf_prova."

  faixa_etaria:
    tipo: TINYINT
    descricao: "Codigo da faixa etaria do participante, conforme dicionario do INEP."
  sexo:
    tipo: VARCHAR
    descricao: "Sexo declarado (M/F)."
  cor_raca:
    tipo: TINYINT
    descricao: "Codigo de cor/raca autodeclarada, conforme dicionario do INEP."
  tipo_escola:
    tipo: TINYINT
    descricao: "Tipo de escola do ensino medio (publica, privada, exterior, nao respondeu)."
  dependencia_adm_escola:
    tipo: TINYINT
    descricao: "Dependencia administrativa da escola (federal, estadual, municipal, privada)."
  treineiro:
    tipo: BOOLEAN
    descricao: "Participante fez a prova como treineiro."

  renda_familiar:
    tipo: VARCHAR
    descricao: "Faixa de renda familiar mensal declarada no questionario socioeconomico (Q006)."
  escolaridade_pai:
    tipo: VARCHAR
    descricao: "Escolaridade do pai declarada no questionario socioeconomico."
  escolaridade_mae:
    tipo: VARCHAR
    descricao: "Escolaridade da mae declarada no questionario socioeconomico."

  presenca_cn:
    tipo: TINYINT
    descricao: "Situacao de presenca em Ciencias da Natureza (0 faltou, 1 presente, 2 eliminado)."
  presenca_ch:
    tipo: TINYINT
    descricao: "Situacao de presenca em Ciencias Humanas."
  presenca_lc:
    tipo: TINYINT
    descricao: "Situacao de presenca em Linguagens e Codigos."
  presenca_mt:
    tipo: TINYINT
    descricao: "Situacao de presenca em Matematica."

  nota_cn:
    tipo: FLOAT
    descricao: "Nota de Ciencias da Natureza (0-1000). Nula para ausentes e eliminados."
  nota_ch:
    tipo: FLOAT
    descricao: "Nota de Ciencias Humanas (0-1000). Nula para ausentes e eliminados."
  nota_lc:
    tipo: FLOAT
    descricao: "Nota de Linguagens e Codigos (0-1000). Nula para ausentes e eliminados."
  nota_mt:
    tipo: FLOAT
    descricao: "Nota de Matematica (0-1000). Nula para ausentes e eliminados."
  nota_redacao:
    tipo: FLOAT
    descricao: "Nota da redacao (0-1000). Nula para ausentes e eliminados."
```

> **Decisão registrada:** linhas de participantes ausentes **não são descartadas** na camada Prata. O INEP já grava nota nula para ausente e eliminado; filtrar `nota IS NOT NULL` é responsabilidade da consulta, não da ingestão. A Prata preserva fidelidade à origem — descartar aqui destruiria a capacidade de responder perguntas sobre abstenção, que é justamente um dos recortes previstos para o AV4.

- [ ] **Step 6: Commit**

```bash
git add pipeline/src/radar_etl/contracts/ pipeline/tests/test_contracts.py
git commit -m "feat(etl): adicionar contratos de schema por edicao"
```

---

## Task 5: Descoberta do schema real de 2024 e 2025

Esta é a única tarefa **exploratória** do plano: o mapeamento origem → canônico não pode ser inventado, tem que ser lido do arquivo real. O comando `inspecionar` existe para tornar essa leitura repetível e auditável — ele será reusado a cada edição futura.

**Files:**
- Create: `pipeline/src/radar_etl/contracts/enem_2024.yml`, `pipeline/src/radar_etl/contracts/enem_2025.yml`
- Modify: `pipeline/src/radar_etl/cli.py`
- Test: `pipeline/tests/test_cli.py`

**Interfaces:**
- Consumes: `extrair_csv` (Task 3), `carregar_canonico` (Task 4)
- Produces: comando `radar-etl inspecionar --zip <caminho>`; contratos `enem_2024.yml` e `enem_2025.yml` validados

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `pipeline/tests/test_cli.py`:

```python
import zipfile


def test_inspecionar_lista_arquivos_e_cabecalho(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(
            "DADOS/MICRODADOS_ENEM_2025.csv",
            "NU_ANO;SG_UF_PROVA;NU_NOTA_MT\n2025;SC;712.4\n",
        )
        z.writestr("LEIA-ME.txt", "doc")

    resultado = runner.invoke(app, ["inspecionar", "--zip", str(zip_path)])

    assert resultado.exit_code == 0
    assert "DADOS/MICRODADOS_ENEM_2025.csv" in resultado.stdout
    assert "NU_NOTA_MT" in resultado.stdout
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_cli.py::test_inspecionar_lista_arquivos_e_cabecalho -v
```

Esperado: FAIL — `exit_code == 2` (comando `inspecionar` inexistente).

- [ ] **Step 3: Implementar o comando**

Acrescentar a `pipeline/src/radar_etl/cli.py`:

```python
import zipfile
from pathlib import Path


@app.command()
def inspecionar(
    zip_path: Path = typer.Option(..., "--zip", help="Caminho do ZIP de microdados."),
    linhas: int = typer.Option(3, help="Quantas linhas de amostra exibir."),
) -> None:
    """Lista o conteudo do ZIP e o cabecalho do maior CSV, para escrever o contrato da edicao."""
    with zipfile.ZipFile(zip_path) as z:
        infos = sorted(z.infolist(), key=lambda i: i.file_size, reverse=True)

        typer.echo("=== Arquivos no ZIP (maiores primeiro) ===")
        for info in infos:
            typer.echo(f"  {info.file_size / 1_048_576:10.1f} MB  {info.filename}")

        csvs = [i for i in infos if i.filename.lower().endswith(".csv")]
        if not csvs:
            typer.echo("\nNenhum CSV encontrado no ZIP.")
            raise typer.Exit(code=1)

        maior = csvs[0]
        typer.echo(f"\n=== Cabecalho de {maior.filename} ===")
        with z.open(maior.filename) as f:
            bruto = f.read(256 * 1024)

        for codificacao in ("utf-8", "latin-1"):
            try:
                texto = bruto.decode(codificacao)
            except UnicodeDecodeError:
                typer.echo(f"  encoding {codificacao}: FALHOU")
                continue
            typer.echo(f"  encoding {codificacao}: OK")
            for numero, linha in enumerate(texto.splitlines()[: linhas + 1]):
                rotulo = "cabecalho" if numero == 0 else f"linha {numero}"
                typer.echo(f"    [{rotulo}] {linha[:400]}")
            break
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_cli.py -v
```

Esperado: 3 passed.

- [ ] **Step 5: Baixar as edições reais e inspecionar**

```bash
cd pipeline
mkdir -p ../data/bronze
for ANO in 2024 2025; do
  curl -L --fail --progress-bar \
    -o "../data/bronze/microdados_enem_${ANO}.zip" \
    "https://download.inep.gov.br/microdados/microdados_enem_${ANO}.zip"
done
ls -lh ../data/bronze/
uv run radar-etl inspecionar --zip ../data/bronze/microdados_enem_2025.zip | tee /tmp/inspecao_2025.txt
uv run radar-etl inspecionar --zip ../data/bronze/microdados_enem_2024.zip | tee /tmp/inspecao_2024.txt
```

Se a URL retornar 404, abrir https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem e copiar o link real da edição — o padrão de nome do INEP já mudou em edições passadas.

- [ ] **Step 6: Escrever os contratos a partir do que foi observado**

Usar a saída do Step 5 para preencher `enem_2025.yml`. O gabarito abaixo usa os nomes de coluna praticados pelo INEP nas edições recentes — **conferir cada linha contra o cabeçalho real impresso** e corrigir o que divergir. É exatamente aqui que o risco **R3** se manifesta, e a divergência encontrada precisa ser anotada em `docs/arquitetura/dicionario_de_dados.md`.

`pipeline/src/radar_etl/contracts/enem_2025.yml`:

```yaml
edicao: 2025
versao_contrato: 1

fonte:
  url: "https://download.inep.gov.br/microdados/microdados_enem_2025.zip"
  arquivo_csv: "DADOS/MICRODADOS_ENEM_2025.csv"   # CONFERIR no Step 5
  separador: ";"
  encoding: "latin-1"                              # CONFERIR no Step 5

# canonico: COLUNA_DE_ORIGEM
mapeamento:
  ano: NU_ANO
  uf_prova: SG_UF_PROVA
  faixa_etaria: TP_FAIXA_ETARIA
  sexo: TP_SEXO
  cor_raca: TP_COR_RACA
  tipo_escola: TP_ESCOLA
  dependencia_adm_escola: TP_DEPENDENCIA_ADM_ESC
  treineiro: IN_TREINEIRO
  renda_familiar: Q006
  escolaridade_pai: Q001
  escolaridade_mae: Q002
  presenca_cn: TP_PRESENCA_CN
  presenca_ch: TP_PRESENCA_CH
  presenca_lc: TP_PRESENCA_LC
  presenca_mt: TP_PRESENCA_MT
  nota_cn: NU_NOTA_CN
  nota_ch: NU_NOTA_CH
  nota_lc: NU_NOTA_LC
  nota_mt: NU_NOTA_MT
  nota_redacao: NU_NOTA_REDACAO

# Colunas que nao existem na origem e sao calculadas pelo pipeline.
derivadas:
  regiao: regiao_por_uf
```

Duplicar como `enem_2024.yml`, trocando `edicao`, `url` e `arquivo_csv`, e ajustando qualquer nome divergente encontrado na inspeção de 2024.

- [ ] **Step 7: Verificar que os contratos fecham com o canônico**

```bash
cd pipeline && uv run python -c "
from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
c = carregar_canonico()
for ano in (2024, 2025):
    contrato = carregar_contrato(ano, c)
    print(f'{ano}: OK, {len(contrato.mapeamento)} colunas mapeadas, encoding={contrato.fonte.encoding}')
"
```

Esperado: duas linhas `OK`. Erro aqui significa contrato incompleto — corrigir antes de seguir.

- [ ] **Step 8: Commit**

```bash
git add pipeline/src/radar_etl/cli.py pipeline/tests/test_cli.py pipeline/src/radar_etl/contracts/enem_202*.yml
git commit -m "feat(etl): adicionar comando inspecionar e contratos de 2024 e 2025"
```

---

## Task 6: Derivação de macrorregião

**Files:**
- Create: `pipeline/src/radar_etl/transform/__init__.py`, `pipeline/src/radar_etl/transform/regioes.py`, `pipeline/tests/test_regioes.py`

**Interfaces:**
- Consumes: nada
- Produces: `UF_PARA_REGIAO: dict[str, str]` (27 entradas); `sql_case_regiao(coluna_uf: str) -> str`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_regioes.py`:

```python
import duckdb
import pytest

from radar_etl.transform.regioes import UF_PARA_REGIAO, sql_case_regiao


def test_mapa_cobre_as_27_unidades_federativas():
    assert len(UF_PARA_REGIAO) == 27
    assert set(UF_PARA_REGIAO.values()) == {
        "Norte",
        "Nordeste",
        "Centro-Oeste",
        "Sudeste",
        "Sul",
    }


@pytest.mark.parametrize(
    ("uf", "regiao"),
    [("SC", "Sul"), ("SP", "Sudeste"), ("BA", "Nordeste"), ("AM", "Norte"), ("DF", "Centro-Oeste")],
)
def test_case_sql_traduz_uf_para_regiao(uf, regiao):
    con = duckdb.connect()
    sql = f"SELECT {sql_case_regiao('uf')} AS regiao FROM (SELECT '{uf}' AS uf)"
    assert con.execute(sql).fetchone()[0] == regiao


def test_uf_desconhecida_vira_nulo_em_vez_de_erro():
    con = duckdb.connect()
    sql = f"SELECT {sql_case_regiao('uf')} AS regiao FROM (SELECT 'ZZ' AS uf)"
    assert con.execute(sql).fetchone()[0] is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_regioes.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.transform'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/transform/__init__.py`: arquivo vazio.

`pipeline/src/radar_etl/transform/regioes.py`:

```python
from __future__ import annotations

UF_PARA_REGIAO: dict[str, str] = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}


def sql_case_regiao(coluna_uf: str) -> str:
    """Gera o CASE que traduz UF em macrorregiao.

    UF fora do mapa devolve NULL em vez de erro: um codigo inesperado na origem
    e assunto do portao de qualidade, nao motivo para derrubar a transformacao.
    """
    ramos = "\n".join(
        f"    WHEN '{uf}' THEN '{regiao}'" for uf, regiao in sorted(UF_PARA_REGIAO.items())
    )
    return f"CASE {coluna_uf}\n{ramos}\n    ELSE NULL\n  END"
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_regioes.py -v
```

Esperado: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/transform/ pipeline/tests/test_regioes.py
git commit -m "feat(etl): adicionar derivacao de macrorregiao a partir da uf"
```

---

## Task 7: Geração do SELECT canônico

Função **pura**: contrato entra, SQL sai. Nenhum I/O — é o que permite testar a transformação sem uma base de gigabytes.

**Files:**
- Create: `pipeline/src/radar_etl/transform/sql.py`, `pipeline/tests/test_sql.py`

**Interfaces:**
- Consumes: `ContratoEdicao`, `SchemaCanonico` (Task 4); `sql_case_regiao` (Task 6)
- Produces: `montar_select(contrato: ContratoEdicao, canonico: SchemaCanonico, caminho_csv: Path) -> str`; `DerivacaoDesconhecida(Exception)`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_sql.py`:

```python
from pathlib import Path

import duckdb
import pytest

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.transform.sql import DerivacaoDesconhecida, montar_select

CSV_AMOSTRA = (
    "NU_ANO;SG_UF_PROVA;TP_FAIXA_ETARIA;TP_SEXO;TP_COR_RACA;TP_ESCOLA;"
    "TP_DEPENDENCIA_ADM_ESC;IN_TREINEIRO;Q006;Q001;Q002;"
    "TP_PRESENCA_CN;TP_PRESENCA_CH;TP_PRESENCA_LC;TP_PRESENCA_MT;"
    "NU_NOTA_CN;NU_NOTA_CH;NU_NOTA_LC;NU_NOTA_MT;NU_NOTA_REDACAO\n"
    "2025;SC;3;M;1;2;2;0;E;D;F;1;1;1;1;540.1;610.2;588.3;712.4;880.0\n"
    "2025;BA;5;F;3;1;;1;B;A;B;0;0;0;0;;;;;\n"
)


def _preparar(tmp_path: Path) -> Path:
    csv = tmp_path / "MICRODADOS_ENEM_2025.csv"
    csv.write_text(CSV_AMOSTRA, encoding="utf-8")
    return csv


def test_select_produz_as_colunas_canonicas_com_os_tipos_certos(tmp_path):
    csv = _preparar(tmp_path)
    canonico = carregar_canonico()
    contrato = carregar_contrato(2025, canonico)
    contrato.fonte.encoding = "utf-8"

    con = duckdb.connect()
    tabela = con.execute(montar_select(contrato, canonico, csv)).arrow()

    assert set(tabela.column_names) == set(canonico.colunas)
    assert tabela.num_rows == 2


def test_valores_sao_convertidos_e_regiao_e_derivada(tmp_path):
    csv = _preparar(tmp_path)
    canonico = carregar_canonico()
    contrato = carregar_contrato(2025, canonico)
    contrato.fonte.encoding = "utf-8"

    con = duckdb.connect()
    con.execute(f"CREATE TABLE prata AS {montar_select(contrato, canonico, csv)}")

    sul = con.execute("SELECT regiao, nota_mt, treineiro FROM prata WHERE uf_prova = 'SC'").fetchone()
    assert sul == ("Sul", pytest.approx(712.4, abs=0.01), False)

    nordeste = con.execute(
        "SELECT regiao, nota_mt, treineiro FROM prata WHERE uf_prova = 'BA'"
    ).fetchone()
    # Ausente: o INEP grava nota vazia, que precisa virar NULL e nao 0.0.
    assert nordeste[0] == "Nordeste"
    assert nordeste[1] is None
    assert nordeste[2] is True


def test_derivacao_nao_reconhecida_falha_cedo(tmp_path):
    csv = _preparar(tmp_path)
    canonico = carregar_canonico()
    contrato = carregar_contrato(2025, canonico)
    contrato.derivadas = {"regiao": "funcao_inexistente"}

    with pytest.raises(DerivacaoDesconhecida) as erro:
        montar_select(contrato, canonico, csv)

    assert "funcao_inexistente" in str(erro.value)
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_sql.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.transform.sql'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/transform/sql.py`:

```python
from __future__ import annotations

from pathlib import Path

from radar_etl.contracts.modelos import ContratoEdicao, SchemaCanonico
from radar_etl.transform.regioes import sql_case_regiao


class DerivacaoDesconhecida(Exception):
    """O contrato pede uma derivacao que o pipeline nao sabe calcular."""


def _expressao_derivada(nome_funcao: str, contrato: ContratoEdicao) -> str:
    if nome_funcao == "regiao_por_uf":
        return sql_case_regiao(f'"{contrato.mapeamento["uf_prova"]}"')
    raise DerivacaoDesconhecida(
        f"Derivacao '{nome_funcao}' nao implementada. Conhecidas: ['regiao_por_uf']"
    )


def montar_select(contrato: ContratoEdicao, canonico: SchemaCanonico, caminho_csv: Path) -> str:
    """Monta o SELECT que projeta o CSV bruto no schema canonico.

    Le o CSV com todas as colunas como VARCHAR e converte explicitamente com TRY_CAST.
    Isso e deliberado: a inferencia de tipos do DuckDB decide o tipo por amostragem,
    e uma coluna que so tem valor a partir da milionesima linha seria tipada errado.
    TRY_CAST tambem transforma valor invalido em NULL em vez de derrubar a carga.
    """
    projecoes: list[str] = []
    for nome, definicao in canonico.colunas.items():
        if nome in contrato.mapeamento:
            origem = f'"{contrato.mapeamento[nome]}"'
            expressao = f"TRY_CAST(NULLIF(TRIM({origem}), '') AS {definicao.tipo})"
        else:
            expressao = f"TRY_CAST({_expressao_derivada(contrato.derivadas[nome], contrato)} AS {definicao.tipo})"
        projecoes.append(f"  {expressao} AS {nome}")

    colunas = ",\n".join(projecoes)
    caminho = str(caminho_csv).replace("'", "''")
    return (
        f"SELECT\n{colunas}\n"
        f"FROM read_csv(\n"
        f"  '{caminho}',\n"
        f"  delim = '{contrato.fonte.separador}',\n"
        f"  header = true,\n"
        f"  encoding = '{contrato.fonte.encoding}',\n"
        f"  all_varchar = true\n"
        f")"
    )
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_sql.py -v
```

Esperado: 3 passed.

Se `test_valores_sao_convertidos_e_regiao_e_derivada` falhar em `treineiro`, o motivo é que `TRY_CAST('0' AS BOOLEAN)` não converte texto numérico em DuckDB. Nesse caso, tratar `BOOLEAN` como caso especial em `montar_select`, envolvendo a origem em `TRY_CAST(... AS TINYINT) = 1`, e acrescentar um teste que fixe esse comportamento.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/transform/sql.py pipeline/tests/test_sql.py
git commit -m "feat(etl): gerar select canonico a partir do contrato da edicao"
```

---

## Task 8: Portões de qualidade

Implementa os três portões da spec §4-Veracidade. `freshness` é a mitigação direta do risco **R1**.

**Files:**
- Create: `pipeline/src/radar_etl/quality/__init__.py`, `pipeline/src/radar_etl/quality/portoes.py`, `pipeline/tests/test_portoes.py`

**Interfaces:**
- Consumes: `Manifesto` (Task 2), `ContratoEdicao` (Task 4)
- Produces:
  - `Veredito` (dataclass, frozen): `portao: str`, `aprovado: bool`, `mensagem: str`
  - `portao_schema(colunas_no_csv: list[str], contrato: ContratoEdicao) -> Veredito`
  - `portao_volume(linhas_atual: int, linhas_anterior: int | None, tolerancia: float = 0.20) -> Veredito`
  - `portao_freshness(sha256_local: str, sha256_remoto: str | None, last_modified_local: str | None, last_modified_remoto: str | None) -> Veredito`
  - `QualidadeReprovada(Exception)` com atributo `vereditos: list[Veredito]`
  - `avaliar(vereditos: list[Veredito]) -> None`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_portoes.py`:

```python
import pytest

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.quality.portoes import (
    QualidadeReprovada,
    avaliar,
    portao_freshness,
    portao_schema,
    portao_volume,
)


@pytest.fixture
def contrato():
    return carregar_contrato(2025, carregar_canonico())


def test_schema_aprova_quando_todas_as_colunas_de_origem_existem(contrato):
    colunas = list(contrato.mapeamento.values()) + ["COLUNA_EXTRA_IGNORADA"]
    veredito = portao_schema(colunas, contrato)
    assert veredito.aprovado


def test_schema_reprova_e_nomeia_a_coluna_que_sumiu(contrato):
    colunas = [c for c in contrato.mapeamento.values() if c != "NU_NOTA_MT"]
    veredito = portao_schema(colunas, contrato)
    assert not veredito.aprovado
    assert "NU_NOTA_MT" in veredito.mensagem


def test_volume_aprova_variacao_pequena():
    assert portao_volume(4_300_000, 4_200_000).aprovado


def test_volume_reprova_queda_brusca():
    veredito = portao_volume(2_000_000, 4_200_000)
    assert not veredito.aprovado
    assert "52" in veredito.mensagem or "-52" in veredito.mensagem


def test_volume_aprova_na_primeira_edicao_sem_referencia():
    veredito = portao_volume(4_300_000, None)
    assert veredito.aprovado
    assert "primeira" in veredito.mensagem.lower()


def test_freshness_aprova_quando_a_fonte_nao_mudou():
    assert portao_freshness("abc", "abc", "Mon, 01 Sep 2026", "Mon, 01 Sep 2026").aprovado


def test_freshness_reprova_quando_o_inep_republicou_o_arquivo():
    veredito = portao_freshness("abc", "def", "Mon, 01 Sep 2026", "Ter, 10 Out 2026")
    assert not veredito.aprovado
    assert "retific" in veredito.mensagem.lower()


def test_freshness_aprova_com_aviso_quando_nao_ha_hash_remoto():
    # HEAD sem etag: nao da para provar mudanca, mas nao e motivo para abortar.
    veredito = portao_freshness("abc", None, "Mon, 01 Sep 2026", "Mon, 01 Sep 2026")
    assert veredito.aprovado


def test_avaliar_levanta_com_todos_os_vereditos_reprovados(contrato):
    vereditos = [
        portao_schema([c for c in contrato.mapeamento.values() if c != "NU_NOTA_MT"], contrato),
        portao_volume(1_000, 4_200_000),
        portao_freshness("abc", "abc", None, None),
    ]

    with pytest.raises(QualidadeReprovada) as erro:
        avaliar(vereditos)

    reprovados = [v.portao for v in erro.value.vereditos]
    assert set(reprovados) == {"schema", "volume"}


def test_avaliar_nao_levanta_quando_tudo_aprova():
    avaliar([portao_volume(100, 100)])
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_portoes.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.quality'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/quality/__init__.py`: arquivo vazio.

`pipeline/src/radar_etl/quality/portoes.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from radar_etl.contracts.modelos import ContratoEdicao


@dataclass(frozen=True)
class Veredito:
    portao: str
    aprovado: bool
    mensagem: str


class QualidadeReprovada(Exception):
    """Ao menos um portao reprovou. A promocao para a camada Prata nao acontece."""

    def __init__(self, vereditos: list[Veredito]) -> None:
        self.vereditos = vereditos
        detalhes = "\n".join(f"  - [{v.portao}] {v.mensagem}" for v in vereditos)
        super().__init__(f"Portoes de qualidade reprovaram:\n{detalhes}")


def portao_schema(colunas_no_csv: list[str], contrato: ContratoEdicao) -> Veredito:
    """A estrutura da fonte mudou? Coluna a mais e tolerada; coluna a menos, nao."""
    presentes = set(colunas_no_csv)
    exigidas = set(contrato.mapeamento.values())
    ausentes = sorted(exigidas - presentes)

    if ausentes:
        return Veredito(
            "schema",
            False,
            f"Colunas exigidas pelo contrato da edicao {contrato.edicao} "
            f"nao existem no CSV: {ausentes}. Revise o contrato antes de reprocessar.",
        )
    return Veredito("schema", True, f"{len(exigidas)} colunas de origem localizadas.")


def portao_volume(
    linhas_atual: int,
    linhas_anterior: int | None,
    tolerancia: float = 0.20,
) -> Veredito:
    """Houve queda brusca na ingestao?"""
    if linhas_anterior is None:
        return Veredito(
            "volume",
            True,
            f"{linhas_atual:,} linhas. Primeira edicao ingerida: sem referencia para comparar.",
        )

    variacao = (linhas_atual - linhas_anterior) / linhas_anterior
    if abs(variacao) > tolerancia:
        return Veredito(
            "volume",
            False,
            f"Variacao de {variacao:.0%} ({linhas_anterior:,} -> {linhas_atual:,}) "
            f"excede a tolerancia de {tolerancia:.0%}. Exige conferencia manual.",
        )
    return Veredito("volume", True, f"{linhas_atual:,} linhas, variacao de {variacao:+.1%}.")


def portao_freshness(
    sha256_local: str,
    sha256_remoto: str | None,
    last_modified_local: str | None,
    last_modified_remoto: str | None,
) -> Veredito:
    """O arquivo que temos ainda e o que o INEP publica?

    Mitigacao do risco R1: o INEP retifica microdados recem-publicados. Se a fonte
    mudou, reprocessar em silencio alteraria as estatisticas sem explicacao.
    """
    if sha256_remoto is not None and sha256_remoto != sha256_local:
        return Veredito(
            "freshness",
            False,
            "O arquivo na origem mudou desde o download (hash divergente): "
            "o INEP provavelmente retificou a edicao. Rebaixe o Bronze e reprocesse "
            "conscientemente.",
        )

    if (
        last_modified_remoto is not None
        and last_modified_local is not None
        and last_modified_remoto != last_modified_local
    ):
        return Veredito(
            "freshness",
            False,
            f"Last-Modified mudou na origem: '{last_modified_local}' -> "
            f"'{last_modified_remoto}'. Confirme se a edicao foi retificada.",
        )

    return Veredito("freshness", True, "Bronze corresponde ao que a origem publica.")


def avaliar(vereditos: list[Veredito]) -> None:
    reprovados = [v for v in vereditos if not v.aprovado]
    if reprovados:
        raise QualidadeReprovada(reprovados)
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_portoes.py -v
```

Esperado: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/quality/ pipeline/tests/test_portoes.py
git commit -m "feat(etl): adicionar portoes de schema, volume e freshness"
```

---

## Task 9: Escrita Parquet particionada e volumetria

**Files:**
- Create: `pipeline/src/radar_etl/load/__init__.py`, `pipeline/src/radar_etl/load/parquet.py`, `pipeline/tests/test_parquet.py`

**Interfaces:**
- Consumes: `SchemaCanonico` (Task 4)
- Produces:
  - `Volumetria` (dataclass, frozen): `bytes_origem: int`, `bytes_destino: int`, `linhas: int`, e propriedade `reducao_percentual: float`
  - `escrever_prata(con: duckdb.DuckDBPyConnection, select_sql: str, destino: Path, canonico: SchemaCanonico) -> int`
  - `medir(bytes_origem: int, destino: Path, linhas: int) -> Volumetria`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_parquet.py`:

```python
import duckdb

from radar_etl.contracts.modelos import carregar_canonico
from radar_etl.load.parquet import escrever_prata, medir


def _select_sintetico() -> str:
    canonico = carregar_canonico()
    outras = [
        f"NULL::{d.tipo} AS {n}"
        for n, d in canonico.colunas.items()
        if n not in {"ano", "uf_prova", "regiao", "nota_mt"}
    ]
    return f"""
        SELECT 2025::SMALLINT AS ano, uf AS uf_prova, reg AS regiao,
               nota::FLOAT AS nota_mt, {', '.join(outras)}
        FROM (VALUES ('SC', 'Sul', 700.0), ('SC', 'Sul', 500.0), ('BA', 'Nordeste', 600.0))
             AS t(uf, reg, nota)
    """


def test_escreve_parquet_particionado_por_ano_e_uf(tmp_path):
    con = duckdb.connect()
    destino = tmp_path / "silver"

    linhas = escrever_prata(con, _select_sintetico(), destino, carregar_canonico())

    assert linhas == 3
    assert (destino / "ano=2025" / "uf_prova=SC").is_dir()
    assert (destino / "ano=2025" / "uf_prova=BA").is_dir()


def test_parquet_escrito_e_relido_com_os_mesmos_valores(tmp_path):
    con = duckdb.connect()
    destino = tmp_path / "silver"
    escrever_prata(con, _select_sintetico(), destino, carregar_canonico())

    total = duckdb.connect().execute(
        f"SELECT count(*), sum(nota_mt) FROM read_parquet('{destino}/**/*.parquet', hive_partitioning=true)"
    ).fetchone()
    assert total[0] == 3
    assert total[1] == 1800.0


def test_duas_escritas_produzem_bytes_identicos(tmp_path):
    """Idempotencia: e o criterio de pronto da Sprint 1."""
    canonico = carregar_canonico()
    hashes = []
    for rodada in ("a", "b"):
        destino = tmp_path / rodada
        escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico)
        arquivos = sorted(destino.rglob("*.parquet"))
        hashes.append([(p.relative_to(destino).as_posix(), p.read_bytes()) for p in arquivos])

    assert hashes[0] == hashes[1]


def test_volumetria_calcula_a_reducao(tmp_path):
    destino = tmp_path / "silver"
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico())

    volumetria = medir(bytes_origem=1_000_000, destino=destino, linhas=3)

    assert volumetria.bytes_origem == 1_000_000
    assert volumetria.bytes_destino > 0
    assert 0 < volumetria.reducao_percentual < 100
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_parquet.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.load'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/load/__init__.py`: arquivo vazio.

`pipeline/src/radar_etl/load/parquet.py`:

```python
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb

from radar_etl.contracts.modelos import SchemaCanonico


@dataclass(frozen=True)
class Volumetria:
    bytes_origem: int
    bytes_destino: int
    linhas: int

    @property
    def reducao_percentual(self) -> float:
        if self.bytes_origem == 0:
            return 0.0
        return (1 - self.bytes_destino / self.bytes_origem) * 100


def escrever_prata(
    con: duckdb.DuckDBPyConnection,
    select_sql: str,
    destino: Path,
    canonico: SchemaCanonico,
) -> int:
    """Escreve a camada Prata em Parquet+Snappy, particionada e reproduzivel.

    Determinismo e requisito, nao detalhe: threads=1, ordem de insercao preservada
    e ORDER BY ALL garantem que duas execucoes sobre a mesma fonte produzam bytes
    identicos -- que e como a idempotencia do pipeline se torna verificavel.
    """
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True, exist_ok=True)

    con.execute("SET threads TO 1")
    con.execute("SET preserve_insertion_order TO true")

    particoes = ", ".join(canonico.particoes)
    caminho = str(destino).replace("'", "''")
    con.execute(f"""
        COPY (SELECT * FROM ({select_sql}) ORDER BY ALL)
        TO '{caminho}'
        (FORMAT PARQUET, COMPRESSION SNAPPY, PARTITION_BY ({particoes}),
         OVERWRITE_OR_IGNORE, FILENAME_PATTERN 'dados_{{i}}')
    """)

    return con.execute(
        f"SELECT count(*) FROM read_parquet('{caminho}/**/*.parquet', hive_partitioning=true)"
    ).fetchone()[0]


def medir(bytes_origem: int, destino: Path, linhas: int) -> Volumetria:
    bytes_destino = sum(p.stat().st_size for p in destino.rglob("*.parquet"))
    return Volumetria(bytes_origem=bytes_origem, bytes_destino=bytes_destino, linhas=linhas)
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd pipeline && uv run pytest tests/test_parquet.py -v
```

Esperado: 4 passed.

Se `test_duas_escritas_produzem_bytes_identicos` falhar, inspecionar a diferença antes de relaxar o teste — a não-determinação costuma vir de paralelismo residual na escrita, e é exatamente o que o critério de pronto exige eliminar.

- [ ] **Step 5: Commit**

```bash
git add pipeline/src/radar_etl/load/ pipeline/tests/test_parquet.py
git commit -m "feat(etl): escrever camada prata em parquet particionado e reproduzivel"
```

---

## Task 10: Orquestração do `ingest` com idempotência

**Files:**
- Create: `pipeline/src/radar_etl/pipeline.py`, `pipeline/tests/test_pipeline.py`
- Modify: `pipeline/src/radar_etl/cli.py`

**Interfaces:**
- Consumes: tudo das Tasks 2–9
- Produces:
  - `Caminhos` (dataclass, frozen): `raiz: Path`, com propriedades `bronze`, `silver`, `manifests`
  - `executar(edicao: int, caminhos: Caminhos, forcar: bool = False, verificar_origem: bool = True) -> Manifesto`
  - `EdicaoJaProcessada(Exception)`
  - comando `radar-etl ingest --edicao <ano> [--forcar] [--sem-rede]`

- [ ] **Step 1: Escrever o teste que falha**

`pipeline/tests/test_pipeline.py`:

```python
import zipfile

import pytest

from radar_etl.manifesto import Manifesto, sha256_arquivo
from radar_etl.pipeline import Caminhos, EdicaoJaProcessada, executar
from radar_etl.quality.portoes import QualidadeReprovada

CABECALHO = (
    "NU_ANO;SG_UF_PROVA;TP_FAIXA_ETARIA;TP_SEXO;TP_COR_RACA;TP_ESCOLA;"
    "TP_DEPENDENCIA_ADM_ESC;IN_TREINEIRO;Q006;Q001;Q002;"
    "TP_PRESENCA_CN;TP_PRESENCA_CH;TP_PRESENCA_LC;TP_PRESENCA_MT;"
    "NU_NOTA_CN;NU_NOTA_CH;NU_NOTA_LC;NU_NOTA_MT;NU_NOTA_REDACAO"
)
LINHA = "2025;{uf};3;M;1;2;2;0;E;D;F;1;1;1;1;540.1;610.2;588.3;{nota};880.0"


def _montar_zip(caminhos: Caminhos, linhas: int = 50, cabecalho: str = CABECALHO) -> None:
    corpo = "\n".join(
        LINHA.format(uf="SC" if i % 2 else "BA", nota=500 + i) for i in range(linhas)
    )
    caminhos.bronze.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminhos.bronze / "microdados_enem_2025.zip", "w") as z:
        z.writestr("DADOS/MICRODADOS_ENEM_2025.csv", f"{cabecalho}\n{corpo}\n")


@pytest.fixture
def caminhos(tmp_path):
    return Caminhos(raiz=tmp_path)


def test_ingestao_completa_produz_prata_e_manifesto(caminhos):
    _montar_zip(caminhos)

    manifesto = executar(2025, caminhos, verificar_origem=False)

    assert manifesto.linhas_prata == 50
    assert manifesto.bytes_prata > 0
    assert (caminhos.silver / "ano=2025" / "uf_prova=SC").is_dir()
    assert (caminhos.manifests / "enem_2025.json").exists()
    assert manifesto.fonte_sha256 == sha256_arquivo(caminhos.bronze / "microdados_enem_2025.zip")


def test_reexecucao_com_fonte_inalterada_e_pulada(caminhos):
    _montar_zip(caminhos)
    executar(2025, caminhos, verificar_origem=False)

    with pytest.raises(EdicaoJaProcessada):
        executar(2025, caminhos, verificar_origem=False)


def test_forcar_reprocessa_e_produz_bytes_identicos(caminhos):
    _montar_zip(caminhos)
    executar(2025, caminhos, verificar_origem=False)
    primeira = {
        p.relative_to(caminhos.silver).as_posix(): p.read_bytes()
        for p in sorted(caminhos.silver.rglob("*.parquet"))
    }

    executar(2025, caminhos, forcar=True, verificar_origem=False)
    segunda = {
        p.relative_to(caminhos.silver).as_posix(): p.read_bytes()
        for p in sorted(caminhos.silver.rglob("*.parquet"))
    }

    assert primeira == segunda


def test_coluna_ausente_reprova_o_portao_de_schema_e_preserva_a_prata(caminhos):
    _montar_zip(caminhos)
    executar(2025, caminhos, verificar_origem=False)
    prata_boa = {
        p.relative_to(caminhos.silver).as_posix(): p.read_bytes()
        for p in sorted(caminhos.silver.rglob("*.parquet"))
    }

    # Injeta a falha: a edicao volta sem a coluna de nota de matematica.
    _montar_zip(caminhos, cabecalho=CABECALHO.replace(";NU_NOTA_MT", ";NU_NOTA_XX"))

    with pytest.raises(QualidadeReprovada) as erro:
        executar(2025, caminhos, forcar=True, verificar_origem=False)

    assert "NU_NOTA_MT" in str(erro.value)
    prata_depois = {
        p.relative_to(caminhos.silver).as_posix(): p.read_bytes()
        for p in sorted(caminhos.silver.rglob("*.parquet"))
    }
    assert prata_depois == prata_boa, "a Prata anterior tem que sobreviver a uma reprovacao"


def test_queda_brusca_de_volume_reprova(caminhos):
    _montar_zip(caminhos, linhas=100)
    executar(2025, caminhos, verificar_origem=False)

    manifesto = Manifesto.carregar(caminhos.manifests / "enem_2025.json")
    assert manifesto is not None

    _montar_zip(caminhos, linhas=10)
    with pytest.raises(QualidadeReprovada) as erro:
        executar(2025, caminhos, forcar=True, verificar_origem=False)

    assert "volume" in str(erro.value)
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd pipeline && uv run pytest tests/test_pipeline.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'radar_etl.pipeline'`.

- [ ] **Step 3: Implementar**

`pipeline/src/radar_etl/pipeline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.extract.descompactar import extrair_csv
from radar_etl.extract.fonte import baixar, consultar_metadados
from radar_etl.load.parquet import escrever_prata, medir
from radar_etl.manifesto import Manifesto, agora_iso, sha256_arquivo
from radar_etl.quality.portoes import avaliar, portao_freshness, portao_schema, portao_volume
from radar_etl.transform.sql import montar_select


class EdicaoJaProcessada(Exception):
    """Fonte inalterada e Prata ja existente: nao ha o que reprocessar."""


@dataclass(frozen=True)
class Caminhos:
    raiz: Path

    @property
    def bronze(self) -> Path:
        return self.raiz / "bronze"

    @property
    def silver(self) -> Path:
        return self.raiz / "silver"

    @property
    def manifests(self) -> Path:
        return self.raiz / "_manifests"


def _linhas_da_edicao_anterior(caminhos: Caminhos, edicao: int) -> int | None:
    anterior = Manifesto.carregar(caminhos.manifests / f"enem_{edicao - 1}.json")
    return anterior.linhas_prata if anterior else None


def executar(
    edicao: int,
    caminhos: Caminhos,
    forcar: bool = False,
    verificar_origem: bool = True,
) -> Manifesto:
    canonico = carregar_canonico()
    contrato = carregar_contrato(edicao, canonico)

    zip_path = caminhos.bronze / f"microdados_enem_{edicao}.zip"
    manifesto_path = caminhos.manifests / f"enem_{edicao}.json"
    anterior = Manifesto.carregar(manifesto_path)

    if not zip_path.exists():
        baixar(contrato.fonte.url, zip_path)

    sha_local = sha256_arquivo(zip_path)

    if anterior and anterior.fonte_sha256 == sha_local and anterior.linhas_prata and not forcar:
        raise EdicaoJaProcessada(
            f"Edicao {edicao} ja processada a partir da mesma fonte (sha256 {sha_local[:12]}...). "
            f"Use --forcar para reprocessar."
        )

    last_modified_remoto = None
    if verificar_origem:
        remoto = consultar_metadados(contrato.fonte.url)
        last_modified_remoto = remoto.last_modified
        avaliar([
            portao_freshness(
                sha256_local=sha_local,
                sha256_remoto=None,
                last_modified_local=anterior.fonte_last_modified if anterior else None,
                last_modified_remoto=last_modified_remoto,
            )
        ])

    csv_path = extrair_csv(zip_path, contrato.fonte.arquivo_csv, caminhos.bronze / str(edicao))

    con = duckdb.connect()
    leitura = (
        f"read_csv('{str(csv_path).replace(chr(39), chr(39) * 2)}', "
        f"delim = '{contrato.fonte.separador}', header = true, "
        f"encoding = '{contrato.fonte.encoding}', all_varchar = true)"
    )

    # `cursor.description` devolve o cabecalho real sem ler nenhuma linha de dados.
    # Preferido a DESCRIBE: nao depende de parametros preparados dentro de DESCRIBE,
    # que o DuckDB nem sempre aceita.
    cursor = con.execute(f"SELECT * FROM {leitura} LIMIT 0")
    colunas_no_csv = [descricao[0] for descricao in cursor.description]

    # Passada extra sobre o CSV, deliberada: o portao de volume precisa do total
    # ANTES da promocao, e promover para so entao descobrir a queda seria tarde.
    linhas_bronze = con.execute(f"SELECT count(*) FROM {leitura}").fetchone()[0]

    referencia = (anterior.linhas_prata if anterior else None) or _linhas_da_edicao_anterior(
        caminhos, edicao
    )

    avaliar([
        portao_schema(colunas_no_csv, contrato),
        portao_volume(linhas_bronze, referencia),
    ])

    linhas_prata = escrever_prata(
        con, montar_select(contrato, canonico, csv_path), caminhos.silver, canonico
    )
    volumetria = medir(zip_path.stat().st_size, caminhos.silver, linhas_prata)

    manifesto = Manifesto(
        edicao=edicao,
        fonte_url=contrato.fonte.url,
        fonte_sha256=sha_local,
        fonte_bytes=zip_path.stat().st_size,
        fonte_last_modified=last_modified_remoto or (anterior.fonte_last_modified if anterior else None),
        baixado_em=anterior.baixado_em if anterior else agora_iso(),
        csv_bytes=csv_path.stat().st_size,
        linhas_bronze=linhas_bronze,
        linhas_prata=linhas_prata,
        bytes_prata=volumetria.bytes_destino,
        versao_contrato=contrato.versao_contrato,
        processado_em=agora_iso(),
    )
    manifesto.salvar(manifesto_path)
    return manifesto
```

> **Nota sobre a preservação da Prata.** `escrever_prata` só é chamada **depois** de `avaliar`. Como os portões levantam antes da escrita, a Prata anterior sobrevive a uma reprovação sem nenhum mecanismo de rollback — a ordem das operações *é* a garantia. É isso que `test_coluna_ausente_reprova_o_portao_de_schema_e_preserva_a_prata` verifica.

- [ ] **Step 4: Ligar ao CLI**

Substituir o comando `ingest` em `pipeline/src/radar_etl/cli.py`:

```python
@app.command()
def ingest(
    edicao: int = typer.Option(..., help="Ano da edicao do ENEM."),
    raiz: Path = typer.Option(Path("../data"), help="Raiz das camadas de dados."),
    forcar: bool = typer.Option(False, "--forcar", help="Reprocessa mesmo sem mudanca na fonte."),
    sem_rede: bool = typer.Option(False, "--sem-rede", help="Pula a verificacao de freshness."),
) -> None:
    """Ingere uma edicao do ENEM: Bronze -> portoes de qualidade -> Prata."""
    from radar_etl.pipeline import Caminhos, EdicaoJaProcessada, executar
    from radar_etl.quality.portoes import QualidadeReprovada

    try:
        manifesto = executar(
            edicao, Caminhos(raiz=raiz), forcar=forcar, verificar_origem=not sem_rede
        )
    except EdicaoJaProcessada as aviso:
        typer.echo(f"[pulado] {aviso}")
        raise typer.Exit(code=0) from aviso
    except QualidadeReprovada as erro:
        typer.echo(f"[REPROVADO] {erro}", err=True)
        raise typer.Exit(code=1) from erro

    reducao = (1 - manifesto.bytes_prata / manifesto.fonte_bytes) * 100
    typer.echo(
        f"[ok] Edicao {manifesto.edicao}: {manifesto.linhas_prata:,} linhas na Prata | "
        f"{manifesto.fonte_bytes / 1_048_576:.1f} MB -> "
        f"{manifesto.bytes_prata / 1_048_576:.1f} MB ({reducao:.1f}% de reducao)"
    )
```

- [ ] **Step 5: Rodar a suíte inteira**

```bash
cd pipeline && uv run pytest -v && uv run ruff check src tests
```

Esperado: todos os testes passando, ruff sem apontamentos.

- [ ] **Step 6: Commit**

```bash
git add pipeline/src/radar_etl/pipeline.py pipeline/src/radar_etl/cli.py pipeline/tests/test_pipeline.py
git commit -m "feat(etl): orquestrar ingestao com idempotencia por hash da fonte"
```

---

## Task 11: Execução real e artefatos de documentação

Fecha os critérios de pronto da Sprint 1 que dependem de dados reais: volumetria medida e dicionário de dados completo.

**Files:**
- Create: `docs/arquitetura/volumetria.md`, `docs/arquitetura/dicionario_de_dados.md`
- Create: `data/_manifests/enem_2024.json`, `data/_manifests/enem_2025.json` (gerados pela execução)

**Interfaces:**
- Consumes: CLI `radar-etl ingest` (Task 10)
- Produces: artefatos de documentação e manifestos versionados

- [ ] **Step 1: Ingerir as duas edições e cronometrar**

```bash
cd pipeline
uv run radar-etl ingest --edicao 2024 --raiz ../data 2>&1 | tee /tmp/ingest_2024.log
time uv run radar-etl ingest --edicao 2025 --raiz ../data 2>&1 | tee /tmp/ingest_2025.log
```

Se um portão reprovar, **não contornar o portão**: ler a mensagem, corrigir o contrato ou investigar a fonte, e rodar de novo. Um portão que reprova está fazendo o trabalho dele.

- [ ] **Step 2: Comprovar a idempotência**

```bash
cd pipeline
find ../data/silver -name '*.parquet' | sort | xargs sha256sum > /tmp/prata_antes.txt
uv run radar-etl ingest --edicao 2025 --raiz ../data          # deve imprimir "[pulado]"
uv run radar-etl ingest --edicao 2025 --raiz ../data --forcar # deve reprocessar
find ../data/silver -name '*.parquet' | sort | xargs sha256sum > /tmp/prata_depois.txt
diff /tmp/prata_antes.txt /tmp/prata_depois.txt && echo "IDEMPOTENTE: bytes identicos"
```

Esperado: `diff` sem saída e a mensagem `IDEMPOTENTE`. Isto é o critério de pronto nº 2 da Sprint 1.

- [ ] **Step 3: Coletar os números reais para a volumetria**

```bash
cd pipeline
uv run python -c "
from pathlib import Path
from radar_etl.manifesto import Manifesto
raiz = Path('../data')
for ano in (2024, 2025):
    m = Manifesto.carregar(raiz / '_manifests' / f'enem_{ano}.json')
    zip_mb = m.fonte_bytes / 1_048_576
    csv_mb = m.csv_bytes / 1_048_576
    pq_mb = m.bytes_prata / 1_048_576
    print(f'{ano}: zip={zip_mb:.1f}MB csv={csv_mb:.1f}MB parquet={pq_mb:.1f}MB '
          f'linhas={m.linhas_prata:,} reducao_vs_csv={(1-m.bytes_prata/m.csv_bytes)*100:.1f}%')
"
```

- [ ] **Step 4: Escrever `docs/arquitetura/volumetria.md`**

Preencher com os números do Step 3 — **nenhuma célula estimada**:

```markdown
# Volumetria — Camada Bronze → Prata

Medição realizada em <DATA>, com `radar-etl` v0.1.0, contrato v1.
Fonte: manifestos em `data/_manifests/`.

| Edição | ZIP origem | CSV expandido (Bronze) | Parquet+Snappy (Prata) | Linhas | Redução vs. CSV |
|---|---|---|---|---|---|
| 2024 | <X> MB | <Y> MB | <Z> MB | <N> | <R>% |
| 2025 | <X> MB | <Y> MB | <Z> MB | <N> | <R>% |
| **Total** | | | | | |

## Justificativa técnica da redução

A redução vem de três mecanismos combinados, e vale separá-los:

1. **Projeção de colunas.** O schema canônico retém <K> das <M> colunas do CSV original.
   Nenhuma estatística do produto depende das demais — respostas item a item, gabaritos e
   identificadores não são consultados.
2. **Tipagem.** No CSV, `712.4` ocupa 5 bytes como texto; em Parquet é um `FLOAT` de 4 bytes,
   e um código de faixa etária cabe em 1 byte como `TINYINT`.
3. **Compressão colunar Snappy.** Valores do mesmo tipo ficam adjacentes no arquivo, o que
   eleva muito a taxa de compressão em colunas categóricas de baixa cardinalidade
   (UF, sexo, cor/raça, faixa de renda).

Snappy foi escolhido em vez de Gzip por priorizar velocidade de descompressão sobre taxa
máxima: o artefato é escrito 3 vezes por semestre e lido a cada requisição de usuário.

## Tempo de processamento

| Edição | Tempo total | Pico de RAM |
|---|---|---|
| 2025 | <T> | <RAM> |

Medido com `/usr/bin/time -v`. O pico de RAM é a evidência de que a conversão ocorre por
streaming: ele permanece muito abaixo do tamanho do CSV de origem.
```

Medir o pico de RAM com:

```bash
cd pipeline && /usr/bin/time -v uv run radar-etl ingest --edicao 2025 --raiz ../data --forcar 2>&1 | grep -E "Maximum resident|Elapsed"
```

- [ ] **Step 5: Gerar o esqueleto do dicionário de dados**

```bash
cd pipeline
uv run python -c "
from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
c = carregar_canonico()
c24 = carregar_contrato(2024, c); c25 = carregar_contrato(2025, c)
print('| Campo canônico | Tipo | Origem 2024 | Origem 2025 | Descrição |')
print('|---|---|---|---|---|')
for nome, d in c.colunas.items():
    o24 = c24.mapeamento.get(nome) or f'derivada: {c24.derivadas.get(nome)}'
    o25 = c25.mapeamento.get(nome) or f'derivada: {c25.derivadas.get(nome)}'
    print(f'| \`{nome}\` | {d.tipo} | \`{o24}\` | \`{o25}\` | {d.descricao} |')
" > /tmp/dicionario_tabela.md
cat /tmp/dicionario_tabela.md
```

- [ ] **Step 6: Escrever `docs/arquitetura/dicionario_de_dados.md`**

Colar a tabela do Step 5 e acrescentar, à mão:

- **Divergências de schema entre 2024 e 2025** encontradas na Task 5 — qualquer linha em que as colunas de origem difiram. Esta seção é a evidência do risco **R3** e alimenta o Relatório Técnico do AV3.
- **Domínios dos códigos categóricos** (`cor_raca`, `tipo_escola`, `renda_familiar`, `faixa_etaria`, `presenca_*`), copiados do dicionário oficial do INEP incluído no ZIP.
- **Nota de privacidade:** `NU_INSCRICAO` e demais identificadores são descartados na projeção; a camada Prata não contém identificador de participante.

- [ ] **Step 7: Verificar os critérios de pronto da Sprint 1**

```bash
cd pipeline
uv run pytest -v                                     # 1. suite verde
uv run ruff check src tests                          # 2. lint limpo
ls ../data/_manifests/                               # 3. manifestos das duas edicoes
grep -c "|" ../docs/arquitetura/volumetria.md        # 4. volumetria preenchida
git status --short ../data/                          # 5. nenhum csv/parquet/zip rastreado
```

O item 5 tem que listar **apenas** arquivos sob `data/_manifests/`. Qualquer `.csv`, `.parquet` ou `.zip` aparecendo ali significa `.gitignore` incorreto — voltar à Task 1.

- [ ] **Step 8: Commit**

```bash
git add data/_manifests/ docs/arquitetura/volumetria.md docs/arquitetura/dicionario_de_dados.md
git commit -m "docs(etl): registrar volumetria medida e dicionario de dados"
```

- [ ] **Step 9: Abrir o Pull Request**

```bash
git push -u origin feat/etl-fundacao-de-dados
gh pr create --title "Sprint 1: fundacao de dados (Bronze -> Prata)" --body "$(cat <<'CORPO'
## O que muda
Pipeline de ingestao dos microdados do ENEM 2024 e 2025: extracao com verificacao
de integridade, contratos de schema por edicao, transformacao via DuckDB, portoes
de qualidade e escrita em Parquet particionado.

## Por que
Sprint 1 do PLANO_IMPLEMENTACAO.md. Estabelece a camada Prata da qual dependem a
API estatistica e a camada Ouro.

## Como foi verificado
- Suite completa verde (`uv run pytest`), ruff limpo
- Idempotencia comprovada: reexecucao com fonte inalterada e pulada; `--forcar`
  produz bytes identicos
- Portoes exercitados com falha injetada (coluna ausente, queda de volume), com
  a camada Prata anterior preservada
- Volumetria medida sobre as duas edicoes reais e registrada em
  `docs/arquitetura/volumetria.md`

## Revisao
Atencao especial ao `montar_select` (`transform/sql.py`) e aos limiares dos
portoes (`quality/portoes.py`).
CORPO
)"
```

---

## Checklist de Conclusão da Sprint 1

Mapeia diretamente os critérios de pronto de `PLANO_IMPLEMENTACAO.md` §7:

- [ ] `radar-etl ingest --edicao 2025` executa fim a fim sem estouro de memória *(Task 11, Step 1)*
- [ ] Idempotência comprovada: hash idêntico, SHA-256 no manifesto, reexecução pulada *(Task 11, Step 2)*
- [ ] Portões abortam sob falha injetada *(Task 10, Steps 1 e 3)*
- [ ] `volumetria.md` com redução **medida** *(Task 11, Step 4)*
- [ ] Dicionário cobre 100% do schema canônico *(Task 11, Step 6)*
- [ ] Divergências de schema 2024 × 2025 documentadas *(Task 11, Step 6)*
- [ ] `.gitignore` impede versionamento de dados *(Task 1, Step 1; verificado na Task 11, Step 7)*
