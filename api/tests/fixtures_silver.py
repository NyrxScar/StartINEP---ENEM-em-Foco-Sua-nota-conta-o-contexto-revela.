"""Auxiliar de *fixtures* da camada *silver* para os testes do Radar ENEM.

Este modulo **nao** e um modulo de teste (nenhuma funcao ``test_*``): e um
utilitario *importavel* que escreve Parquet minusculos e particionados no mesmo
layout Hive da *silver* real (``ano=<edicao>/uf_prova=<UF>/dados_0.parquet``),
para que os testes do nucleo analitico (``analisar`` e as propriedades P1/P2/P3
das tasks 5.4/5.5/5.6) construam uma :class:`~radar_api.config.Config` apontando
para um diretorio temporario, montem um :class:`~radar_api.catalogo.Catalogo` e
exercitem a analise de forma **deterministica**, sem depender dos dados reais.

Fidelidade ao contrato de dados:

* As colunas *fisicas* escritas e seus tipos espelham a *silver* real
  (:data:`COLUNAS_FISICAS`) — ``regiao``/``renda_familiar``/``escolaridade_*``
  como ``VARCHAR``; ``cor_raca``/``tipo_escola``/``dependencia_adm_escola`` como
  ``TINYINT``; ``nota_*`` como ``FLOAT`` anulavel.
* ``ano`` e ``uf_prova`` **nao** sao colunas fisicas: derivam do caminho quando
  lidos com ``hive_partitioning=1`` (exatamente como na *silver* real). Por
  isso, um Recorte por ``Dimensao.UF`` filtra a coluna derivada do caminho, e um
  Recorte por ``Dimensao.REGIAO`` filtra a coluna fisica ``regiao``.

Cada arquivo escrito contem **todas** as colunas fisicas (valores ausentes viram
``NULL``), garantindo um schema uniforme entre particoes — o que evita
divergencias de schema ao ler ``ano=<edicao>/**/*.parquet`` com uniao por nome.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb

# Colunas fisicas da *silver* (nome -> tipo DuckDB), na ordem de escrita.
# NAO inclui ``ano``/``uf_prova``: essas sao derivadas do caminho Hive.
COLUNAS_FISICAS: tuple[tuple[str, str], ...] = (
    ("regiao", "VARCHAR"),
    ("municipio_prova", "VARCHAR"),
    ("codigo_escola", "VARCHAR"),
    ("localizacao_escola", "TINYINT"),
    ("faixa_etaria", "TINYINT"),
    ("sexo", "VARCHAR"),
    ("cor_raca", "TINYINT"),
    ("tipo_escola", "TINYINT"),
    ("dependencia_adm_escola", "TINYINT"),
    ("treineiro", "BOOLEAN"),
    ("renda_familiar", "VARCHAR"),
    ("escolaridade_pai", "VARCHAR"),
    ("escolaridade_mae", "VARCHAR"),
    ("nota_cn", "FLOAT"),
    ("nota_ch", "FLOAT"),
    ("nota_lc", "FLOAT"),
    ("nota_mt", "FLOAT"),
    ("nota_redacao", "FLOAT"),
)

_NOMES_COLUNAS: tuple[str, ...] = tuple(nome for nome, _ in COLUNAS_FISICAS)

# Mapa UF -> regiao (mesmas 5 macrorregioes que o ETL deriva de ``uf_prova``).
# Usado para preencher ``regiao`` automaticamente quando a linha nao a informa,
# tornando Recortes por ``Dimensao.REGIAO`` naturais nos testes.
REGIAO_POR_UF: dict[str, str] = {
    # Norte
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    # Nordeste
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    # Centro-Oeste
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    # Sudeste
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    # Sul
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}


def _linha_completa(linha: Mapping[str, Any], uf: str) -> list[Any]:
    """Normaliza uma linha em uma tupla posicional de todas as colunas fisicas.

    Colunas ausentes viram ``None`` (``NULL`` no Parquet). ``regiao`` e
    preenchida a partir de :data:`REGIAO_POR_UF` quando a linha nao a fornece
    (mas continua sobrescrivivel explicitamente, inclusive para ``None``).

    Args:
        linha: Mapeamento coluna -> valor (subconjunto de :data:`COLUNAS_FISICAS`).
        uf: UF da particao, usada para inferir ``regiao`` quando ausente.

    Returns:
        Lista de valores na ordem de :data:`COLUNAS_FISICAS`.

    Raises:
        ValueError: A linha referencia uma coluna que nao existe na *silver*
            (ex.: ``uf_prova``/``ano``, que sao derivadas do caminho).
    """
    desconhecidas = set(linha) - set(_NOMES_COLUNAS)
    if desconhecidas:
        raise ValueError(
            f"Colunas desconhecidas na linha da fixture: {sorted(desconhecidas)}. "
            f"Note que 'ano'/'uf_prova' derivam do caminho Hive e nao sao colunas fisicas."
        )
    valores: dict[str, Any] = dict(linha)
    if "regiao" not in valores:
        valores["regiao"] = REGIAO_POR_UF.get(uf)
    return [valores.get(nome) for nome in _NOMES_COLUNAS]


def _escrever_particao(
    con: duckdb.DuckDBPyConnection,
    destino: Path,
    linhas: Sequence[Mapping[str, Any]],
    uf: str,
) -> None:
    """Escreve uma unica particao ``uf_prova=<uf>`` como ``dados_0.parquet``.

    Cria uma tabela temporaria com o schema fisico exato (tipos de
    :data:`COLUNAS_FISICAS`), insere as linhas normalizadas e faz ``COPY`` para
    Parquet. Uma particao sem linhas ainda gera um Parquet valido (schema
    preservado, zero linhas), util para exercitar o caso de amostra vazia.
    """
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "dados_0.parquet"

    ddl = ", ".join(f'"{nome}" {tipo}' for nome, tipo in COLUNAS_FISICAS)
    con.execute("DROP TABLE IF EXISTS _fixture_tmp")
    con.execute(f"CREATE TABLE _fixture_tmp ({ddl})")
    try:
        registros = [_linha_completa(linha, uf) for linha in linhas]
        if registros:
            marcadores = ", ".join("?" for _ in COLUNAS_FISICAS)
            con.executemany(
                f"INSERT INTO _fixture_tmp VALUES ({marcadores})", registros
            )
        caminho_sql = arquivo.as_posix().replace("'", "''")
        con.execute(f"COPY _fixture_tmp TO '{caminho_sql}' (FORMAT PARQUET)")
    finally:
        con.execute("DROP TABLE IF EXISTS _fixture_tmp")


def escrever_silver_fixture(
    raiz: Path,
    linhas_por_particao: Mapping[tuple[int, str], Sequence[Mapping[str, Any]]],
) -> None:
    """Escreve uma *silver* de teste particionada por ``(edicao, uf)``.

    Para cada chave ``(edicao, uf)``, escreve
    ``<raiz>/ano=<edicao>/uf_prova=<uf>/dados_0.parquet`` com as linhas
    fornecidas. Cada linha e um mapeamento coluna -> valor cobrindo qualquer
    subconjunto de :data:`COLUNAS_FISICAS`; colunas omitidas ficam ``NULL`` e
    ``regiao`` e inferida da UF quando ausente.

    Args:
        raiz: Diretorio-raiz da *silver* de teste (ex.: ``tmp_path``). Sera a
            ``silver_root`` da :class:`~radar_api.config.Config` do teste.
        linhas_por_particao: Mapa ``(edicao, uf) -> lista de linhas``. Uma lista
            vazia cria a particao com zero linhas (Parquet valido e vazio).

    Example:
        >>> escrever_silver_fixture(
        ...     tmp_path,
        ...     {(2023, "SP"): [{"nota_cn": 500.0, "tipo_escola": 1}]},
        ... )
    """
    con = duckdb.connect()
    try:
        for (edicao, uf), linhas in linhas_por_particao.items():
            destino = raiz / f"ano={int(edicao)}" / f"uf_prova={uf}"
            _escrever_particao(con, destino, linhas, uf)
    finally:
        con.close()


def escrever_silver(
    raiz: Path,
    edicao: int,
    linhas: Sequence[Mapping[str, Any]],
    *,
    uf_padrao: str = "SP",
) -> None:
    """Atalho: escreve uma unica Edicao, agrupando as linhas por UF.

    Conveniencia sobre :func:`escrever_silver_fixture` para o caso comum de uma
    so Edicao. Cada linha pode conter uma chave ``"uf_prova"`` indicando a sua
    particao; linhas sem ela caem em ``uf_padrao``. A chave ``"uf_prova"`` e
    consumida para o roteamento de particao e **nao** e escrita como coluna
    fisica (coerente com a *silver* real, onde a UF deriva do caminho).

    Args:
        raiz: Diretorio-raiz da *silver* de teste.
        edicao: Ano da Edicao a escrever.
        linhas: Linhas da Edicao; cada uma um mapeamento coluna -> valor,
            opcionalmente com ``"uf_prova"`` para escolher a particao.
        uf_padrao: UF usada para as linhas que nao informam ``"uf_prova"``.
    """
    por_particao: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for linha in linhas:
        dados = dict(linha)
        uf = str(dados.pop("uf_prova", uf_padrao))
        por_particao.setdefault((edicao, uf), []).append(dados)
    # Garante ao menos a particao padrao (Parquet vazio) quando nao ha linhas.
    if not por_particao:
        por_particao[(edicao, uf_padrao)] = []
    escrever_silver_fixture(raiz, por_particao)


__all__ = [
    "COLUNAS_FISICAS",
    "REGIAO_POR_UF",
    "escrever_silver",
    "escrever_silver_fixture",
]
