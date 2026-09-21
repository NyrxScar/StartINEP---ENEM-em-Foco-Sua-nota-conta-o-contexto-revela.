"""Construtor de consultas DuckDB do nucleo analitico do Radar ENEM.

Este modulo e uma camada **pura e inspecionavel** de montagem de SQL: cada
funcao ``construir_*`` e uma funcao pura que devolve ``(sql, params)`` (um
:class:`ConsultaSQL`), sem tocar em nenhuma conexao. A execucao fica isolada
nas funcoes ``executar_*``, para que o SQL gerado possa ser inspecionado por
testes de unidade/propriedade (Property 6, task 5.2) sem precisar de um banco.

Garantias de design honradas aqui:

* **Agregacao-only (Req 6.4 / 9.1)** — a projecao que cruza a fronteira do
  Motor_de_Consulta contem *apenas* expressoes agregadas (``count``, ``min``,
  ``max``, ``quantile_cont``, o percentil por rank, e as faixas do histograma
  via ``GROUP BY``). Nenhuma coluna de linha individual sai do DuckDB.
* **Exclusao de nulos (Req 1.2)** — todo recorte filtra ``nota_<area> IS NOT
  NULL`` antes de qualquer agregacao.
* **Recorte conjuntivo (Req 1.4)** — cada filtro de :class:`~radar_api.modelos.Recorte`
  vira um predicado ligado por ``AND``.
* **Partition pruning (Req 6.2)** — o segmento ``ano=<edicao>`` no caminho do
  ``read_parquet`` restringe a leitura a uma unica particao de ano; quando o
  recorte inclui ``uf_prova`` (``Dimensao.UF``), o predicado correspondente
  tambem induz pruning por ``uf_prova``.
* **Sem materializar a Edicao inteira (Req 6.1)** — le direto do Parquet
  particionado via ``read_parquet(..., hive_partitioning=1)``.

Seguranca de injecao: nomes de coluna vem *exclusivamente* dos enums
:class:`~radar_api.modelos.Area`/:class:`~radar_api.modelos.Dimensao` (nao de
entrada do usuario); a ``edicao`` e coagida a ``int``; a raiz da *silver* tem
aspas simples escapadas antes de entrar no literal de caminho; e **todos** os
valores de filtro, a nota do usuario e a largura de faixa sao passados por
*parameter binding* (``?``) do DuckDB, nunca interpolados no texto do SQL.
"""

from __future__ import annotations

import math
import os
from typing import Any, NamedTuple

import duckdb

from radar_api.modelos import Area, Dimensao, Recorte

# Largura padrao (em pontos) de cada faixa do histograma de distribuicao.
LARGURA_FAIXA_PADRAO = 100.0

# Teto de grupos devolvidos por uma exploracao. Dimensionado para o maior
# dominio real (``municipio_prova``, com mais de mil valores distintos por
# Edicao) permanecer util sem que a resposta cresca sem limite.
LIMITE_GRUPOS_PADRAO = 200


class ConsultaSQL(NamedTuple):
    """Par ``(sql, params)`` produzido por um construtor de consulta.

    E uma ``NamedTuple`` (portanto tambem uma ``tuple``): pode ser
    desempacotada como ``sql, params = consulta`` ou acessada por atributo
    (``consulta.sql`` / ``consulta.params``), e repassada as funcoes
    ``executar_*`` via ``executar_agregada(con, *consulta)``.

    Attributes:
        sql: Texto SQL com marcadores posicionais ``?`` para os valores.
        params: Valores a vincular, na ordem textual em que os ``?`` aparecem.
    """

    sql: str
    params: list[Any]


def _clausula_from(silver_root: str | os.PathLike[str], edicao: int) -> str:
    """Monta a expressao ``read_parquet(...)`` restrita a ``ano=<edicao>``.

    O literal ``ano=<edicao>`` no caminho e o que induz o *partition pruning*
    por ano (Req 6.2) e permanece visivel no SQL para inspecao por testes.

    Args:
        silver_root: Raiz da camada *silver* (Parquet particionado). Aceita
            ``str`` ou ``os.PathLike``; nao e hardcoded.
        edicao: Ano da Edicao; coagido a ``int`` para eliminar qualquer
            superficie de injecao pelo caminho.

    Returns:
        A clausula ``read_parquet('<raiz>/ano=<edicao>/**/*.parquet',
        hive_partitioning = 1)`` pronta para uso em ``FROM``.
    """
    raiz = os.fspath(silver_root).rstrip("/").replace("'", "''")
    padrao = f"{raiz}/ano={int(edicao)}/**/*.parquet"
    return f"read_parquet('{padrao}', hive_partitioning = 1)"


