"""Teste de propriedade da exclusao de nulos e do tamanho amostral.

Property 1 (task 5.4) — **Exclusao de nulos e correcao do tamanho amostral**:
para *qualquer* conjunto de linhas *silver* de uma Edicao (incluindo o Recorte
vazio) e *qualquer* Area, o ``tamanho_amostral`` devolvido por
``radar_api.nucleo.analisar`` deve ser igual a contagem de linhas do Recorte cuja
nota da Area e **nao nula**, e nenhuma linha com nota nula deve participar da
agregacao (Req 1.2, 1.3, 1.5).

A propriedade e exercitada de ponta a ponta sobre *fixtures* Parquet minusculas
escritas por :mod:`fixtures_silver` no mesmo layout Hive da *silver* real
(``ano=<edicao>/uf_prova=<UF>``). Cada exemplo gera de 0 a 40 linhas em que a
nota da Area sorteada e **ou** um valor valido em ``[0, 1000]`` **ou** ausente
(coluna omitida => ``NULL`` no Parquet), mais um ``tipo_escola`` de dominio
pequeno (``TINYINT`` ``{1, 2, 3}``) para que um Recorte possa filtrar sobre ele.
O Recorte e vazio (Req 1.3) ou um unico filtro em ``Dimensao.TIPO_ESCOLA``.

O ``esperado`` e recalculado **independentemente em Python** (contando as linhas
que casam o filtro *e* tem nota nao nula), sem reusar nada do caminho SQL — e o
oraculo da propriedade.

Usa-se ``limiar=0`` de proposito: assim a guarda de privacidade nunca suprime a
contagem, e ``tamanho_amostral`` permanece um inteiro concreto ``>= 0`` (jamais
``None``) diretamente comparavel ao oraculo. Sob o limiar padrao a contagem
verdadeira ficaria mascarada por ``None`` e a propriedade seria inverificavel.

Cada TemporaryDirectory e criado *dentro* do corpo do teste (nunca a fixture
``tmp_path`` do pytest junto de ``@given``, que seria compartilhada entre os
exemplos) e removido ao fim do ``with``.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.modelos import Area, Dimensao, Recorte
from radar_api.nucleo import analisar

# Edicao com capacidade plena e nota-sonda arbitraria: esta propriedade so olha o
# ``tamanho_amostral`` (contagem), nao a Distribuicao nem o Percentil.
EDICAO = 2023
NOTA_SONDA = 500.0

# Dominio pequeno de ``tipo_escola`` (coluna fisica TINYINT). Os valores de
# FILTRO sao os mesmos, como texto: casam com o ``CAST(col AS VARCHAR) = ?`` do
# construtor de consulta (``Recorte.filtros`` mapeia Dimensao -> str).
_TIPOS_ESCOLA = (1, 2, 3)
_FILTROS_TIPO_ESCOLA = ("1", "2", "3")

# Nota da Area: ausente (``None`` => coluna omitida => NULL, linha excluida por
# ``IS NOT NULL``) ou um valor valido em 0..1000.
_ESTRATEGIA_NOTA = st.one_of(
    st.none(),
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
)

# Especificacao bruta de uma linha: (tipo_escola, nota|None).
_ESTRATEGIA_LINHA = st.tuples(st.sampled_from(_TIPOS_ESCOLA), _ESTRATEGIA_NOTA)

# Linhas fixas dos ``@example``: metade com nota, metade nula, nos tres tipos.
_LINHAS_MISTAS: list[tuple[int, float | None]] = [
    (1, 500.0),
    (1, None),
    (2, 620.0),
    (2, None),
    (3, 710.0),
    (3, None),
]


def _montar_linhas(
    especificacoes: list[tuple[int, float | None]], coluna_nota: str
) -> list[dict[str, object]]:
    """Converte as especificacoes brutas em linhas de *fixture* da *silver*.

    Quando a nota e ``None``, a coluna ``nota_<area>`` e **omitida** — a fixture
    a materializa como ``NULL`` no Parquet, que e exatamente o caso que a
    consulta deve excluir (Req 1.2). ``tipo_escola`` e sempre preenchido para
    que o Recorte possa filtrar sobre ele.
    """
    linhas: list[dict[str, object]] = []
    for tipo, nota in especificacoes:
        linha: dict[str, object] = {"tipo_escola": tipo}
        if nota is not None:
            linha[coluna_nota] = nota
        linhas.append(linha)
    return linhas


def _contar_esperado(especificacoes: list[tuple[int, float | None]], filtro: str | None) -> int:
    """Oraculo independente: linhas que casam o Recorte **e** tem nota nao nula.

    Reimplementa a semantica esperada em Python puro (sem tocar SQL): filtro
    vazio (``None``) conta todas as linhas com nota (Req 1.3); com filtro, so as
    do ``tipo_escola`` correspondente (comparado como texto, como no
    ``CAST(... AS VARCHAR)``). Linhas de nota nula nunca contam (Req 1.2).
    """
    return sum(
        1
        for tipo, nota in especificacoes
        if nota is not None and (filtro is None or str(tipo) == filtro)
    )


@settings(max_examples=100, deadline=None)
@given(
    area=st.sampled_from(list(Area)),
    especificacoes=st.lists(_ESTRATEGIA_LINHA, max_size=40),
    filtro=st.one_of(st.none(), st.sampled_from(_FILTROS_TIPO_ESCOLA)),
)
# Recorte vazio (Req 1.3): sem linhas, e com mistura de notas e nulos.
@example(area=Area.CN, especificacoes=[], filtro=None)
@example(area=Area.MT, especificacoes=_LINHAS_MISTAS, filtro=None)
# Mesmas linhas sob um unico filtro de recorte.
@example(area=Area.REDACAO, especificacoes=_LINHAS_MISTAS, filtro="1")
# Universo em que *todas* as notas da Area sao nulas: contagem deve ser 0.
@example(area=Area.LC, especificacoes=[(1, None), (2, None), (3, None)], filtro=None)
def test_exclusao_de_nulos_e_tamanho_amostral(
    area: Area,
    especificacoes: list[tuple[int, float | None]],
    filtro: str | None,
) -> None:
    """Feature: radar-enem-analise-api, Property 1: Exclusão de nulos e correção do tamanho amostral

    **Validates: Requirements 1.2, 1.3, 1.5**

    Para qualquer conjunto de linhas de uma Edicao (incluindo o Recorte vazio) e
    qualquer Area, o ``tamanho_amostral`` devolvido por ``analisar`` iguala a
    contagem de linhas do Recorte cuja nota da Area e nao nula — nenhuma linha de
    nota nula participa da agregacao. Com ``limiar=0`` a contagem nunca e
    suprimida, logo e sempre um inteiro concreto comparavel ao oraculo Python.
    """
    coluna_nota = f"nota_{area.value}"
    linhas = _montar_linhas(especificacoes, coluna_nota)
    recorte = Recorte() if filtro is None else Recorte(filtros={Dimensao.TIPO_ESCOLA: filtro})

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        escrever_silver(raiz, EDICAO, linhas)
        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=0))
        resultado = analisar(catalogo, EDICAO, area, NOTA_SONDA, recorte, limiar=0)

    esperado = _contar_esperado(especificacoes, filtro)

    # limiar=0 => nunca suprimido: a contagem verdadeira e observavel.
    assert resultado.tamanho_amostral is not None
    # P1 (Req 1.2/1.3/1.5): a contagem e exatamente a das linhas do Recorte com
    # nota nao nula na Area.
    assert resultado.tamanho_amostral == esperado

    # Nenhuma linha de nota nula participa: havendo linhas de nota nula que
    # satisfazem o Recorte, a contagem fica estritamente abaixo do total de
    # linhas do Recorte (nao apenas igual ao oraculo).
    nulas_no_recorte = sum(
        1
        for tipo, nota in especificacoes
        if nota is None and (filtro is None or str(tipo) == filtro)
    )
    total_no_recorte = esperado + nulas_no_recorte
    if nulas_no_recorte:
        assert resultado.tamanho_amostral < total_no_recorte
    else:
        assert resultado.tamanho_amostral == total_no_recorte

    # Amostra vazia nao produz Distribuicao nem Percentil (nada a agregar).
    if esperado == 0:
        assert resultado.distribuicao is None
        assert resultado.percentil is None


def test_linhas_de_nota_nula_nao_alteram_o_tamanho_amostral() -> None:
    """Caso deterministico: acrescentar linhas de nota NULL nao muda a contagem.

    Guarda de nao-vacuidade da exclusao de nulos (Req 1.2): sobre um universo
    conhecido de 12 linhas com ``nota_cn`` preenchida, a contagem e 12. Ao
    acrescentar 20 linhas com ``nota_cn`` NULL — mas com as **outras** colunas
    populadas (``tipo_escola``, ``cor_raca``, ``renda_familiar`` e ate notas de
    *outras* Areas) — e reescrever a *silver*, a contagem continua 12. Ou seja: a
    exclusao olha especificamente a nota da Area consultada, e linhas nulas nessa
    Area nunca entram na agregacao, mesmo satisfazendo o Recorte.
    """
    com_nota = [{"nota_cn": 500.0, "tipo_escola": 1, "cor_raca": 1} for _ in range(12)]
    sem_nota = [
        {
            "tipo_escola": 1,
            "cor_raca": 1,
            "renda_familiar": "C",
            # Notas de outras Areas presentes: nao devem "salvar" a linha.
            "nota_mt": 700.0,
            "nota_redacao": 800.0,
        }
        for _ in range(20)
    ]
    recorte = Recorte(filtros={Dimensao.TIPO_ESCOLA: "1"})

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)

        escrever_silver(raiz, EDICAO, com_nota)
        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=0))
        antes = analisar(catalogo, EDICAO, Area.CN, NOTA_SONDA, recorte, limiar=0)

        # Reescreve a mesma Edicao com as linhas de nota nula acrescentadas.
        escrever_silver(raiz, EDICAO, [*com_nota, *sem_nota])
        depois = analisar(catalogo, EDICAO, Area.CN, NOTA_SONDA, recorte, limiar=0)

    assert antes.tamanho_amostral == 12
    # As 20 linhas de nota_cn NULL nao participam da agregacao (Req 1.2).
    assert depois.tamanho_amostral == 12
