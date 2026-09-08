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
    ausentes: dict[str, str] = {}


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
    exatamente as colunas canonicas, sem faltar nenhuma e sem inventar nenhuma. Cada
    coluna canonica precisa aparecer em exatamente um dos tres conjuntos -
    `mapeamento`, `derivadas` ou `ausentes`. Uma edicao que nao consegue fornecer uma
    coluna declara isso em `ausentes` com uma justificativa real; nunca em silencio.
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

    mapeadas = set(contrato.mapeamento)
    derivadas = set(contrato.derivadas)
    ausentes = set(contrato.ausentes)
    esperadas = set(canonico.colunas)

    duplicadas = (
        (mapeadas & derivadas) | (mapeadas & ausentes) | (derivadas & ausentes)
    )
    if duplicadas:
        raise ContratoInvalido(
            f"{caminho.name} declara a(s) coluna(s) {sorted(duplicadas)} em mais de "
            "um dos conjuntos mapeamento/derivadas/ausentes. Uma coluna so pode "
            "aparecer em um deles."
        )

    cobertas = mapeadas | derivadas | ausentes

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

    sem_justificativa = [
        coluna for coluna, texto in contrato.ausentes.items() if not texto.strip()
    ]
    if sem_justificativa:
        raise ContratoInvalido(
            f"{caminho.name} declara ausente sem justificativa: {sorted(sem_justificativa)}"
        )

    return contrato