def _predicados_recorte(recorte: Recorte) -> tuple[list[str], list[Any]]:
    """Traduz os filtros de um Recorte em predicados parametrizados.

    Cada entrada ``(dimensao, valor)`` vira ``CAST(<coluna> AS VARCHAR) = ?``,
    onde ``<coluna>`` e o nome fisico da coluna (o *valor* do enum
    :class:`~radar_api.modelos.Dimensao`). O ``CAST`` para ``VARCHAR`` torna o
    predicado robusto para colunas de qualquer tipo fisico (VARCHAR, TINYINT,
    etc.), ja que os valores de filtro chegam como texto. Os valores sao
    devolvidos para *binding* posicional (nunca interpolados).

    Os predicados sao emitidos em ordem canonica (ordenados pelo nome da
    coluna) para tornar o SQL deterministico e facilmente inspecionavel,
    independentemente da ordem de insercao no dicionario de filtros.

    Args:
        recorte: Recorte com os filtros conjuntivos (pode ser vazio).

    Returns:
        Uma tupla ``(condicoes, params)``: a lista de fragmentos SQL e a lista
        de valores a vincular, na mesma ordem.
    """
    condicoes: list[str] = []
    params: list[Any] = []
    for dimensao, valor in sorted(recorte.filtros.items(), key=lambda kv: kv[0].value):
        condicoes.append(f"CAST({dimensao.value} AS VARCHAR) = ?")
        params.append(valor)
    return condicoes, params


def _clausula_where(coluna_nota: str, recorte: Recorte) -> tuple[str, list[Any]]:
    """Monta a clausula ``WHERE`` da CTE ``base`` e seus parametros.

    Sempre inicia por ``<coluna_nota> IS NOT NULL`` (Req 1.2) e adiciona, de
    forma conjuntiva (Req 1.4), um predicado por filtro do Recorte.

    Args:
        coluna_nota: Nome fisico da coluna de nota (ex.: ``nota_cn``).
        recorte: Recorte com os filtros a aplicar.

    Returns:
        Uma tupla ``(where, params)`` com o texto da clausula (sem a palavra
        ``WHERE``) e os valores a vincular.
    """
    condicoes_filtro, params = _predicados_recorte(recorte)
    condicoes = [f"{coluna_nota} IS NOT NULL", *condicoes_filtro]
    return "\n      AND ".join(condicoes), params


def construir_consulta_agregada(
    silver_root: str | os.PathLike[str],
    edicao: int,
    area: Area,
    recorte: Recorte,
    nota_usuario: float,
) -> ConsultaSQL:
    """Constroi a consulta agregada principal de analise (agregacao-only).

    Produz um SQL cuja projecao externa contem **apenas** agregados: o tamanho
    amostral (``count``), os quantis (``min``, Q1, mediana, Q3, ``max`` via
    ``quantile_cont``) e o Percentil da ``nota_usuario`` calculado por rank
    deterministico com interpolacao de empates::

        100 * (#{nota < u} + 0.5 * #{nota = u}) / #{total}

    A leitura vem de ``read_parquet('<silver_root>/ano=<edicao>/**/*.parquet',
    hive_partitioning=1)`` (pruning por ``ano``; e por ``uf_prova`` quando o
    recorte inclui ``Dimensao.UF``), sempre filtrando ``nota_<area> IS NOT
    NULL`` (Req 1.2) e aplicando os filtros do recorte conjuntivamente (Req
    1.4). Nenhuma coluna de linha individual cruza a fronteira do DuckDB (Req
    6.4 / 9.1).

    Args:
        silver_root: Raiz da camada *silver* (nao hardcoded).
        edicao: Ano da Edicao a consultar (dirige o pruning por ``ano``).
        area: Area de avaliacao; mapeia para a coluna ``nota_<area>``.
        recorte: Filtros conjuntivos do Recorte (pode ser vazio = sem recorte).
        nota_usuario: Nota informada, cujo Percentil sera calculado; vinculada
            por parametro (duas vezes, para os cortes ``<`` e ``=``).

    Returns:
        Um :class:`ConsultaSQL` com o SQL e os parametros na ordem: primeiro os
        valores dos filtros do recorte (ordem canonica), depois a
        ``nota_usuario`` duas vezes.
    """
    coluna_nota = f"nota_{area.value}"
    origem = _clausula_from(silver_root, edicao)
    where, params_filtros = _clausula_where(coluna_nota, recorte)

    sql = (
        "WITH base AS (\n"
        f"    SELECT {coluna_nota} AS nota\n"
        f"    FROM {origem}\n"
        f"    WHERE {where}\n"
        ")\n"
        "SELECT\n"
        "    count(*) AS tamanho_amostral,\n"
        "    min(nota) AS q_min,\n"
        "    quantile_cont(nota, 0.25) AS q1,\n"
        "    quantile_cont(nota, 0.5) AS mediana,\n"
        "    quantile_cont(nota, 0.75) AS q3,\n"
        "    max(nota) AS q_max,\n"
        "    100.0 * (\n"
        "        sum(CASE WHEN nota < ? THEN 1 ELSE 0 END)\n"
        "        + 0.5 * sum(CASE WHEN nota = ? THEN 1 ELSE 0 END)\n"
        "    ) / count(*) AS percentil\n"
        "FROM base"
    )
    params: list[Any] = [*params_filtros, nota_usuario, nota_usuario]
    return ConsultaSQL(sql, params)


