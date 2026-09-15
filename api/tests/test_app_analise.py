"""Smoke test da camada HTTP (``radar_api.app``): ``/health`` e ``POST /v1/analise``.

Exercita a app real com :class:`~fastapi.testclient.TestClient` sobre uma
*silver* temporaria escrita por :func:`fixtures_silver.escrever_silver`, injetada
via ``criar_app(Config(silver_root=...))``. O objetivo aqui e **fumaca**: fluxo
felizs/erros representativos de cada requisito da task 7.1. A taxonomia de erros
exaustiva (task 7.5) e as propriedades P8/P9/P10 (tasks 7.2/7.3/7.4) sao cobertas
separadamente.

Cobre:

* ``GET /health`` -> 200 com a *silver* acessivel e **503 / degradado** quando a
  raiz nao existe, sem levantar excecao (Req 7.1);
* ``POST /v1/analise`` caminho feliz -> 200 com ``capacidade`` (Req 2.5) e
  ``linhagem`` (Req 5.1) no corpo;
* ``nota=1500`` -> 422 ``NOTA_FORA_INTERVALO`` (Req 1.8);
* ``area="xx"`` -> 422 ``AREA_INVALIDA`` (Req 1.1);
* Edicao inexistente -> 404 ``EDICAO_AUSENTE`` (Req 5.4);
* Edicao sem notas (todas as ``nota_*`` nulas) -> 409 ``EDICAO_SEM_NOTAS``
  (Req 2.3).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.config import Config

LIMIAR = 25

# Edicao com notas e perfil na mesma linha (analoga a 2023).
EDICAO_COM_NOTAS = 2023
# Edicao apenas de perfil, sem notas (analoga a 2025).
EDICAO_SEM_NOTAS = 2025
# Edicao inexistente na *silver* de teste.
EDICAO_AUSENTE = 2099


def _cliente(raiz: Path) -> TestClient:
    """Monta um :class:`TestClient` sobre uma app apontando para ``raiz``.

    O ``limiar_agregacao`` e fixado para que a supressao nao dependa de
    variaveis ``RADAR_*`` do ambiente de teste.
    """
    return TestClient(criar_app(Config(silver_root=raiz, limiar_agregacao=LIMIAR)))


@pytest.fixture
def cliente(tmp_path: Path) -> Iterator[TestClient]:
    """Cliente HTTP sobre uma *silver* com uma Edicao com notas e outra sem."""
    # 30 linhas (>= LIMIAR) com notas e perfil combinaveis.
    escrever_silver(
        tmp_path,
        EDICAO_COM_NOTAS,
        [
            {"nota_cn": float(i * 25), "tipo_escola": 1, "cor_raca": 1}
            for i in range(30)
        ],
    )
    # Edicao de perfil sem nenhuma nota (todas as ``nota_*`` NULL).
    escrever_silver(
        tmp_path,
        EDICAO_SEM_NOTAS,
        [{"cor_raca": 1, "tipo_escola": 2} for _ in range(30)],
    )
    with _cliente(tmp_path) as cliente:
        yield cliente


# --------------------------------------------------------------------------- #
# /health (Req 7.1)                                                           #
# --------------------------------------------------------------------------- #
def test_health_silver_acessivel(cliente: TestClient) -> None:
    """Com a *silver* legivel, ``/health`` responde 200 e lista as Edicoes."""
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["silver_acessivel"] is True
    assert corpo["edicoes"] == [EDICAO_COM_NOTAS, EDICAO_SEM_NOTAS]
    assert "ambiente_referencia" in corpo


def test_health_silver_inacessivel_degrada_sem_excecao(tmp_path: Path) -> None:
    """Raiz inexistente -> 503 ``degradado``, sem excecao (readiness vermelha)."""
    with _cliente(tmp_path / "silver_que_nao_existe") as cliente:
        resposta = cliente.get("/health")

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["status"] == "degradado"
    assert corpo["silver_acessivel"] is False
    assert corpo["edicoes"] == []


# --------------------------------------------------------------------------- #
# POST /v1/analise — caminho feliz (Req 1.1, 2.5, 5.1)                       #
# --------------------------------------------------------------------------- #
def test_analise_caminho_feliz_traz_capacidade_e_linhagem(cliente: TestClient) -> None:
    """200 com Distribuicao, Percentil, ``capacidade`` (Req 2.5) e ``linhagem`` (Req 5.1)."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": EDICAO_COM_NOTAS, "area": "cn", "nota": 375.0},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["edicao"] == EDICAO_COM_NOTAS
    assert corpo["estatisticamente_insuficiente"] is False
    assert corpo["tamanho_amostral"] == 30
    assert 0.0 <= corpo["percentil"] <= 100.0
    assert corpo["distribuicao"]["quantis"]["minimo"] == 0.0
    # Req 2.5 — a Capacidade da Edicao acompanha a resposta.
    capacidade = corpo["capacidade"]
    assert capacidade["edicao"] == EDICAO_COM_NOTAS
    assert capacidade["possui_notas"] is True
    # Req 5.1 — a Linhagem identifica as Edicoes usadas (manifesto pode ser nulo).
    assert corpo["linhagem"]["edicoes"] == [EDICAO_COM_NOTAS]
    assert str(EDICAO_COM_NOTAS) in corpo["linhagem"]["manifestos"]


# --------------------------------------------------------------------------- #
# POST /v1/analise — erros no envelope padronizado                            #
# --------------------------------------------------------------------------- #
def test_nota_fora_do_intervalo_retorna_422_categorizado(cliente: TestClient) -> None:
    """``nota=1500`` -> 422 ``NOTA_FORA_INTERVALO`` no envelope (Req 1.8)."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": EDICAO_COM_NOTAS, "area": "cn", "nota": 1500.0},
    )

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["codigo"] == "NOTA_FORA_INTERVALO"
    assert corpo["mensagem"]
    assert corpo["detalhes"]["maximo"] == 1000
    # O formato padrao do FastAPI nao pode vazar: o envelope e o contrato.
    assert "detail" not in corpo


def test_area_invalida_retorna_422_categorizado(cliente: TestClient) -> None:
    """``area="xx"`` -> 422 ``AREA_INVALIDA`` no envelope (Req 1.1)."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": EDICAO_COM_NOTAS, "area": "xx", "nota": 375.0},
    )

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["codigo"] == "AREA_INVALIDA"
    assert corpo["detalhes"]["area"] == "xx"
    assert "detail" not in corpo


def test_edicao_inexistente_retorna_404(cliente: TestClient) -> None:
    """Edicao fora da *silver* -> 404 ``EDICAO_AUSENTE`` (Req 5.4)."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": EDICAO_AUSENTE, "area": "cn", "nota": 375.0},
    )

    assert resposta.status_code == 404
    corpo = resposta.json()
    assert corpo["codigo"] == "EDICAO_AUSENTE"
    assert corpo["detalhes"]["edicao"] == EDICAO_AUSENTE


def test_edicao_sem_notas_retorna_409(cliente: TestClient) -> None:
    """Edicao apenas de perfil -> 409 ``EDICAO_SEM_NOTAS`` (Req 2.3)."""
    resposta = cliente.post(
        "/v1/analise",
        json={"edicao": EDICAO_SEM_NOTAS, "area": "cn", "nota": 375.0},
    )

    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["codigo"] == "EDICAO_SEM_NOTAS"
    assert corpo["detalhes"]["edicao"] == EDICAO_SEM_NOTAS
