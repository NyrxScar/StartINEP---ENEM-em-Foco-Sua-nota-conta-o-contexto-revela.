"""Teste de propriedade do construtor de consultas DuckDB (``radar_api.consulta``).

Property 6 (task 5.2) — **Saida exclusivamente agregada**: para *qualquer*
consulta montada pelo nucleo, a projecao que cruza a fronteira do
Motor_de_Consulta contem apenas expressoes agregadas (contagens, quantis,
faixas, percentil) e *nunca* colunas de linha individual; alem disso, o SQL
restringe o caminho de leitura a ``ano`` (sempre) e ``uf_prova`` (quando o
Recorte inclui ``Dimensao.UF``) — Req 6.2.

Como o modulo ``consulta`` e uma camada **pura** que devolve ``(sql, params)``,
esta propriedade e verificada por **inspecao do SQL gerado**, sem executar o
DuckDB. Os auxiliares abaixo extraem a projecao externa (o ``SELECT`` de topo,
apos o fechamento da(s) CTE(s)) e a projecao da CTE ``base``, e classificam cada
item projetado como agregado/derivado-de-agrupamento ou nao. A checagem foi
desenhada para **reprovar** caso alguem adicione uma coluna crua (ex.: ``nota``
ou ``uf_prova``) a projecao externa — ver o teste de controle negativo no fim.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import re

from hypothesis import example, given, settings
from hypothesis import strategies as st

from radar_api.consulta import construir_consulta_agregada, construir_consulta_histograma
from radar_api.modelos import Area, Dimensao, Recorte

# Raiz *silver* fixa e "limpa": nao contem os tokens que as asserts procuram
# (``uf_prova``, ``ano=<edicao>``), evitando falsos positivos de substring.
RAIZ_SILVER = "/silver"

# Funcoes de agregacao/agrupamento cuja *chamada inteira* (com argumentos) e
# considerada segura: nada que esteja dentro delas cruza a fronteira como linha.
_FUNCOES_AGREGADAS = ("count", "min", "max", "sum", "avg", "quantile_cont", "median", "stddev")
_RE_AGREGADO = re.compile(r"\b(?:" + "|".join(_FUNCOES_AGREGADAS) + r")\s*\(", re.IGNORECASE)

# Identificadores "nus" tolerados numa projecao externa: sao *derivados de
# agrupamento* (nao valores de linha). ``contagem`` = ``count(*)`` e ``indice``
# = ``floor(nota/?)`` (chave de GROUP BY) na CTE ``faixas`` do histograma.
_IDENT_DERIVADOS_PERMITIDOS = frozenset({"indice", "contagem"})

_RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RE_ALIAS_FINAL = re.compile(r"\s+AS\s+\w+\s*$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Auxiliares de parsing (pequenos e comentados)                               #
# --------------------------------------------------------------------------- #
def _projecao_externa(sql: str) -> str:
    """Extrai a projecao do ``SELECT`` de topo (o que cruza a fronteira).

    Localiza o fechamento da ultima CTE — o unico ``)`` imediatamente seguido de
    ``SELECT`` (nas consultas agregada e de histograma esse marcador ocorre uma
    unica vez) — e devolve o texto ate o ``FROM`` de topo (``FROM base`` /
    ``FROM faixas``, sempre no inicio de linha, ao contrario dos ``FROM``
    indentados das CTEs).
    """
    marcador = ")\nSELECT\n"
    inicio = sql.rindex(marcador) + len(marcador)
    fim = sql.index("\nFROM ", inicio)
    return sql[inicio:fim]


def _projecao_base(sql: str) -> str:
    """Extrai a lista de projecao da CTE ``base`` (a unica coluna crua lida).

    E aqui — e somente aqui — que uma coluna fisica entra no pipeline; espera-se
    exatamente ``nota_<area> AS nota``.
    """
    inicio_cte = sql.index("WITH base AS (")
    inicio = sql.index("SELECT ", inicio_cte) + len("SELECT ")
    fim = sql.index("\n", inicio)
    return sql[inicio:fim].strip()


def _dividir_itens(projecao: str) -> list[str]:
    """Divide a projecao em itens por virgulas de **topo** (profundidade 0).

    Virgulas dentro de parenteses (ex.: ``quantile_cont(nota, 0.25)``) sao
    ignoradas, para nao fatiar uma unica expressao agregada em duas.
    """
    itens: list[str] = []
    profundidade = 0
    inicio = 0
    for i, caractere in enumerate(projecao):
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade -= 1
        elif caractere == "," and profundidade == 0:
            itens.append(projecao[inicio:i].strip())
            inicio = i + 1
    ultimo = projecao[inicio:].strip()
    if ultimo:
        itens.append(ultimo)
    return itens


def _remover_chamadas_agregadas(expr: str) -> str:
    """Remove toda chamada de funcao agregada (com seus argumentos, equilibrando
    parenteses), deixando apenas o "esqueleto" nao-agregado da expressao.

    Ex.: ``100.0 * (sum(CASE WHEN nota < ? ...) + count(*))`` -> ``100.0 * ( + )``.
    """
    resultado = expr
    while True:
        m = _RE_AGREGADO.search(resultado)
        if m is None:
            return resultado
        abre = m.end() - 1  # posicao do '(' que inicia os argumentos
        profundidade = 0
        fim = -1
        for j in range(abre, len(resultado)):
            if resultado[j] == "(":
                profundidade += 1
            elif resultado[j] == ")":
                profundidade -= 1
                if profundidade == 0:
                    fim = j
                    break
        if fim == -1:  # defensivo: parenteses desbalanceados nao devem ocorrer
            return resultado
        resultado = resultado[: m.start()] + " " + resultado[fim + 1 :]


def _expr_sem_alias(item: str) -> str:
    """Remove o ``AS <alias>`` final de um item de projecao (se houver)."""
    return _RE_ALIAS_FINAL.sub("", item).strip()


def _e_item_agregado(item: str) -> bool:
    """Diz se um item da projecao externa e agregado/derivado-de-agrupamento.

    Estrategia: apaga as chamadas agregadas do item; o que sobra so pode conter
    identificadores derivados de agrupamento (``indice``/``contagem``), numeros,
    operadores e ``?``. Se sobrar qualquer identificador de coluna crua (ex.:
    ``nota``, ``uf_prova``, ``regiao``), o item e reprovado.
    """
    reduzido = _remover_chamadas_agregadas(_expr_sem_alias(item))
    identificadores = set(_RE_IDENT.findall(reduzido))
    return identificadores <= _IDENT_DERIVADOS_PERMITIDOS


def _todos_itens_agregados(itens: list[str]) -> bool:
    """``True`` sse *todos* os itens da projecao externa sao agregados."""
    return all(_e_item_agregado(item) for item in itens)


# --------------------------------------------------------------------------- #
# Blocos de assercao reutilizados pelas duas consultas                        #
# --------------------------------------------------------------------------- #
def _conferir_agregacao_only(sql: str, area: Area) -> None:
    """Confere Property 6: nenhuma coluna de linha cruza a fronteira.

    (1) a CTE ``base`` puxa exatamente uma coluna crua (``nota_<area> AS nota``);
    (2) nao ha ``SELECT *`` em lugar algum;
    (3) todo item da projecao externa e agregado/derivado-de-agrupamento;
    (4) ``nota`` so aparece na projecao externa dentro de agregados.
    """
    assert _projecao_base(sql) == f"nota_{area.value} AS nota"
    assert "select *" not in sql.lower()

    projecao = _projecao_externa(sql)
    itens = _dividir_itens(projecao)
    assert itens, "projecao externa vazia"
    for item in itens:
        assert _e_item_agregado(item), f"item nao-agregado na projecao externa: {item!r}"

    # 'nota' (coluna de linha) nao pode sobrar fora de um agregado
    assert re.search(r"\bnota\b", _remover_chamadas_agregadas(projecao)) is None


def _conferir_pruning_e_params(
    sql: str,
    params: list[object],
    *,
    edicao: int,
    recorte: Recorte,
    n_placeholders_extra: int,
) -> None:
    """Confere pruning por ``ano``/``uf_prova`` (Req 6.2) e a seguranca de params."""
    # pruning por ano: o literal esta no caminho do read_parquet (sempre)
    assert "read_parquet(" in sql
    assert f"/ano={edicao}/**/*.parquet'" in sql

    # pruning por uf_prova: predicado presente sse, e somente se, UF no recorte
    if Dimensao.UF in recorte.filtros:
        assert "CAST(uf_prova AS VARCHAR) = ?" in sql
    else:
        assert "uf_prova" not in sql

    # paridade placeholders x params e contagem esperada
    assert sql.count("?") == len(params)
    assert len(params) == len(recorte.filtros) + n_placeholders_extra

    # valores fornecidos pelo usuario vao para params (nunca ao texto do SQL)
    for valor in recorte.filtros.values():
        assert valor in params


def _conferir_independencia_de_valores(
    edicao: int,
    area: Area,
    recorte: Recorte,
    nota_usuario: float,
    largura: float,
) -> None:
    """Seguranca de injecao: o texto do SQL nao depende dos *valores* de filtro.

    Reconstroi as consultas trocando todos os valores por dois sentinelas
    distintos; se o SQL fosse interpolado com valores, os textos divergiriam.
    A igualdade prova que os valores so entram via ``params`` (binding ``?``).
    """
    chaves = list(recorte.filtros)
    r_a = Recorte(filtros=dict.fromkeys(chaves, "AAA"))
    r_b = Recorte(filtros=dict.fromkeys(chaves, "BBB"))

    ag_a = construir_consulta_agregada(RAIZ_SILVER, edicao, area, r_a, nota_usuario)
    ag_b = construir_consulta_agregada(RAIZ_SILVER, edicao, area, r_b, nota_usuario)
    assert ag_a.sql == ag_b.sql
    assert ag_a.params.count("AAA") == len(chaves)

    hi_a = construir_consulta_histograma(RAIZ_SILVER, edicao, area, r_a, largura)
    hi_b = construir_consulta_histograma(RAIZ_SILVER, edicao, area, r_b, largura)
    assert hi_a.sql == hi_b.sql
    assert hi_a.params.count("AAA") == len(chaves)


# --------------------------------------------------------------------------- #
# Property 6                                                                  #
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(
    edicao=st.integers(min_value=2000, max_value=2100),
    area=st.sampled_from(list(Area)),
    nota_usuario=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    filtros=st.dictionaries(
        keys=st.sampled_from(list(Dimensao)),
        values=st.text(min_size=1, max_size=6),
        max_size=len(Dimensao),
    ),
    largura=st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
)
@example(edicao=2023, area=Area.CN, nota_usuario=500.0, filtros={}, largura=100.0)
@example(edicao=2024, area=Area.CH, nota_usuario=750.0, filtros={Dimensao.UF: "SP"}, largura=50.0)
@example(
    edicao=2025, area=Area.MT, nota_usuario=0.0, filtros={Dimensao.REGIAO: "Sul"}, largura=100.0
)
def test_saida_exclusivamente_agregada(
    edicao: int,
    area: Area,
    nota_usuario: float,
    filtros: dict[Dimensao, str],
    largura: float,
) -> None:
    """Feature: radar-enem-analise-api, Property 6: Saída exclusivamente agregada

    **Validates: Requirements 6.2, 6.4, 9.1**

    Para qualquer consulta construida pelo nucleo (agregada e histograma), a
    projecao que cruza a fronteira do Motor_de_Consulta contem apenas expressoes
    agregadas (contagens, quantis, faixas, percentil) — nunca colunas de linha
    individual — e o SQL restringe o caminho a ``ano``/``uf_prova`` (Req 6.2).
    """
    recorte = Recorte(filtros=filtros)

    agregada = construir_consulta_agregada(RAIZ_SILVER, edicao, area, recorte, nota_usuario)
    histograma = construir_consulta_histograma(RAIZ_SILVER, edicao, area, recorte, largura)

    # (Req 6.4 / 9.1) projecao exclusivamente agregada nas duas consultas
    _conferir_agregacao_only(agregada.sql, area)
    _conferir_agregacao_only(histograma.sql, area)

    # o histograma so pode expor ``indice``/``contagem`` porque sao de GROUP BY
    assert "GROUP BY indice" in histograma.sql

    # (Req 6.2) pruning + seguranca de params: 2 extras (percentil) / 3 (faixa)
    _conferir_pruning_e_params(
        agregada.sql, agregada.params, edicao=edicao, recorte=recorte, n_placeholders_extra=2
    )
    _conferir_pruning_e_params(
        histograma.sql, histograma.params, edicao=edicao, recorte=recorte, n_placeholders_extra=3
    )

    # (Req 9.1) seguranca de injecao: SQL independente dos valores de filtro
    _conferir_independencia_de_valores(edicao, area, recorte, nota_usuario, largura)


# --------------------------------------------------------------------------- #
# Controle negativo — prova que a checagem de Property 6 "tem dentes"         #
# --------------------------------------------------------------------------- #
def test_controle_negativo_detecta_coluna_crua_na_projecao() -> None:
    """Injeta uma coluna de linha crua na projecao externa e confirma REPROVA.

    Sem esta prova, a asserção de Property 6 poderia passar vacuamente. Aqui o
    SQL real e adulterado (o modulo ``consulta`` NAO e alterado) para simular o
    vazamento de ``nota`` e de ``uf_prova`` na projecao de topo.
    """
    consulta = construir_consulta_agregada(
        RAIZ_SILVER, 2023, Area.CN, Recorte(filtros={Dimensao.UF: "SP"}), 500.0
    )
    # o SQL genuino passa na checagem
    assert _todos_itens_agregados(_dividir_itens(_projecao_externa(consulta.sql)))

    # vazamento de uma coluna de nota crua -> deve REPROVAR
    sql_nota = consulta.sql.replace(
        "    count(*) AS tamanho_amostral,\n",
        "    count(*) AS tamanho_amostral,\n    nota,\n",
        1,
    )
    assert not _todos_itens_agregados(_dividir_itens(_projecao_externa(sql_nota)))

    # vazamento de uma coluna fisica de recorte -> deve REPROVAR
    sql_uf = consulta.sql.replace(
        "    max(nota) AS q_max,\n",
        "    max(nota) AS q_max,\n    uf_prova,\n",
        1,
    )
    assert not _todos_itens_agregados(_dividir_itens(_projecao_externa(sql_uf)))
