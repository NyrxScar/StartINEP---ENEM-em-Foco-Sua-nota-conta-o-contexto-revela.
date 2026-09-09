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

    Le tudo como VARCHAR e converte com TRY_CAST explicito. E deliberado: a inferencia
    de tipos do DuckDB decide por amostragem, e uma coluna que so tem valor a partir da
    milionesima linha seria tipada errado. TRY_CAST tambem transforma valor invalido em
    NULL em vez de derrubar a carga.

    Coluna que a edicao nao fornece sai como NULL tipado, na mesma posicao: a camada
    Prata tem o mesmo formato em toda edicao, e quem consulta nao precisa saber qual
    edicao publicou o que.
    """
    projecoes: list[str] = []
    for nome, definicao in canonico.colunas.items():
        if nome in contrato.mapeamento:
            origem = f'"{contrato.mapeamento[nome]}"'
            expressao = f"TRY_CAST(NULLIF(TRIM({origem}), '') AS {definicao.tipo})"
        elif nome in contrato.derivadas:
            derivada = _expressao_derivada(contrato.derivadas[nome], contrato)
            expressao = f"TRY_CAST({derivada} AS {definicao.tipo})"
        else:
            expressao = f"CAST(NULL AS {definicao.tipo})"
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