def construir_consulta_histograma(
    silver_root: str | os.PathLike[str],
    edicao: int,
    area: Area,
    recorte: Recorte,
    largura_faixa: float = LARGURA_FAIXA_PADRAO,
) -> ConsultaSQL:
    """Constroi a consulta do histograma de faixas (agregacao-only).

    Agrupa as notas em faixas de largura fixa via ``floor(nota / largura)`` e
    conta as ocorrencias por faixa. A saida traz, por faixa, o intervalo
    ``[limite_inferior, limite_superior)`` e a ``contagem`` — todos derivados
    de agrupamento/``count`` (Req 6.4 / 9.1). Aplica os mesmos filtros de nulo
    e de recorte da consulta agregada.

    Args:
        silver_root: Raiz da camada *silver* (nao hardcoded).
        edicao: Ano da Edicao a consultar.
        area: Area de avaliacao; mapeia para ``nota_<area>``.
        recorte: Filtros conjuntivos do Recorte (pode ser vazio).
        largura_faixa: Largura (em pontos) de cada faixa; deve ser um numero
            finito e positivo. Vinculada por parametro.

    Returns:
        Um :class:`ConsultaSQL` com o SQL e os parametros na ordem: valores dos
        filtros do recorte, seguidos da ``largura_faixa`` (uma vez no calculo
        do indice e uma vez em cada limite da faixa).

    Raises:
        ValueError: Se ``largura_faixa`` nao for um numero finito e positivo.
    """
    if not math.isfinite(largura_faixa) or largura_faixa <= 0:
        raise ValueError("largura_faixa deve ser um numero finito e positivo.")

    coluna_nota = f"nota_{area.value}"
    origem = _clausula_from(silver_root, edicao)
    where, params_filtros = _clausula_where(coluna_nota, recorte)

    sql = (
        "WITH base AS (\n"
        f"    SELECT {coluna_nota} AS nota\n"
        f"    FROM {origem}\n"
        f"    WHERE {where}\n"
        "),\n"
        "faixas AS (\n"
        "    SELECT floor(nota / ?) AS indice, count(*) AS contagem\n"
        "    FROM base\n"
        "    GROUP BY indice\n"
        ")\n"
        "SELECT\n"
        "    indice * ? AS limite_inferior,\n"
        "    (indice + 1) * ? AS limite_superior,\n"
        "    contagem\n"
        "FROM faixas\n"
        "ORDER BY limite_inferior"
    )
    params: list[Any] = [*params_filtros, largura_faixa, largura_faixa, largura_faixa]
    return ConsultaSQL(sql, params)


def executar_agregada(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
) -> dict[str, Any]:
    """Executa a consulta agregada e devolve os agregados como um ``dict``.

    A consulta agregada nao tem ``GROUP BY``, logo sempre retorna exatamente
    uma linha (mesmo sobre entrada vazia: ``tamanho_amostral = 0`` e os demais
    agregados ``None``). Apenas agregados sao devolvidos — nenhuma linha
    individual da *silver*.

    Args:
        con: Conexao DuckDB ja aberta (o ciclo de vida e do chamador).
        sql: SQL produzido por :func:`construir_consulta_agregada`.
        params: Parametros correspondentes, na ordem dos ``?``.

    Returns:
        Um ``dict`` mapeando cada alias de agregado
        (``tamanho_amostral``, ``q_min``, ``q1``, ``mediana``, ``q3``,
        ``q_max``, ``percentil``) ao valor calculado.
    """
    cursor = con.execute(sql, params)
    colunas = [descricao[0] for descricao in cursor.description]
    linha = cursor.fetchone()
    if linha is None:  # defensivo: nao ocorre para agregacao sem GROUP BY
        return dict.fromkeys(colunas)
    return dict(zip(colunas, linha, strict=True))


