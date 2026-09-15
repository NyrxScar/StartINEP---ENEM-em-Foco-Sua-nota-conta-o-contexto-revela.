"""Testes unitarios da guarda de privacidade (``radar_api.privacidade``).

Cobrem ``aplicar_limiar`` (Req 1.6 / 9.3, Property 4): supressao abaixo do
limiar, nao-supressao no limiar e acima dele, tratamento defensivo de entrada
ja suprimida (``tamanho_amostral`` None) e imutabilidade da entrada.

Cobrem tambem ``proteger_differencing`` e o predicado auxiliar
``differ_por_um_filtro`` (Req 9.5, Property 5): a decisao de suprimir ambos os
Recortes quando a celula-diferenca e nao vazia e menor que o limiar (exemplos;
a propriedade exaustiva e coberta separadamente).
"""

from __future__ import annotations

from datetime import datetime

from radar_api.modelos import (
    Area,
    Capacidade,
    Dimensao,
    Distribuicao,
    FaixaHistograma,
    Linhagem,
    Quantis,
    Recorte,
    ResultadoAnalise,
)
from radar_api.privacidade import (
    aplicar_limiar,
    differ_por_um_filtro,
    proteger_differencing,
)

LIMIAR = 25


def _resultado(tamanho_amostral: int | None) -> ResultadoAnalise:
    """Constroi um ``ResultadoAnalise`` completo (pre-guarda) para os testes.

    Representa a saida crua do nucleo antes da guarda de privacidade: sempre com
    distribuicao/percentil preenchidos e ``estatisticamente_insuficiente=False``;
    apenas o ``tamanho_amostral`` varia por caso de teste.
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
        percentil=62.5,
        tamanho_amostral=tamanho_amostral,
        estatisticamente_insuficiente=False,
        capacidade=capacidade,
        linhagem=linhagem,
    )


def test_abaixo_do_limiar_suprime_campos_sensiveis() -> None:
    """(a) tamanho_amostral logo abaixo do limiar -> resultado suprimido (Req 1.6/9.3)."""
    entrada = _resultado(tamanho_amostral=LIMIAR - 1)
    saida = aplicar_limiar(entrada, LIMIAR)

    assert saida.estatisticamente_insuficiente is True
    assert saida.distribuicao is None
    assert saida.percentil is None
    assert saida.tamanho_amostral is None
    # metadados nao sensiveis sao preservados
    assert saida.edicao == entrada.edicao
    assert saida.area == entrada.area
    assert saida.capacidade == entrada.capacidade
    assert saida.linhagem == entrada.linhagem


def test_igual_ao_limiar_nao_suprime() -> None:
    """(b) tamanho_amostral == limiar -> NAO suprimido (regra e ``< limiar``)."""
    entrada = _resultado(tamanho_amostral=LIMIAR)
    saida = aplicar_limiar(entrada, LIMIAR)

    assert saida.estatisticamente_insuficiente is False
    assert saida.distribuicao == entrada.distribuicao
    assert saida.percentil == entrada.percentil
    assert saida.tamanho_amostral == LIMIAR


def test_acima_do_limiar_mantem_resultado_intacto() -> None:
    """(c) tamanho_amostral acima do limiar -> distribuicao/percentil intactos."""
    entrada = _resultado(tamanho_amostral=100)
    saida = aplicar_limiar(entrada, LIMIAR)

    assert saida.estatisticamente_insuficiente is False
    assert saida.distribuicao == entrada.distribuicao
    assert saida.percentil == 62.5
    assert saida.tamanho_amostral == 100


def test_tamanho_amostral_none_permanece_suprimido() -> None:
    """Entrada ja suprimida (tamanho_amostral None) permanece suprimida (defensivo)."""
    entrada = _resultado(tamanho_amostral=None)
    saida = aplicar_limiar(entrada, LIMIAR)

    assert saida.estatisticamente_insuficiente is True
    assert saida.distribuicao is None
    assert saida.percentil is None
    assert saida.tamanho_amostral is None


def test_entrada_nao_e_mutada_in_loco() -> None:
    """(d) a guarda nao deve mutar a entrada — retorna uma nova instancia."""
    entrada = _resultado(tamanho_amostral=LIMIAR - 1)
    saida = aplicar_limiar(entrada, LIMIAR)

    # a entrada original permanece intacta apos a supressao da saida
    assert entrada.tamanho_amostral == LIMIAR - 1
    assert entrada.distribuicao is not None
    assert entrada.percentil == 62.5
    assert entrada.estatisticamente_insuficiente is False
    # a saida e um objeto distinto da entrada
    assert saida is not entrada


def test_differencing_diferenca_zero_nao_suprime() -> None:
    """Celula-diferenca vazia (contagens iguais) -> nao suprime (nada revelado)."""
    assert proteger_differencing(100, 100, LIMIAR) is False


def test_differencing_diferenca_logo_abaixo_do_limiar_suprime() -> None:
    """Celula-diferenca nao vazia e < limiar -> suprime ambos (Req 9.5)."""
    assert proteger_differencing(100, 100 + (LIMIAR - 1), LIMIAR) is True


def test_differencing_diferenca_igual_ao_limiar_nao_suprime() -> None:
    """Celula-diferenca == limiar -> nao suprime (regra e ``< limiar``)."""
    assert proteger_differencing(100, 100 + LIMIAR, LIMIAR) is False


def test_differencing_diferenca_bem_acima_do_limiar_nao_suprime() -> None:
    """Celula-diferenca >> limiar -> segura sob k-anonimato, nao suprime."""
    assert proteger_differencing(1000, 100, LIMIAR) is False


def test_differencing_e_simetrico_na_ordem_dos_argumentos() -> None:
    """A decisao independe da ordem dos argumentos (usa ``abs``)."""
    a, b = 100, 100 + (LIMIAR - 1)
    assert proteger_differencing(a, b, LIMIAR) == proteger_differencing(b, a, LIMIAR)
    assert proteger_differencing(a, b, LIMIAR) is True


def test_differ_por_um_filtro_caso_adicionar_um_filtro() -> None:
    """``r2`` = ``r1`` mais uma dimensao -> diferem por exatamente um filtro."""
    r1 = Recorte(filtros={Dimensao.REGIAO: "Sudeste"})
    r2 = Recorte(filtros={Dimensao.REGIAO: "Sudeste", Dimensao.TIPO_ESCOLA: "publica"})
    assert differ_por_um_filtro(r1, r2) is True


def test_differ_por_um_filtro_caso_irmaos_mesmo_dimensao_valor_diferente() -> None:
    """Mesmas dimensoes, um unico valor diferente -> diferem por um filtro."""
    r1 = Recorte(filtros={Dimensao.REGIAO: "Sudeste", Dimensao.TIPO_ESCOLA: "publica"})
    r2 = Recorte(filtros={Dimensao.REGIAO: "Sudeste", Dimensao.TIPO_ESCOLA: "privada"})
    assert differ_por_um_filtro(r1, r2) is True


def test_differ_por_um_filtro_identicos_e_falso() -> None:
    """Recortes identicos nao "diferem por um filtro"."""
    r1 = Recorte(filtros={Dimensao.REGIAO: "Sudeste"})
    r2 = Recorte(filtros={Dimensao.REGIAO: "Sudeste"})
    assert differ_por_um_filtro(r1, r2) is False


def test_differ_por_um_filtro_duas_divergencias_e_falso() -> None:
    """Divergencia em duas dimensoes -> nao e vizinhanca por um unico filtro."""
    r1 = Recorte(filtros={Dimensao.REGIAO: "Sudeste", Dimensao.TIPO_ESCOLA: "publica"})
    r2 = Recorte(filtros={Dimensao.REGIAO: "Sul", Dimensao.TIPO_ESCOLA: "privada"})
    assert differ_por_um_filtro(r1, r2) is False
