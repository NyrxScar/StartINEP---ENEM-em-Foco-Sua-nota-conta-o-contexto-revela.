"""Taxonomia de erros no nivel de API (``POST /v1/analise``) — task 7.5.

Complementa o *smoke test* de ``radar_api.app`` (``test_app_analise.py``, task
7.1) com a cobertura **exaustiva** da taxonomia de erros no nivel HTTP: cada
codigo alcancavel por ``POST /v1/analise``, seus limites, o formato do envelope e
o teste de contrato da Req 9.2.

Reusa a mesma montagem do *smoke*: :class:`~fastapi.testclient.TestClient` sobre
``criar_app(Config(silver_root=..., limiar_agregacao=...))`` com uma *silver*
temporaria escrita por :func:`fixtures_silver.escrever_silver`. A Capacidade de
cada Edicao e derivada **dos dados** (o ETL ``radar_etl`` nao e dependencia da
API), portanto as tres Edicoes sinteticas abaixo reproduzem, por construcao das
colunas, as tres capacidades reais:

======================  ===================================================
Edicao sintetica        Colunas escritas
======================  ===================================================
:data:`EDICAO_COMPLETA` notas **e** perfil na mesma linha (analoga a 2023)
:data:`EDICAO_SO_NOTAS` notas presentes, perfil todo ``NULL`` (analoga a 2024)
:data:`EDICAO_SO_PERFIL` perfil presente, todas as ``nota_*`` ``NULL`` (2025)
======================  ===================================================

Cobertura desta suite:

* ``NOTA_FORA_INTERVALO`` (Req 1.8) — fora de 0..1000 e nao numerica **e** a
  aceitacao dos limites validos 0 e 1000 (a fronteira e inclusiva);
* ``AREA_INVALIDA`` (Req 1.1) — valores invalidos e a aceitacao das cinco Areas;
* ``EDICAO_AUSENTE`` (Req 5.4);
* ``EDICAO_SEM_NOTAS`` (Req 2.3);
* ``PERFIL_NOTA_NAO_COMBINAVEL`` (Req 2.4);
* ``RECORTE_INDISPONIVEL`` com ``edicoes_que_suportam`` (Req 2.2/2.6);
* formato do envelope (``codigo``/``mensagem``/``detalhes``, sem ``detail``);
* **contrato Req 9.2** — nenhum caminho junta perfil e notas na Edicao
  desidentificada (:func:`test_contrato_nenhum_caminho_junta_perfil_e_notas`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.catalogo import DIMENSOES_PERFIL
from radar_api.config import Config
from radar_api.modelos import Area, Dimensao

LIMIAR = 25
# Linhas por Edicao: acima do limiar, para que o caminho feliz seja 200 com
# resultado divulgado (e nao uma supressao por amostra insuficiente).
N_LINHAS = 30

# Notas e perfil na mesma linha: suporta todos os recortes (analoga a 2023).
EDICAO_COMPLETA = 2023
# Notas sem perfil: perfil desidentificado em arquivo separado (analoga a 2024).
EDICAO_SO_NOTAS = 2024
# Perfil sem nenhuma nota (analoga a 2025).
EDICAO_SO_PERFIL = 2025
# Edicao que nao existe na *silver* de teste.
EDICAO_AUSENTE = 2099

# Dimensao nao-perfil deixada NULL em EDICAO_SO_NOTAS: exercita a recusa
# *generica* RECORTE_INDISPONIVEL, distinta da recusa por perfil.
DIM_NAO_PERFIL_AUSENTE = Dimensao.TIPO_ESCOLA

AREAS = tuple(area.value for area in Area)


def _linhas_completas() -> list[dict[str, Any]]:
    """Linhas com todas as ``nota_*`` e todas as colunas de perfil preenchidas."""
    return [
        {
            "nota_cn": float(i * 25),
            "nota_ch": float(i * 25 + 1),
            "nota_lc": float(i * 25 + 2),
            "nota_mt": float(i * 25 + 3),
            "nota_redacao": float(i * 20),
            "renda_familiar": f"faixa_{i % 3}",
            "cor_raca": i % 5,
            "escolaridade_pai": f"nivel_{i % 4}",
            "escolaridade_mae": f"nivel_{i % 4}",
            "tipo_escola": 1 + i % 2,
            "dependencia_adm_escola": 2,
        }
        for i in range(N_LINHAS)
    ]


def _linhas_so_notas() -> list[dict[str, Any]]:
    """Linhas com notas e **nenhuma** coluna de perfil (perfil todo ``NULL``).

    ``tipo_escola`` tambem fica ``NULL`` de proposito: e a dimensao nao-perfil
    indisponivel usada para exercitar ``RECORTE_INDISPONIVEL``. ``regiao`` (e a
    ``uf_prova`` derivada do caminho) continuam disponiveis, como em 2024.
    """
    return [
        {
            "nota_cn": float(i * 25),
            "nota_ch": float(i * 25 + 1),
            "nota_lc": float(i * 25 + 2),
            "nota_mt": float(i * 25 + 3),
            "nota_redacao": float(i * 20),
            "dependencia_adm_escola": 2,
        }
        for i in range(N_LINHAS)
    ]


def _linhas_so_perfil() -> list[dict[str, Any]]:
    """Linhas de perfil sem nenhuma nota (todas as ``nota_*`` ``NULL``)."""
    return [
        {
            "renda_familiar": f"faixa_{i % 3}",
            "cor_raca": i % 5,
            "escolaridade_pai": f"nivel_{i % 4}",
            "escolaridade_mae": f"nivel_{i % 4}",
        }
        for i in range(N_LINHAS)
    ]


@pytest.fixture(scope="module")
def raiz_silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """*Silver* temporaria com as tres Edicoes sinteticas (somente leitura)."""
    raiz = tmp_path_factory.mktemp("silver_erros")
    escrever_silver(raiz, EDICAO_COMPLETA, _linhas_completas())
    escrever_silver(raiz, EDICAO_SO_NOTAS, _linhas_so_notas())
    escrever_silver(raiz, EDICAO_SO_PERFIL, _linhas_so_perfil())
    return raiz


@pytest.fixture(scope="module")
def cliente(raiz_silver: Path) -> Iterator[TestClient]:
    """Cliente HTTP sobre a app apontando para :func:`raiz_silver`.

    Escopo de modulo: as Edicoes sao somente leitura e a Capacidade derivada fica
    memoizada no :class:`~radar_api.catalogo.Catalogo`, evitando resondar o
    Parquet em cada caso parametrizado.
    """
    with TestClient(criar_app(Config(silver_root=raiz_silver, limiar_agregacao=LIMIAR))) as cliente:
        yield cliente


def _analisar(
    cliente: TestClient,
    *,
    edicao: int = EDICAO_COMPLETA,
    area: object = "cn",
    nota: object = 500.0,
    recorte: dict[str, str] | None = None,
) -> Any:
    """Faz ``POST /v1/analise`` e devolve a resposta (corpo sempre JSON)."""
    corpo: dict[str, Any] = {"edicao": edicao, "area": area, "nota": nota}
    if recorte is not None:
        corpo["recorte"] = {"filtros": recorte}
    return cliente.post("/v1/analise", json=corpo)


def _assertar_envelope(corpo: dict[str, Any], codigo: str) -> dict[str, Any]:
    """Valida o formato do envelope de erro e devolve seus ``detalhes``.

    O envelope ``{codigo, mensagem, detalhes}`` e o contrato de erro da API: o
    formato ``{"detail": ...}`` padrao do FastAPI nunca pode vazar.
    """
    assert set(corpo) == {"codigo", "mensagem", "detalhes"}
    assert corpo["codigo"] == codigo
    assert isinstance(corpo["mensagem"], str)
    assert corpo["mensagem"].strip()
    assert isinstance(corpo["detalhes"], dict)
    assert "detail" not in corpo
    detalhes: dict[str, Any] = corpo["detalhes"]
    return detalhes


# --------------------------------------------------------------------------- #
# NOTA_FORA_INTERVALO (Req 1.8)                                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nota", [-1500.0, -1.0, -0.01, 1000.01, 1001.0, 1500.0])
def test_nota_fora_do_intervalo_e_rejeitada(cliente: TestClient, nota: float) -> None:
    """Qualquer nota fora de 0..1000 -> 422 ``NOTA_FORA_INTERVALO`` (Req 1.8)."""
    resposta = _analisar(cliente, nota=nota)

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "NOTA_FORA_INTERVALO")
    assert detalhes["minimo"] == 0
    assert detalhes["maximo"] == 1000
    assert detalhes["nota"] == pytest.approx(nota)


@pytest.mark.parametrize("nota", [0.0, 0.01, 999.99, 1000.0])
def test_limites_validos_da_nota_sao_aceitos(cliente: TestClient, nota: float) -> None:
    """Os limites 0 e 1000 sao **inclusivos**: a recusa nao pode ser exagerada.

    Contraparte necessaria do teste anterior — sem ela, uma implementacao que
    rejeitasse *toda* nota passaria na verificacao de Req 1.8.
    """
    resposta = _analisar(cliente, nota=nota)

    assert resposta.status_code == 200
    assert resposta.json()["edicao"] == EDICAO_COMPLETA


@pytest.mark.parametrize("nota", ["abc", "", None, "500,0", [500.0]])
def test_nota_nao_numerica_e_rejeitada(cliente: TestClient, nota: object) -> None:
    """Nota nao numerica tambem cai em ``NOTA_FORA_INTERVALO`` (Req 1.8).

    O envelope entao omite ``detalhes.nota`` (nao ha valor numerico a citar), mas
    mantem os limites do intervalo valido.
    """
    resposta = _analisar(cliente, nota=nota)

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "NOTA_FORA_INTERVALO")
    assert detalhes["minimo"] == 0
    assert detalhes["maximo"] == 1000
    assert "nota" not in detalhes


# --------------------------------------------------------------------------- #
# AREA_INVALIDA (Req 1.1)                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("area", ["xx", "", "CN ", "CN", "cn ", "matematica", "nota_cn"])
def test_area_invalida_e_rejeitada(cliente: TestClient, area: str) -> None:
    """Area fora de cn/ch/lc/mt/redacao -> 422 ``AREA_INVALIDA`` (Req 1.1)."""
    resposta = _analisar(cliente, area=area)

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "AREA_INVALIDA")
    # O valor recebido e ecoado, para que o cliente saiba o que foi rejeitado.
    assert detalhes["area"] == area
    assert detalhes["areas_validas"] == list(AREAS)


@pytest.mark.parametrize("area", AREAS)
def test_areas_validas_sao_aceitas(cliente: TestClient, area: str) -> None:
    """As cinco Areas do contrato sao aceitas na Edicao com todas as notas."""
    resposta = _analisar(cliente, area=area)

    assert resposta.status_code == 200
    assert resposta.json()["area"] == area


def test_nota_tem_precedencia_sobre_area_quando_ambas_invalidas(
    cliente: TestClient,
) -> None:
    """Com ``nota`` e ``area`` invalidas, a resposta e deterministica: nota primeiro."""
    resposta = _analisar(cliente, area="xx", nota=1500.0)

    assert resposta.status_code == 422
    _assertar_envelope(resposta.json(), "NOTA_FORA_INTERVALO")


def test_campo_fora_do_contrato_usa_codigo_generico(cliente: TestClient) -> None:
    """Campo invalido fora de ``nota``/``area`` -> ``REQUISICAO_INVALIDA``, no envelope."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": "nao-e-um-ano", "area": "cn", "nota": 500.0},
    )

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "REQUISICAO_INVALIDA")
    assert [violacao["campo"] for violacao in detalhes["violacoes"]] == ["edicao"]


