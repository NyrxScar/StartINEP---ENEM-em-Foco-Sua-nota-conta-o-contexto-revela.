"""Testes de ``POST /v1/exploracao``: agregacao por valor de uma Dimensao.

A rota responde "como esta Area se distribui entre os valores desta Dimensao?".
O que precisa ser garantido aqui, e que nenhum outro teste cobre:

* os grupos saem **do maior para o menor**, com desempate estavel;
* a guarda de privacidade age **grupo a grupo** — grupo abaixo do limiar volta
  com quantis anulados e ``estatisticamente_insuficiente``, mas com o ``valor``
  ainda visivel (Req 1.6/9.3);
* o ``recorte`` e aplicado **antes** do agrupamento;
* linhas com a Dimensao nula ficam de fora, em vez de virarem um grupo ``NULL``;
* agrupar por uma Dimensao que a Edicao nao publica produz a **mesma** taxonomia
  de erro que filtrar por ela (Req 2.2/2.6).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver_fixture
from radar_api.app import criar_app
from radar_api.config import Config

LIMIAR = 25
EDICAO = 2023


def _linhas(n: int, nota: float, **extra: object) -> list[dict[str, object]]:
    """``n`` linhas identicas com ``nota_mt = nota``."""
    return [{"nota_mt": nota, **extra} for _ in range(n)]


@pytest.fixture
def cliente(tmp_path: Path) -> Iterator[TestClient]:
    # SP: 30 urbanas (acima do limiar) + 5 rurais (abaixo) + 3 sem escola.
    # MG: 26 urbanas, todas acima do limiar.
    # BA: 10 urbanas — UF inteira abaixo do limiar.
    escrever_silver_fixture(
        tmp_path,
        {
            (EDICAO, "SP"): [
                *_linhas(30, 600.0, localizacao_escola=1, municipio_prova="Sao Paulo"),
                *_linhas(5, 400.0, localizacao_escola=2, municipio_prova="Sao Paulo"),
                *_linhas(3, 500.0, municipio_prova="Campinas"),
            ],
            (EDICAO, "MG"): _linhas(26, 700.0, localizacao_escola=1, municipio_prova="Uberaba"),
            (EDICAO, "BA"): _linhas(10, 300.0, localizacao_escola=1, municipio_prova="Salvador"),
        },
    )
    app = criar_app(Config(silver_root=tmp_path, limiar_agregacao=LIMIAR))
    with TestClient(app) as c:
        yield c


def _explorar(cliente: TestClient, dimensao: str, **extra: object) -> dict:
    resposta = cliente.post(
        "/v1/exploracao",
        json={"edicao": EDICAO, "area": "mt", "dimensao": dimensao, **extra},
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_agrupa_por_uf_do_maior_para_o_menor(cliente: TestClient) -> None:
    corpo = _explorar(cliente, "uf_prova")
    valores = [g["valor"] for g in corpo["grupos"]]
    assert valores == ["SP", "MG", "BA"]
    assert [g["tamanho_amostral"] for g in corpo["grupos"]] == [38, 26, None]
    assert corpo["dimensao"] == "uf_prova"
    assert corpo["grupos_truncados"] is False


def test_grupo_abaixo_do_limiar_e_suprimido_mas_continua_visivel(cliente: TestClient) -> None:
    """A supressao anula os numeros sem esconder que o grupo existe (Req 9.3)."""
    grupos = {g["valor"]: g for g in _explorar(cliente, "uf_prova")["grupos"]}

    bahia = grupos["BA"]
    assert bahia["estatisticamente_insuficiente"] is True
    assert bahia["tamanho_amostral"] is None
    assert bahia["quantis"] is None

    sao_paulo = grupos["SP"]
    assert sao_paulo["estatisticamente_insuficiente"] is False
    assert sao_paulo["quantis"]["mediana"] == pytest.approx(600.0)


def test_linhas_com_dimensao_nula_nao_viram_um_grupo(cliente: TestClient) -> None:
    """As 3 linhas de SP sem escola nao podem virar um grupo ``NULL``."""
    corpo = _explorar(cliente, "localizacao_escola")
    valores = {g["valor"] for g in corpo["grupos"]}
    assert valores == {"1", "2"}
    assert None not in valores and "None" not in valores

    urbana = next(g for g in corpo["grupos"] if g["valor"] == "1")
    # 30 de SP + 26 de MG + 10 da BA, e nao as 3 linhas sem localizacao.
    assert urbana["tamanho_amostral"] == 66


def test_recorte_e_aplicado_antes_do_agrupamento(cliente: TestClient) -> None:
    corpo = _explorar(cliente, "localizacao_escola", recorte={"filtros": {"uf_prova": "SP"}})
    grupos = {g["valor"]: g for g in corpo["grupos"]}

    assert grupos["1"]["tamanho_amostral"] == 30
    # As 5 rurais de SP ficam abaixo do limiar quando o recorte isola SP.
    assert grupos["2"]["estatisticamente_insuficiente"] is True


def test_dimensao_nao_publicada_pela_edicao_e_recusada(cliente: TestClient) -> None:
    """Agrupar por Dimensao ausente erra igual a filtrar por ela (Req 2.2/2.6)."""
    resposta = cliente.post(
        "/v1/exploracao",
        json={"edicao": EDICAO, "area": "mt", "dimensao": "codigo_escola"},
    )
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["codigo"] == "RECORTE_INDISPONIVEL"
    assert corpo["detalhes"]["dimensao"] == "codigo_escola"


def test_dimensao_invalida_e_requisicao_invalida(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/v1/exploracao",
        json={"edicao": EDICAO, "area": "mt", "dimensao": "cor_do_teclado"},
    )
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "REQUISICAO_INVALIDA"


def test_resposta_carrega_capacidade_e_linhagem(cliente: TestClient) -> None:
    corpo = _explorar(cliente, "uf_prova")
    assert corpo["capacidade"]["edicao"] == EDICAO
    assert corpo["linhagem"]["edicoes"] == [EDICAO]