def executar_histograma(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """Executa a consulta de histograma e devolve as faixas como lista de dicts.

    Cada elemento representa uma faixa agregada
    (``limite_inferior``, ``limite_superior``, ``contagem``) — nenhuma linha
    individual da *silver* e exposta.

    Args:
        con: Conexao DuckDB ja aberta (o ciclo de vida e do chamador).
        sql: SQL produzido por :func:`construir_consulta_histograma`.
        params: Parametros correspondentes, na ordem dos ``?``.

    Returns:
        Uma lista de ``dict`` (uma por faixa nao vazia), ordenada por
        ``limite_inferior``.
    """
    cursor = con.execute(sql, params)
    colunas = [descricao[0] for descricao in cursor.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cursor.fetchall()]


__all__ = [
    "LARGURA_FAIXA_PADRAO",
    "ConsultaSQL",
    "construir_consulta_agregada",
    "construir_consulta_histograma",
    "executar_agregada",
    "executar_histograma",
]


def construir_consulta_exploracao(
    silver_root: str | os.PathLike[str],
    edicao: int,
    area: Area,
    dimensao: Dimensao,
    recorte: Recorte,
    *,
    limite_grupos: int = LIMITE_GRUPOS_PADRAO,
) -> ConsultaSQL:
    """Monta a consulta que agrega a Area por valor de uma Dimensao.

    Uma unica varredura com ``GROUP BY`` responde o que, de outra forma, exigiria
    uma requisicao por valor da Dimensao — 27 para UF, mais de mil para municipio.
    A *silver* e lida em modo agregacao-only: nenhuma linha individual cruza a
    fronteira, apenas contagens e quantis por grupo (Req 6.4/9.1).

    **Grupos nulos ficam de fora.** ``<dimensao> IS NOT NULL`` no ``WHERE`` evita
    um grupo ``NULL`` que, em Dimensoes como ``localizacao_escola`` (preenchida
    so para quem declara vinculo escolar), seria o maior da lista e nao
    significaria "um valor", e sim "a coluna nao se aplica a estas pessoas".

    **O limite e por seguranca de resposta, nao por privacidade.** ``municipio_prova``
    tem mais de mil valores distintos; devolver todos de uma vez produziria uma
    resposta grande sem utilidade pratica. A ordenacao e por tamanho do grupo
    decrescente, entao o corte cai sempre nos grupos menores — que a guarda de
    limiar suprimiria de qualquer forma.

    Args:
        silver_root: Raiz da camada *silver* (Parquet particionado).
        edicao: Ano da Edicao a explorar.
        area: Area de avaliacao; mapeia para a coluna ``nota_<area>``.
        dimensao: Dimensao cujos valores viram os grupos.
        recorte: Filtros conjuntivos aplicados **antes** do agrupamento, de modo
            que a exploracao acontece dentro do recorte escolhido.
        limite_grupos: Numero maximo de grupos devolvidos.

    Returns:
        Um :class:`ConsultaSQL` cujas linhas trazem ``valor``, ``tamanho_amostral``
        e os quantis do grupo, do maior grupo para o menor.
    """
    coluna_nota = f"nota_{area.value}"
    coluna_dim = dimensao.value
    origem = _clausula_from(silver_root, edicao)
    where, params_filtros = _clausula_where(coluna_nota, recorte)

    sql = (
        "WITH base AS (\n"
        f"    SELECT CAST({coluna_dim} AS VARCHAR) AS valor, {coluna_nota} AS nota\n"
        f"    FROM {origem}\n"
        f"    WHERE {where}\n"
        f"      AND {coluna_dim} IS NOT NULL\n"
        ")\n"
        "SELECT\n"
        "    valor,\n"
        "    count(*) AS tamanho_amostral,\n"
        "    min(nota) AS q_min,\n"
        "    quantile_cont(nota, 0.25) AS q1,\n"
        "    quantile_cont(nota, 0.5) AS mediana,\n"
        "    quantile_cont(nota, 0.75) AS q3,\n"
        "    max(nota) AS q_max\n"
        "FROM base\n"
        "GROUP BY valor\n"
        # Desempate por valor: sem ele, grupos de mesmo tamanho sairiam em ordem
        # arbitraria e a mesma consulta poderia responder diferente entre chamadas.
        "ORDER BY tamanho_amostral DESC, valor ASC\n"
        "LIMIT ?"
    )
    params: list[Any] = [*params_filtros, int(limite_grupos)]
    return ConsultaSQL(sql, params)


def executar_exploracao(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """Executa a consulta de exploracao e devolve uma linha de agregados por grupo.

    Args:
        con: Conexao DuckDB ja aberta (o ciclo de vida e do chamador).
        sql: SQL produzido por :func:`construir_consulta_exploracao`.
        params: Parametros correspondentes, na ordem dos ``?``.

    Returns:
        Uma lista de ``dict``, um por valor da Dimensao, do maior grupo para o
        menor. Lista vazia quando o recorte nao tem nenhuma linha elegivel.
    """
    cursor = con.execute(sql, params)
    colunas = [descricao[0] for descricao in cursor.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cursor.fetchall()]