# --------------------------------------------------------------------------- #
# EDICAO_AUSENTE (Req 5.4)                                                    #
# --------------------------------------------------------------------------- #
def test_edicao_sem_particao_na_silver_retorna_404(cliente: TestClient) -> None:
    """Edicao sem diretorio ``ano=`` -> 404 ``EDICAO_AUSENTE`` (Req 5.4)."""
    resposta = _analisar(cliente, edicao=EDICAO_AUSENTE)

    assert resposta.status_code == 404
    detalhes = _assertar_envelope(resposta.json(), "EDICAO_AUSENTE")
    assert detalhes["edicao"] == EDICAO_AUSENTE


# --------------------------------------------------------------------------- #
# EDICAO_SEM_NOTAS (Req 2.3)                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("area", AREAS)
def test_edicao_sem_notas_recusa_qualquer_area(cliente: TestClient, area: str) -> None:
    """Edicao so de perfil -> 409 ``EDICAO_SEM_NOTAS`` para toda Area (Req 2.3)."""
    resposta = _analisar(cliente, edicao=EDICAO_SO_PERFIL, area=area)

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "EDICAO_SEM_NOTAS")
    assert detalhes["edicao"] == EDICAO_SO_PERFIL


def test_edicao_sem_notas_recusa_antes_de_avaliar_o_recorte(cliente: TestClient) -> None:
    """A ausencia de notas e a recusa mais fundamental: precede a do recorte."""
    resposta = _analisar(
        cliente,
        edicao=EDICAO_SO_PERFIL,
        recorte={DIM_NAO_PERFIL_AUSENTE.value: "1"},
    )

    assert resposta.status_code == 409
    _assertar_envelope(resposta.json(), "EDICAO_SEM_NOTAS")


