"""Teste de propriedade da capacidade derivada do contrato (``radar_api.catalogo``).

Property 7 (task 3.3) — **Capacidade derivada do contrato**: para *qualquer*
contrato de Edicao, um tipo de Recorte (uma :class:`~radar_api.modelos.Dimensao`)
e reportado como suportado se, e somente se, TODAS as colunas canonicas que o
sustentam (:data:`~radar_api.catalogo.SUSTENTACAO_CANONICA`) estao em
``mapeamento``/``derivadas`` e NENHUMA em ``ausentes`` (Req 2.1). A mesma regra
*sse* governa ``possui_notas`` (sobre :data:`~radar_api.catalogo.NOTAS_CANONICAS`)
e ``perfil_combinavel_com_notas`` (ha notas *e* ao menos uma dimensao de perfil
suportada).

Estrategia (contratos consistentes por construcao): cada coluna canonica de
:data:`ALL_COLS` e atribuida a EXATAMENTE um dos tres baldes
(``mapeamento``/``derivadas``/``ausentes``). Assim nenhuma coluna necessaria
fica fora dos tres conjuntos nem aparece em dois deles — a derivacao jamais
dispara a guarda de contrato inconsistente/incompleto, isolando a regra *sse*
que esta propriedade exercita. Os dois ramos da guarda (coluna em NENHUM balde;
coluna em ``ausentes`` E ``mapeamento``) sao cobertos por testes dedicados ao
final.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import chain

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from radar_api.catalogo import (
    DIMENSOES_PERFIL,
    NOTAS_CANONICAS,
    SUSTENTACAO_CANONICA,
    derivar_capacidade_do_contrato,
)
from radar_api.erros import ErroCapacidadeIndeterminada
from radar_api.modelos import Dimensao

# Universo de colunas canonicas relevantes: as que sustentam cada Dimensao mais
# as colunas de nota. E o dominio que a estrategia particiona nos tres baldes.
ALL_COLS: tuple[str, ...] = tuple(
    sorted(set(chain.from_iterable(SUSTENTACAO_CANONICA.values())) | set(NOTAS_CANONICAS))
)

# Colunas que sustentam as dimensoes de perfil socioeconomico (renda, cor/raca,
# escolaridade dos pais); usadas para montar o exemplo "notas sem perfil".
COLS_PERFIL: frozenset[str] = frozenset(
    chain.from_iterable(SUSTENTACAO_CANONICA[dim] for dim in DIMENSOES_PERFIL)
)

# Nomes dos tres baldes; cada coluna cai em exatamente um deles.
_BALDES: tuple[str, ...] = ("mapeamento", "derivadas", "ausentes")

# A edicao apenas rotula a Capacidade/erros; o valor concreto e irrelevante para
# a regra *sse*, dirigida somente pela particao das colunas.
EDICAO_SINTETICA = 2023


@dataclass(frozen=True)
class _ContratoFalso:
    """Contrato canonico sintetico (satisfaz o Protocol ``ContratoCanonico``).

    Expoe apenas os tres conjuntos de nomes de coluna que a derivacao consome —
    ``mapeamento``, ``derivadas`` e ``ausentes``. Sem I/O e sem o ETL real.
    """

    mapeamento: frozenset[str] = field(default_factory=frozenset)
    derivadas: frozenset[str] = field(default_factory=frozenset)
    ausentes: frozenset[str] = field(default_factory=frozenset)


def _suporte_esperado(
    colunas: tuple[str, ...],
    mapeamento: frozenset[str],
    derivadas: frozenset[str],
    ausentes: frozenset[str],
) -> bool:
    """Regra *sse* de referencia, computada de forma independente do SUT.

    Um grupo de ``colunas`` esta disponivel sse TODAS estao em
    ``mapeamento``/``derivadas`` e NENHUMA em ``ausentes``.
    """
    disponiveis = mapeamento | derivadas
    return all(col in disponiveis for col in colunas) and not any(
        col in ausentes for col in colunas
    )


def _contrato_de_baldes(baldes: dict[str, str]) -> _ContratoFalso:
    """Constroi o contrato a partir do mapa ``coluna -> balde`` (particao)."""
    return _ContratoFalso(
        mapeamento=frozenset(c for c, b in baldes.items() if b == "mapeamento"),
        derivadas=frozenset(c for c, b in baldes.items() if b == "derivadas"),
        ausentes=frozenset(c for c, b in baldes.items() if b == "ausentes"),
    )


# Estrategia: atribui cada coluna de ALL_COLS a um unico balde. O contrato
# resultante e sempre consistente e completo (particao exata do dominio).
contratos_consistentes = st.fixed_dictionaries(
    {col: st.sampled_from(_BALDES) for col in ALL_COLS}
).map(_contrato_de_baldes)


@settings(max_examples=100, deadline=None)
@given(contrato=contratos_consistentes)
# Cantos deterministicos que a amostragem aleatoria cobriria raramente:
@example(contrato=_ContratoFalso(mapeamento=frozenset(ALL_COLS)))  # tudo disponivel
@example(contrato=_ContratoFalso(ausentes=frozenset(ALL_COLS)))  # tudo ausente
@example(  # notas presentes, porem nenhum perfil -> perfil nao combinavel
    contrato=_ContratoFalso(
        mapeamento=frozenset(ALL_COLS) - COLS_PERFIL,
        ausentes=COLS_PERFIL,
    )
)
def test_capacidade_derivada_do_contrato(contrato: _ContratoFalso) -> None:
    """Feature: radar-enem-analise-api, Property 7: Capacidade derivada do contrato

    **Validates: Requirements 2.1**

    Para qualquer contrato consistente, a Capacidade derivada obedece a regra
    *sse* sobre a particao das colunas:

    1. cada :class:`~radar_api.modelos.Dimensao` e suportada sse todas as suas
       colunas de sustentacao estao em ``mapeamento``/``derivadas`` e nenhuma em
       ``ausentes``;
    2. ``possui_notas`` segue a mesma regra sobre as colunas de nota;
    3. ``perfil_combinavel_com_notas`` e verdadeiro sse ha notas E ao menos uma
       dimensao de perfil e suportada.
    """
    mapeamento, derivadas, ausentes = (
        contrato.mapeamento,
        contrato.derivadas,
        contrato.ausentes,
    )

    capac = derivar_capacidade_do_contrato(EDICAO_SINTETICA, contrato)

    # (1) suporte de cada Dimensao coincide com a regra *sse* de referencia.
    for dim in Dimensao:
        esperado = _suporte_esperado(SUSTENTACAO_CANONICA[dim], mapeamento, derivadas, ausentes)
        assert (dim in capac.dimensoes_suportadas) == esperado, dim

    # (2) possui_notas segue a mesma regra sobre as colunas de nota.
    notas_esperado = _suporte_esperado(NOTAS_CANONICAS, mapeamento, derivadas, ausentes)
    assert capac.possui_notas == notas_esperado

    # (3) perfil combinavel sse ha notas E ao menos uma dimensao de perfil suportada.
    perfil_disponivel_esperado = any(
        _suporte_esperado(SUSTENTACAO_CANONICA[dim], mapeamento, derivadas, ausentes)
        for dim in DIMENSOES_PERFIL
    )
    assert capac.perfil_combinavel_com_notas == (notas_esperado and perfil_disponivel_esperado)

    # coerencia: a Capacidade e rotulada com a Edicao consultada.
    assert capac.edicao == EDICAO_SINTETICA


# --------------------------------------------------------------------------- #
# Guarda do contrato — ramos de indeterminacao (fora do espaco da propriedade) #
# --------------------------------------------------------------------------- #
def test_contrato_incompleto_levanta_indeterminada() -> None:
    """Coluna necessaria em NENHUM dos baldes -> ``CAPACIDADE_INDETERMINADA`` (Req 2).

    Todas as colunas menos uma sao declaradas disponiveis; a coluna faltante nao
    aparece em ``mapeamento``/``derivadas`` nem em ``ausentes``, tornando a
    capacidade indeterminavel.
    """
    faltante = SUSTENTACAO_CANONICA[Dimensao.REGIAO][0]
    presentes = frozenset(c for c in ALL_COLS if c != faltante)
    contrato = _ContratoFalso(mapeamento=presentes)

    with pytest.raises(ErroCapacidadeIndeterminada):
        derivar_capacidade_do_contrato(EDICAO_SINTETICA, contrato)


def test_contrato_inconsistente_levanta_indeterminada() -> None:
    """Coluna necessaria em ``ausentes`` E ``mapeamento`` -> ``CAPACIDADE_INDETERMINADA``.

    A contradicao (coluna simultaneamente disponivel e ausente) impede
    determinar a capacidade, mesmo com todas as demais colunas resolvidas.
    """
    conflitante = SUSTENTACAO_CANONICA[Dimensao.REGIAO][0]
    contrato = _ContratoFalso(
        mapeamento=frozenset(ALL_COLS),
        ausentes=frozenset({conflitante}),
    )

    with pytest.raises(ErroCapacidadeIndeterminada):
        derivar_capacidade_do_contrato(EDICAO_SINTETICA, contrato)
