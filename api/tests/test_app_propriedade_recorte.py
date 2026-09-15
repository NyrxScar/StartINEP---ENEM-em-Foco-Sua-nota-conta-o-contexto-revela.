# A etiqueta obrigatoria da propriedade (primeira linha do docstring do teste)
# precisa casar *exatamente* com o texto do design — "Feature:
# radar-enem-analise-api, Property 8: Rejeição de Recorte referenciando dimensão
# indisponível" tem 100 caracteres, que somados ao recuo e as aspas passam do
# limite de 100 colunas e nao podem ser quebrados sem alterar a etiqueta. E501 e
# desligado neste arquivo por isso; nenhuma outra linha aqui excede o limite.
# ruff: noqa: E501
"""Teste de propriedade da rejeicao de Recorte com dimensao indisponivel.

Property 8 (task 7.2) — **Rejeicao de Recorte referenciando dimensao
indisponivel**: para *qualquer* requisicao cujo Recorte contenha uma Dimensao
ausente da Capacidade da Edicao, a requisicao deve ser **rejeitada** com um
codigo de erro categorizado que identifique a dimensao e a Edicao (Req 2.2) e
que aponte quais Edicoes suportam aquele recorte (Req 2.6) — nunca um resultado
silencioso ou parcial.

A propriedade e exercitada **de ponta a ponta pela borda HTTP** (``POST
/v1/analise`` com :class:`~fastapi.testclient.TestClient`), pois o que se afirma
e sobre a *resposta* observada pelo cliente: status, codigo, detalhes e a
**ausencia** de qualquer carga analitica no corpo.

*Silver* de teste (escrita por :mod:`fixtures_silver` no layout Hive real
``ano=<edicao>/uf_prova=<UF>``), com duas Edicoes:

* :data:`EDICAO_ALVO` — possui notas em todas as Areas e suporta ``regiao``/
  ``uf_prova``, mas tem ``tipo_escola`` e ``dependencia_adm_escola``
  **inteiramente NULL**. Como a Capacidade e derivada *dos dados* (uma Dimensao
  e suportada sse sua coluna tem ao menos um valor nao nulo na Edicao), essas
  duas dimensoes ficam **indisponiveis** nesta Edicao — sem precisar simular
  contrato algum.
* :data:`EDICAO_SUPORTA` — popula ``tipo_escola`` e ``dependencia_adm_escola``,
  de modo que ``detalhes.edicoes_que_suportam`` seja **nao vazia** e possa ser
  verificada (Req 2.6): a orientacao acionavel so tem valor se apontar uma
  Edicao concreta.

**Por que apenas dimensoes nao-perfil sao sorteadas.** A guarda de capacidade
(``nucleo.verificar_capacidade_recorte``) aplica as verificacoes da mais
especifica para a mais generica: ``EDICAO_SEM_NOTAS`` -> ``PERFIL_NOTA_NAO_
COMBINAVEL`` -> ``RECORTE_INDISPONIVEL``. Numa Edicao *com* notas e *sem* perfil,
uma dimensao de perfil (``renda_familiar``, ``cor_raca``, ``escolaridade_pai``,
``escolaridade_mae``) satisfaz simultaneamente as duas ultimas condicoes e
produz — corretamente — o codigo mais informativo ``PERFIL_NOTA_NAO_COMBINAVEL``.
Para que a assercao sobre ``RECORTE_INDISPONIVEL`` seja **afiada** (e nao um
"um destes codigos serve"), a dimensao indisponivel sorteada e restrita as
nao-perfil :data:`DIMENSOES_INDISPONIVEIS`. O ramo de perfil e coberto pelos
requisitos 2.3/2.4 em outros testes.

Cada TemporaryDirectory e criado *dentro* do corpo do teste (nunca a fixture
``tmp_path`` do pytest junto de ``@given``, que seria compartilhada entre os
exemplos) e removido ao fim do ``with``.

Nao-vacuidade: :func:`test_recorte_apenas_com_dimensoes_suportadas_e_aceito`
mostra que a mesma Edicao **aceita** (200) um Recorte que usa somente dimensoes
suportadas — logo a propriedade nao esta simplesmente recusando tudo.

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
from radar_api.config import Config
from radar_api.modelos import Area, Dimensao

# Limiar fixado no teste para nao depender de variaveis ``RADAR_*`` do ambiente.
LIMIAR = 25

# Edicao alvo do pedido: tem notas, mas ``tipo_escola``/``dependencia_adm_escola``
# sao inteiramente NULL -> essas dimensoes sao indisponiveis nela.
EDICAO_ALVO = 2024
# Edicao que popula essas colunas -> aparece em ``edicoes_que_suportam`` (Req 2.6).
EDICAO_SUPORTA = 2023

# Linhas da Edicao alvo (>= LIMIAR para que o caso aceito produza Distribuicao).
LINHAS_ALVO = 30
# A Edicao de apoio so precisa ter as colunas nao nulas; o tamanho e irrelevante.
LINHAS_SUPORTE = 5

# UF (e portanto ``regiao``) das particoes da Edicao alvo.
UF_ALVO = "SP"
REGIAO_ALVO = "Sudeste"

# Dimensoes deixadas NULL na Edicao alvo. Ambas sao **nao-perfil**, o que garante
# que a guarda de capacidade chegue ao ramo ``RECORTE_INDISPONIVEL`` (ver docstring
# do modulo).
DIMENSOES_INDISPONIVEIS = (Dimensao.TIPO_ESCOLA, Dimensao.DEP_ADM)

# Dimensoes suportadas pela Edicao alvo, usadas para (a) compor um Recorte
# parcialmente valido e (b) o teste de nao-vacuidade.
FILTRO_SUPORTADO = {Dimensao.REGIAO.value: REGIAO_ALVO}

# Chaves de carga analitica que **nao** podem aparecer numa resposta de rejeicao.
CHAVES_ANALITICAS = ("distribuicao", "percentil", "tamanho_amostral", "capacidade")


def _escrever_silver_de_teste(raiz: Path) -> None:
    """Escreve a *silver* de duas Edicoes usada por todos os testes deste modulo.

    ``EDICAO_ALVO`` recebe notas em **todas** as Areas (para que qualquer Area
    sorteada seja analisavel) e omite ``tipo_escola``/``dependencia_adm_escola``,
    que assim ficam NULL no Parquet — a Capacidade derivada dos dados nao as
    considera suportadas. ``EDICAO_SUPORTA`` popula justamente essas colunas.
    """
    escrever_silver(
        raiz,
        EDICAO_ALVO,
        [
            {f"nota_{area.value}": float(indice * 25) for area in Area}
            for indice in range(LINHAS_ALVO)
        ],
        uf_padrao=UF_ALVO,
    )
    escrever_silver(
        raiz,
        EDICAO_SUPORTA,
        [
            {
                "tipo_escola": 1,
                "dependencia_adm_escola": 2,
                **{f"nota_{area.value}": 500.0 for area in Area},
            }
            for _ in range(LINHAS_SUPORTE)
        ],
        uf_padrao=UF_ALVO,
    )


def _cliente(raiz: Path) -> TestClient:
    """Monta um :class:`TestClient` sobre uma app apontando para ``raiz``."""
    return TestClient(criar_app(Config(silver_root=raiz, limiar_agregacao=LIMIAR)))


def _corpo_requisicao(area: Area, nota: float, filtros: dict[str, str]) -> dict[str, Any]:
    """Monta o JSON de ``POST /v1/analise`` para a Edicao alvo."""
    return {
        "edicao": EDICAO_ALVO,
        "area": area.value,
        "nota": nota,
        "recorte": {"filtros": filtros},
    }


@settings(max_examples=100, deadline=None)
@given(
    area=st.sampled_from(list(Area)),
    nota=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    dimensao=st.sampled_from(DIMENSOES_INDISPONIVEIS),
    valor=st.text(max_size=8),
    com_filtro_suportado=st.booleans(),
)
# Limites do intervalo de nota, com e sem uma dimensao suportada acompanhando.
@example(
    area=Area.CN,
    nota=0.0,
    dimensao=Dimensao.TIPO_ESCOLA,
    valor="1",
    com_filtro_suportado=False,
)
@example(
    area=Area.REDACAO,
    nota=1000.0,
    dimensao=Dimensao.DEP_ADM,
    valor="2",
    com_filtro_suportado=True,
)
# Valor de filtro vazio: a rejeicao depende da dimensao, nunca do valor pedido.
@example(
    area=Area.MT,
    nota=500.0,
    dimensao=Dimensao.TIPO_ESCOLA,
    valor="",
    com_filtro_suportado=True,
)
def test_recorte_com_dimensao_indisponivel_e_rejeitado(
    area: Area,
    nota: float,
    dimensao: Dimensao,
    valor: str,
    com_filtro_suportado: bool,
) -> None:
    """Feature: radar-enem-analise-api, Property 8: Rejeição de Recorte referenciando dimensão indisponível

    **Validates: Requirements 2.2**

    Para qualquer Area, qualquer nota valida, qualquer valor de filtro e qualquer
    Dimensao ausente da Capacidade da Edicao, ``POST /v1/analise`` responde
    **409 ``RECORTE_INDISPONIVEL``** no envelope padronizado, citando a
    ``dimensao`` e a ``edicao`` (Req 2.2) e listando as Edicoes que suportam o
    recorte (Req 2.6) — sem qualquer carga analitica no corpo, isto e, nunca um
    resultado silencioso ou parcial.
    """
    filtros = {dimensao.value: valor}
    if com_filtro_suportado:
        # A dimensao indisponivel e rejeitada mesmo acompanhada de um filtro valido.
        filtros.update(FILTRO_SUPORTADO)

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        _escrever_silver_de_teste(raiz)
        with _cliente(raiz) as cliente:
            resposta = cliente.post("/v1/analise", json=_corpo_requisicao(area, nota, filtros))

    # P8 (Req 2.2): violacao de capacidade -> 409, nunca 200.
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["codigo"] == "RECORTE_INDISPONIVEL"
    assert corpo["mensagem"]

    # O erro identifica a dimensao pedida e a Edicao alvo (Req 2.2).
    detalhes = corpo["detalhes"]
    assert detalhes["dimensao"] == dimensao.value
    assert detalhes["edicao"] == EDICAO_ALVO

    # Req 2.6: a orientacao acionavel aponta uma Edicao concreta que suporta o
    # recorte — e nao a Edicao que acabou de recusa-lo.
    suportam = detalhes["edicoes_que_suportam"]
    assert isinstance(suportam, list)
    assert EDICAO_SUPORTA in suportam
    assert EDICAO_ALVO not in suportam

    # O envelope e o contrato: o formato ``{"detail": ...}`` do FastAPI nao vaza.
    assert "detail" not in corpo
    assert set(corpo) == {"codigo", "mensagem", "detalhes"}
    # Rejeicao completa: nenhuma carga analitica (nem parcial) acompanha o erro.
    for chave in CHAVES_ANALITICAS:
        assert chave not in corpo


def test_recorte_apenas_com_dimensoes_suportadas_e_aceito() -> None:
    """Guarda de nao-vacuidade: a mesma Edicao aceita um Recorte suportado.

    Sobre a *silver* identica a da propriedade, um Recorte que usa apenas
    dimensoes com valores nao nulos na Edicao alvo (``regiao`` e ``uf_prova``)
    responde **200** com Distribuicao e Percentil. Ou seja, o 409 da propriedade
    decorre especificamente da dimensao indisponivel — a borda nao esta recusando
    todo e qualquer Recorte.
    """
    filtros = {Dimensao.REGIAO.value: REGIAO_ALVO, Dimensao.UF.value: UF_ALVO}

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        _escrever_silver_de_teste(raiz)
        with _cliente(raiz) as cliente:
            resposta = cliente.post("/v1/analise", json=_corpo_requisicao(Area.CN, 375.0, filtros))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["edicao"] == EDICAO_ALVO
    assert corpo["estatisticamente_insuficiente"] is False
    assert corpo["tamanho_amostral"] == LINHAS_ALVO
    assert 0.0 <= corpo["percentil"] <= 100.0
    assert corpo["distribuicao"] is not None
