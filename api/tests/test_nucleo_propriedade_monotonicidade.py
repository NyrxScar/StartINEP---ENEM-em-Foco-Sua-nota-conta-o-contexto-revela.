"""Teste de propriedade da monotonicidade do Recorte (``radar_api.nucleo.analisar``).

Property 2 (task 5.5) — **Monotonicidade do Recorte (AND conjuntivo)**: para
*qualquer* Recorte R e *qualquer* R' obtido de R adicionando exatamente um
filtro (numa Dimensao ainda ausente de R), o ``tamanho_amostral`` de R' nunca e
maior que o de R. Isso decorre de os filtros serem aplicados de forma
conjuntiva (AND, Req 1.4): acrescentar um predicado so pode *remover* linhas do
conjunto, nunca acrescentar.

A propriedade e exercitada de ponta a ponta sobre *fixtures* Parquet minusculas
escritas por :mod:`fixtures_silver` no mesmo layout Hive da *silver* real
(``ano=<edicao>/uf_prova=<UF>``). Cada exemplo gera:

* um conjunto de linhas com duas dimensoes filtraveis de dominio pequeno —
  ``tipo_escola``/``cor_raca`` (``TINYINT`` ``{1, 2, 3}``) — mais a ``uf_prova``
  roteada por particao (``{SP, RJ, MG}``), e uma nota opcionalmente nula na Area;
* um Recorte base R (vazio ou com filtros) e um Recorte estendido R' = R mais
  **exatamente um** filtro, numa Dimensao garantidamente ausente de R.

Usa-se ``limiar=0`` de proposito: assim a guarda de privacidade nunca suprime a
contagem (``tamanho_amostral`` permanece um inteiro concreto ``>= 0``, jamais
``None``), tornando ``tamanho_amostral(R')`` e ``tamanho_amostral(R)``
diretamente comparaveis (do contrario a supressao mascararia a contagem real).

Cada TemporaryDirectory e criado *dentro* do teste (nunca a fixture ``tmp_path``
do pytest junto de ``@given``) e limpo ao fim. Biblioteca PBT: **hypothesis**
(minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.modelos import Area, Dimensao, Recorte
from radar_api.nucleo import analisar

# Edicao com capacidade plena (todos os recortes) e nota-sonda arbitraria: esta
# propriedade so olha o ``tamanho_amostral`` (contagem), nao o Percentil.
EDICAO = 2023
NOTA_SONDA = 500.0

# Dominios pequenos das dimensoes filtraveis. ``uf_prova`` e roteada por
# particao (string); ``tipo_escola``/``cor_raca`` sao colunas fisicas TINYINT.
_UFS = ("SP", "RJ", "MG")
_TIPOS_ESCOLA = (1, 2, 3)
_CORES_RACA = (1, 2, 3)

# Valores de FILTRO como texto: casam com ``CAST(<coluna> AS VARCHAR) = ?`` do
# construtor de consulta (``Recorte.filtros`` mapeia Dimensao -> str).
_DOMINIOS_FILTRO: dict[Dimensao, tuple[str, ...]] = {
    Dimensao.UF: _UFS,
    Dimensao.TIPO_ESCOLA: ("1", "2", "3"),
    Dimensao.COR_RACA: ("1", "2", "3"),
}
_DIMENSOES = tuple(_DOMINIOS_FILTRO)

# Nota da Area: nula (linha excluida por ``IS NOT NULL``) ou um valor valido.
_ESTRATEGIA_NOTA = st.one_of(
    st.none(),
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
)

# Especificacao bruta de uma linha: (uf, tipo_escola, cor_raca, nota|None).
_ESTRATEGIA_LINHA = st.tuples(
    st.sampled_from(_UFS),
    st.sampled_from(_TIPOS_ESCOLA),
    st.sampled_from(_CORES_RACA),
    _ESTRATEGIA_NOTA,
)

# (area, coluna_nota, linhas, recorte_base R, recorte_estendido R').
_Cenario = tuple[Area, str, list[dict[str, object]], Recorte, Recorte]


@st.composite
def _cenarios(draw: st.DrawFn) -> _Cenario:
    """Gera ``(area, coluna_nota, linhas, R, R')`` com R' = R + um filtro extra.

    A Dimensao extra que distingue R' de R e escolhida primeiro; R so pode usar
    as *outras* dimensoes, garantindo que R' estende R por **exatamente um**
    filtro (a chave extra e sempre ausente de R). As linhas cobrem as duas
    dimensoes filtraveis (``tipo_escola``/``cor_raca``) e a ``uf_prova`` roteada,
    com nota opcionalmente nula na Area sorteada.
    """
    area = draw(st.sampled_from(list(Area)))
    coluna_nota = f"nota_{area.value}"

    especificacoes = draw(st.lists(_ESTRATEGIA_LINHA, max_size=40))
    linhas: list[dict[str, object]] = []
    for uf, tipo, cor, nota in especificacoes:
        linha: dict[str, object] = {"uf_prova": uf, "tipo_escola": tipo, "cor_raca": cor}
        if nota is not None:
            linha[coluna_nota] = nota
        linhas.append(linha)

    dim_extra = draw(st.sampled_from(_DIMENSOES))
    outras = [dim for dim in _DIMENSOES if dim != dim_extra]
    dims_base = draw(st.lists(st.sampled_from(outras), unique=True, max_size=len(outras)))
    filtros_base = {dim: draw(st.sampled_from(_DOMINIOS_FILTRO[dim])) for dim in dims_base}
    valor_extra = draw(st.sampled_from(_DOMINIOS_FILTRO[dim_extra]))

    recorte_base = Recorte(filtros=filtros_base)
    recorte_estendido = Recorte(filtros={**filtros_base, dim_extra: valor_extra})
    return area, coluna_nota, linhas, recorte_base, recorte_estendido


@settings(max_examples=100, deadline=None)
@given(cenario=_cenarios())
def test_monotonicidade_do_recorte(cenario: _Cenario) -> None:
    """Feature: radar-enem-analise-api, Property 2: Monotonicidade do Recorte (AND conjuntivo)

    **Validates: Requirements 1.4**

    Para qualquer Recorte R e qualquer R' obtido de R adicionando exatamente um
    filtro (numa Dimensao ausente de R), ``tamanho_amostral(R') <=
    tamanho_amostral(R)``: um predicado conjuntivo (AND) so pode remover linhas.
    Com ``limiar=0`` a contagem nunca e suprimida, logo ``tamanho_amostral`` e
    sempre um inteiro concreto (``>= 0``). Quando R e vazio, a contagem iguala o
    total de linhas com nota nao nula na Area (Req 1.3/1.5).
    """
    area, coluna_nota, linhas, recorte_base, recorte_estendido = cenario

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        escrever_silver(raiz, EDICAO, linhas)
        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=0))

        resultado_base = analisar(catalogo, EDICAO, area, NOTA_SONDA, recorte_base, limiar=0)
        resultado_estendido = analisar(
            catalogo, EDICAO, area, NOTA_SONDA, recorte_estendido, limiar=0
        )

    contagem_base = resultado_base.tamanho_amostral
    contagem_estendida = resultado_estendido.tamanho_amostral

    # limiar=0 => nunca suprimido: as contagens sao inteiros concretos e >= 0.
    assert contagem_base is not None
    assert contagem_estendida is not None
    assert contagem_base >= 0
    assert contagem_estendida >= 0

    # P2 (Req 1.4): adicionar um filtro conjuntivo so pode remover linhas.
    assert contagem_estendida <= contagem_base

    # R vazio => contagem = total de linhas com nota nao nula na Area.
    if not recorte_base.filtros:
        esperado = sum(1 for linha in linhas if coluna_nota in linha)
        assert contagem_base == esperado


def test_monotonicidade_estrita_em_caso_conhecido() -> None:
    """Caso deterministico: refinar o Recorte reduz *estritamente* a contagem.

    Guarda de nao-vacuidade: assegura que a propriedade nao passa apenas porque
    as contagens seriam sempre iguais. Sobre um universo conhecido (60 linhas em
    SP/RJ), R = {} tem 60; R' = {UF: SP} remove as 10 de RJ (50); e refinar para
    {UF: SP, tipo_escola: 1} remove tambem as 20 de ``tipo_escola=2`` (30) —
    cada passo estritamente menor que o anterior.
    """
    linhas = (
        [{"nota_cn": 500.0, "uf_prova": "SP", "tipo_escola": 1} for _ in range(30)]
        + [{"nota_cn": 600.0, "uf_prova": "SP", "tipo_escola": 2} for _ in range(20)]
        + [{"nota_cn": 700.0, "uf_prova": "RJ", "tipo_escola": 1} for _ in range(10)]
    )

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        escrever_silver(raiz, EDICAO, linhas)
        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=0))

        vazio = analisar(catalogo, EDICAO, Area.CN, NOTA_SONDA, Recorte(), limiar=0)
        so_sp = analisar(
            catalogo,
            EDICAO,
            Area.CN,
            NOTA_SONDA,
            Recorte(filtros={Dimensao.UF: "SP"}),
            limiar=0,
        )
        sp_tipo1 = analisar(
            catalogo,
            EDICAO,
            Area.CN,
            NOTA_SONDA,
            Recorte(filtros={Dimensao.UF: "SP", Dimensao.TIPO_ESCOLA: "1"}),
            limiar=0,
        )

    assert vazio.tamanho_amostral == 60
    assert so_sp.tamanho_amostral == 50  # remove as 10 linhas de RJ
    assert sp_tipo1.tamanho_amostral == 30  # remove tambem as 20 de tipo_escola=2
    # cadeia de refinamento estritamente decrescente
    assert sp_tipo1.tamanho_amostral < so_sp.tamanho_amostral < vazio.tamanho_amostral
