"""Teste de propriedade da supressao abaixo do limiar (``radar_api.privacidade``).

Property 4 (task 4.3) — **Supressao abaixo do limiar**: para *qualquer* Recorte
cujo ``tamanho_amostral`` seja menor que o ``Limite_Minimo_de_Agregacao``
configurado, ``aplicar_limiar`` deve marcar o resultado como
``estatisticamente_insuficiente`` e nao expor distribuicao, quantis nem
percentil (Req 1.6 / 9.3). O complemento tambem e verificado: quando
``tamanho_amostral >= limiar``, o resultado permanece intacto
(distribuicao/percentil/tamanho amostral preservados e a flag em ``False``).

A guarda e uma funcao **pura** que nao muta a entrada, portanto a propriedade e
verificada construindo um ``ResultadoAnalise`` completo (pre-guarda), aplicando
``aplicar_limiar`` e inspecionando a saida — sem HTTP nem DuckDB. Um caso
adicional cobre a entrada ja suprimida (``tamanho_amostral`` None), que deve
permanecer suprimida.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from radar_api.modelos import (
    Area,
    Capacidade,
    Dimensao,
    Distribuicao,
    FaixaHistograma,
    Linhagem,
    Quantis,
    ResultadoAnalise,
)
from radar_api.privacidade import aplicar_limiar


def _resultado(tamanho_amostral: int | None, percentil: float) -> ResultadoAnalise:
    """Constroi um ``ResultadoAnalise`` completo (pre-guarda) para a propriedade.

    Representa a saida crua do nucleo antes da guarda de privacidade: sempre com
    ``distribuicao``/``quantis`` preenchidos e ``estatisticamente_insuficiente``
    em ``False``; ``tamanho_amostral`` e ``percentil`` variam por exemplo gerado.
    """
    distribuicao = Distribuicao(
        faixas=[
            FaixaHistograma(limite_inferior=0.0, limite_superior=500.0, contagem=10),
            FaixaHistograma(limite_inferior=500.0, limite_superior=1000.0, contagem=15),
        ],
        quantis=Quantis(minimo=100.0, q1=400.0, mediana=550.0, q3=700.0, maximo=980.0),
    )
    capacidade = Capacidade(
        edicao=2023,
        dimensoes_suportadas={Dimensao.REGIAO, Dimensao.UF},
        possui_notas=True,
        perfil_combinavel_com_notas=True,
    )
    linhagem = Linhagem(
        edicoes=[2023],
        manifestos={2023: "sha256:abc123"},
        datas_carga={2023: datetime(2026, 1, 1, 12, 0, 0)},
    )
    return ResultadoAnalise(
        edicao=2023,
        area=Area.CH,
        distribuicao=distribuicao,
        percentil=percentil,
        tamanho_amostral=tamanho_amostral,
        estatisticamente_insuficiente=False,
        capacidade=capacidade,
        linhagem=linhagem,
    )


@settings(max_examples=100)
@given(
    limiar=st.integers(min_value=1, max_value=200),
    tamanho_amostral=st.integers(min_value=0, max_value=500),
    percentil=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
def test_supressao_abaixo_do_limiar(
    limiar: int,
    tamanho_amostral: int,
    percentil: float,
) -> None:
    """Feature: radar-enem-analise-api, Property 4: Supressão abaixo do limiar

    **Validates: Requirements 1.6, 9.3**

    Para qualquer Recorte cujo ``tamanho_amostral`` seja menor que o limiar
    configurado, o resultado e marcado como ``estatisticamente_insuficiente`` e
    nao expoe distribuicao, quantis nem percentil. No complemento
    (``tamanho_amostral >= limiar``), o resultado permanece intacto. Em ambos os
    casos, a entrada nunca e mutada in loco.
    """
    entrada = _resultado(tamanho_amostral=tamanho_amostral, percentil=percentil)
    saida = aplicar_limiar(entrada, limiar)

    if tamanho_amostral < limiar:
        # abaixo do limiar -> suprimido: flag ligada e campos sensiveis anulados
        assert saida.estatisticamente_insuficiente is True
        assert saida.distribuicao is None
        assert saida.percentil is None
        assert saida.tamanho_amostral is None
    else:
        # no limiar ou acima -> intacto: distribuicao/percentil/tamanho preservados
        assert saida.estatisticamente_insuficiente is False
        assert saida.distribuicao == entrada.distribuicao
        assert saida.percentil == percentil
        assert saida.tamanho_amostral == tamanho_amostral

    # metadados nao sensiveis sao sempre preservados
    assert saida.edicao == entrada.edicao
    assert saida.area == entrada.area
    assert saida.capacidade == entrada.capacidade
    assert saida.linhagem == entrada.linhagem

    # a entrada nunca e mutada in loco (a guarda retorna uma nova instancia)
    assert saida is not entrada
    assert entrada.tamanho_amostral == tamanho_amostral
    assert entrada.distribuicao is not None
    assert entrada.percentil == percentil
    assert entrada.estatisticamente_insuficiente is False


@settings(max_examples=100)
@given(
    limiar=st.integers(min_value=1, max_value=200),
    percentil=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
def test_tamanho_amostral_none_permanece_suprimido(
    limiar: int,
    percentil: float,
) -> None:
    """Property 4 (complemento): entrada ja suprimida (``tamanho_amostral`` None).

    **Validates: Requirements 1.6, 9.3**

    Uma entrada cujo ``tamanho_amostral`` ja e ``None`` (sinal de supressao
    previa) deve permanecer suprimida para qualquer limiar, sem reexpor
    distribuicao, quantis ou percentil, e sem mutar a entrada.
    """
    entrada = _resultado(tamanho_amostral=None, percentil=percentil)
    saida = aplicar_limiar(entrada, limiar)

    assert saida.estatisticamente_insuficiente is True
    assert saida.distribuicao is None
    assert saida.percentil is None
    assert saida.tamanho_amostral is None

    # a entrada nao e mutada: distribuicao/percentil originais permanecem
    assert saida is not entrada
    assert entrada.distribuicao is not None
    assert entrada.percentil == percentil
    assert entrada.estatisticamente_insuficiente is False