# --------------------------------------------------------------------------- #
# PERFIL_NOTA_NAO_COMBINAVEL (Req 2.4)                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("dimensao", DIMENSOES_PERFIL, ids=lambda dim: dim.value)
def test_perfil_com_nota_na_edicao_desidentificada_retorna_409(
    cliente: TestClient, dimensao: Dimensao
) -> None:
    """Recorte de perfil + nota -> 409 ``PERFIL_NOTA_NAO_COMBINAVEL`` (Req 2.4).

    O codigo tem de ser o *especifico*: dizer apenas ``RECORTE_INDISPONIVEL``
    esconderia do cliente a razao real (perfil e notas nao sao unificaveis nessa
    Edicao) e sugeriria que outro valor de filtro poderia funcionar.
    """
    resposta = _analisar(cliente, edicao=EDICAO_SO_NOTAS, recorte={dimensao.value: "qualquer"})

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "PERFIL_NOTA_NAO_COMBINAVEL")
    assert detalhes["edicao"] == EDICAO_SO_NOTAS
    assert detalhes["dimensao"] == dimensao.value


def test_perfil_com_nota_e_aceito_quando_a_edicao_combina(cliente: TestClient) -> None:
    """Na Edicao com perfil *na mesma linha*, o mesmo recorte e aceito (200)."""
    resposta = _analisar(cliente, edicao=EDICAO_COMPLETA, recorte={Dimensao.RENDA.value: "faixa_0"})

    assert resposta.status_code == 200
    assert resposta.json()["capacidade"]["perfil_combinavel_com_notas"] is True


