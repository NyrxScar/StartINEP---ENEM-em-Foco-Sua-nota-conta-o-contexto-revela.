"""Teste de propriedade da presenca da Capacidade nas respostas de ``POST /v1/analise``.

Property 9 (task 7.3) — **Toda resposta de analise carrega a Capacidade**: para
*qualquer* resposta de analise bem-sucedida, o campo de Capacidade da Edicao
consultada deve estar presente e coincidir com a capacidade derivada pelo
catalogo sobre a mesma *silver* (Req 2.5).

O ponto central desta propriedade e que a presenca da Capacidade **nao depende**
do regime de privacidade. Por isso cada exemplo sorteia o tamanho da amostra em
torno do ``Limite_Minimo_de_Agregacao`` (fixado em :data:`LIMIAR`), exercitando
os dois regimes:

* **amostra suficiente** (``>= LIMIAR``) -> resultado completo, com
  ``distribuicao``/``percentil``/``tamanho_amostral`` preenchidos;
* **amostra insuficiente** (``< LIMIAR``) -> ``estatisticamente_insuficiente``
  verdadeiro e os tres campos sensiveis nulos (Req 1.6/9.3).

Em **ambos** os casos a resposta deve trazer ``capacidade``: a guarda de
privacidade suprime as estatisticas, nunca os metadados de capacidade — que sao
justamente o que permite ao cliente saber o que a Edicao suporta.

A verificacao e de ponta a ponta pela borda HTTP (:class:`TestClient` sobre
``criar_app(Config(...))``), sobre *fixtures* Parquet minusculas escritas por
:mod:`fixtures_silver` no mesmo layout Hive da *silver* real. A equivalencia e
forte: as ``dimensoes_suportadas`` do corpo JSON sao comparadas com as que um
:class:`~radar_api.catalogo.Catalogo` deriva da mesma *silver*.

Cada exemplo cria seu proprio ``tempfile.TemporaryDirectory`` (em vez da fixture
``tmp_path`` do pytest) porque, sob ``@given``, o corpo do teste roda muitas
vezes enquanto uma fixture de escopo de funcao seria compartilhada entre os
exemplos — o diretorio proprio mantem cada exemplo isolado e deterministico.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.modelos import Area, Dimensao

# Limiar de agregacao fixado no teste (independe de variaveis de ambiente
# RADAR_*). O tamanho da amostra e sorteado *em torno* dele para que os dois
# regimes (suficiente / suprimido) aparecam entre os exemplos.
LIMIAR = 25

# UF unica das particoes escritas; todas as linhas caem nela, portanto um
# Recorte por ``uf_prova`` = esta UF nao remove nenhuma linha.
UF = "SP"

# Valor de ``tipo_escola`` gravado em todas as linhas. O recorte por essa
# dimensao usa o mesmo valor como texto (os filtros comparam
# ``CAST(coluna AS VARCHAR) = ?``), logo tambem preserva a amostra inteira.
TIPO_ESCOLA = 1

# Recortes sorteados: vazio (sem recorte, Req 1.3) ou um filtro em uma dimensao
# *suportada* pela Edicao gerada. Nenhum deles reduz a amostra, de modo que o
# regime de privacidade seja governado apenas pelo tamanho gerado. Dimensoes de
# perfil ficam de fora de proposito: elas seriam recusadas por capacidade
# (``PERFIL_NOTA_NAO_COMBINAVEL``) e esta propriedade fala de respostas
# bem-sucedidas.
_RECORTES = [
    {},
    {Dimensao.TIPO_ESCOLA.value: str(TIPO_ESCOLA)},
    {Dimensao.UF.value: UF},
]

_NOTAS_VALIDAS = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)


def _linhas(quantidade: int, area: Area) -> list[dict[str, Any]]:
    """Monta ``quantidade`` linhas com nota na Area e ``tipo_escola`` preenchido.

    As notas sao deterministicas (espalhadas em 0..1000) para que o unico eixo
    que muda o regime de privacidade seja ``quantidade``. ``regiao`` e inferida
    da UF pela fixture; ``uf_prova`` vem do caminho Hive. Nenhuma coluna de
    perfil socioeconomico e preenchida, portanto a Edicao gerada possui notas e
    suporta ``regiao``/``uf_prova``/``tipo_escola``.
    """
    return [
        {
            f"nota_{area.value}": float((i * 37) % 1001),
            "tipo_escola": TIPO_ESCOLA,
        }
        for i in range(quantidade)
    ]


@settings(max_examples=100, deadline=None)
@given(
    edicao=st.integers(min_value=2000, max_value=2100),
    area=st.sampled_from(list(Area)),
    quantidade=st.integers(min_value=1, max_value=60),
    nota_usuario=_NOTAS_VALIDAS,
    filtros=st.sampled_from(_RECORTES),
)
# Fronteiras do regime de privacidade: logo abaixo, exatamente no, e acima do
# limiar — e um recorte nao vazio no regime suprimido.
@example(edicao=2023, area=Area.CN, quantidade=LIMIAR - 1, nota_usuario=500.0, filtros={})
@example(edicao=2023, area=Area.CN, quantidade=LIMIAR, nota_usuario=500.0, filtros={})
@example(edicao=2024, area=Area.MT, quantidade=LIMIAR + 1, nota_usuario=0.0, filtros={})
@example(
    edicao=2025,
    area=Area.REDACAO,
    quantidade=1,
    nota_usuario=1000.0,
    filtros={Dimensao.TIPO_ESCOLA.value: str(TIPO_ESCOLA)},
)
def test_resposta_de_analise_carrega_capacidade(
    edicao: int,
    area: Area,
    quantidade: int,
    nota_usuario: float,
    filtros: dict[str, str],
) -> None:
    """Feature: radar-enem-analise-api, Property 9: Toda resposta de análise carrega a Capacidade

    **Validates: Requirements 2.5**

    Toda resposta bem-sucedida de ``POST /v1/analise`` traz ``capacidade``, com a
    Edicao consultada e os tres campos da Capacidade, e ela coincide com a que o
    catalogo deriva da mesma *silver* — inclusive quando a guarda de privacidade
    suprime distribuicao, percentil e tamanho amostral por amostra insuficiente.
    """
    with tempfile.TemporaryDirectory() as dir_tmp:
        raiz = Path(dir_tmp)
        escrever_silver(raiz, edicao, _linhas(quantidade, area), uf_padrao=UF)

        config = Config(silver_root=raiz, limiar_agregacao=LIMIAR)
        with TestClient(criar_app(config)) as cliente:
            resposta = cliente.post(
                "/v1/analise",
                json={
                    "edicao": edicao,
                    "area": area.value,
                    "nota": nota_usuario,
                    "recorte": {"filtros": filtros},
                },
            )
        # Capacidade derivada de forma independente, sobre a mesma *silver*.
        esperada = Catalogo(config).capacidade(edicao)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()

    # O regime de privacidade e o esperado para o tamanho gerado (Req 1.6/9.3) —
    # ancora que garante que os dois ramos sao realmente exercitados.
    suficiente = quantidade >= LIMIAR
    assert corpo["estatisticamente_insuficiente"] is not suficiente
    if suficiente:
        assert corpo["tamanho_amostral"] == quantidade
        assert corpo["distribuicao"] is not None
        assert corpo["percentil"] is not None
    else:
        assert corpo["tamanho_amostral"] is None
        assert corpo["distribuicao"] is None
        assert corpo["percentil"] is None

    # Property 9 (Req 2.5): a Capacidade esta presente nos DOIS regimes.
    assert "capacidade" in corpo
    capacidade = corpo["capacidade"]
    assert isinstance(capacidade, dict)
    assert capacidade["edicao"] == edicao
    assert {
        "dimensoes_suportadas",
        "possui_notas",
        "perfil_combinavel_com_notas",
    } <= set(capacidade)
    # A Edicao gerada tem notas em todas as linhas.
    assert capacidade["possui_notas"] is True

    # Equivalencia com a derivacao do catalogo (nao apenas presenca).
    assert set(capacidade["dimensoes_suportadas"]) == {
        dim.value for dim in esperada.dimensoes_suportadas
    }
    assert capacidade["possui_notas"] is esperada.possui_notas
    assert capacidade["perfil_combinavel_com_notas"] is esperada.perfil_combinavel_com_notas
    # As dimensoes efetivamente usadas no Recorte estao entre as suportadas.
    assert set(filtros) <= set(capacidade["dimensoes_suportadas"])