# --------------------------------------------------------------------------- #
# RECORTE_INDISPONIVEL (Req 2.2, 2.6)                                         #
# --------------------------------------------------------------------------- #
def test_dimensao_nao_perfil_indisponivel_retorna_409_com_edicoes_que_suportam(
    cliente: TestClient,
) -> None:
    """Dimensao nao-perfil ausente -> 409 ``RECORTE_INDISPONIVEL`` (Req 2.2/2.6).

    ``detalhes.edicoes_que_suportam`` orienta o cliente: apenas a Edicao que
    escreveu ``tipo_escola`` aparece; a Edicao pedida nunca se lista a si mesma.
    """
    resposta = _analisar(
        cliente, edicao=EDICAO_SO_NOTAS, recorte={DIM_NAO_PERFIL_AUSENTE.value: "1"}
    )

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "RECORTE_INDISPONIVEL")
    assert detalhes["edicao"] == EDICAO_SO_NOTAS
    assert detalhes["dimensao"] == DIM_NAO_PERFIL_AUSENTE.value
    assert detalhes["edicoes_que_suportam"] == [EDICAO_COMPLETA]


def test_dimensao_de_particao_disponivel_e_aceita(cliente: TestClient) -> None:
    """Recorte por ``regiao``/``uf_prova`` funciona na Edicao so de notas.

    Delimita a recusa anterior: o que falta em 2024 e o perfil (e as colunas de
    escola nao publicadas), nao o recorte geografico.
    """
    resposta = _analisar(
        cliente,
        edicao=EDICAO_SO_NOTAS,
        recorte={Dimensao.REGIAO.value: "Sudeste", Dimensao.UF.value: "SP"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["tamanho_amostral"] == N_LINHAS


# --------------------------------------------------------------------------- #
# Formato do envelope (contrato de erro)                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("caso", "status", "codigo"),
    [
        ({"nota": 1500.0}, 422, "NOTA_FORA_INTERVALO"),
        ({"area": "xx"}, 422, "AREA_INVALIDA"),
        ({"edicao": EDICAO_AUSENTE}, 404, "EDICAO_AUSENTE"),
        ({"edicao": EDICAO_SO_PERFIL}, 409, "EDICAO_SEM_NOTAS"),
        (
            {"edicao": EDICAO_SO_NOTAS, "recorte": {Dimensao.RENDA.value: "faixa_0"}},
            409,
            "PERFIL_NOTA_NAO_COMBINAVEL",
        ),
        (
            {
                "edicao": EDICAO_SO_NOTAS,
                "recorte": {DIM_NAO_PERFIL_AUSENTE.value: "1"},
            },
            409,
            "RECORTE_INDISPONIVEL",
        ),
    ],
    ids=["nota", "area", "edicao_ausente", "sem_notas", "perfil_nota", "recorte"],
)
def test_todo_erro_usa_o_envelope_padronizado(
    cliente: TestClient, caso: dict[str, Any], status: int, codigo: str
) -> None:
    """Todo erro responde ``{codigo, mensagem, detalhes}`` — nunca ``{"detail":...}``."""
    resposta = _analisar(cliente, **caso)

    assert resposta.status_code == status
    _assertar_envelope(resposta.json(), codigo)


# --------------------------------------------------------------------------- #
# Contrato Req 9.2 — nenhum caminho junta perfil e notas de 2024              #
# --------------------------------------------------------------------------- #
def test_contrato_nenhum_caminho_junta_perfil_e_notas(cliente: TestClient) -> None:
    """Req 9.2 — na Edicao desidentificada, perfil + nota **nunca** produz 200.

    Este e o teste de contrato central da restricao definidora do produto: em
    2024 o INEP publicou perfil (``PARTICIPANTES``) e notas (``RESULTADOS``) em
    arquivos separados, desidentificados, com chaves e ordens de linha distintas
    — uni-los seria uma tentativa de reidentificacao. Logo, para **toda**
    combinacao de dimensao de perfil e Area, a requisicao tem de ser recusada com
    um codigo de capacidade; nenhuma resposta 200 e admissivel, nem mesmo uma
    suprimida por amostra insuficiente (que ainda revelaria que o cruzamento foi
    executado).

    O laco varre o produto cartesiano ``DIMENSOES_PERFIL`` x ``Area`` para que o
    contrato valha por construcao, e nao apenas no caso testado a mao.
    """
    for dimensao in DIMENSOES_PERFIL:
        for area in AREAS:
            resposta = _analisar(
                cliente,
                edicao=EDICAO_SO_NOTAS,
                area=area,
                recorte={dimensao.value: "qualquer"},
            )
            contexto = f"dimensao={dimensao.value} area={area}"
            assert resposta.status_code == 409, contexto
            corpo = resposta.json()
            assert corpo["codigo"] == "PERFIL_NOTA_NAO_COMBINAVEL", contexto
            assert corpo["detalhes"]["dimensao"] == dimensao.value, contexto


def test_capacidade_da_edicao_desidentificada_declara_perfil_nao_combinavel(
    cliente: TestClient,
) -> None:
    """A recusa e visivel *antes* da tentativa: a Capacidade ja a declara (Req 2.5).

    Uma analise sem recorte da Edicao so de notas retorna 200 e informa
    ``possui_notas=True`` com ``perfil_combinavel_com_notas=False``, e nenhuma
    dimensao de perfil entre as suportadas — deixando o cliente (e o Frontend)
    filtrar as opcoes sem precisar provocar o erro.
    """
    resposta = _analisar(cliente, edicao=EDICAO_SO_NOTAS)

    assert resposta.status_code == 200
    capacidade = resposta.json()["capacidade"]
    assert capacidade["edicao"] == EDICAO_SO_NOTAS
    assert capacidade["possui_notas"] is True
    assert capacidade["perfil_combinavel_com_notas"] is False
    suportadas = set(capacidade["dimensoes_suportadas"])
    assert suportadas.isdisjoint({dim.value for dim in DIMENSOES_PERFIL})
