"""Catalogo de Edicoes e linhagem no nivel de API — task 9.2.

Testes de **contrato HTTP** de ``GET /v1/edicoes`` e
``GET /v1/edicoes/{edicao}/capacidade``. A derivacao de Capacidade em si e
coberta no nivel do catalogo (``test_catalogo.py``) e pela Property 7
(``test_prop_capacidade.py``); aqui verifica-se o que apenas a borda pode
quebrar: a forma do corpo 200 (um **array** de ``InfoEdicao`` e uma
``Capacidade`` nua, exatamente o que o cliente tipado do frontend consome), a
degradacao da linhagem sem Manifesto (Req 5.3/5.4), a coerencia entre a
Capacidade embutida na listagem e a do endpoint dedicado, e a traducao de erros
pelos handlers ja registrados (404 ``EDICAO_AUSENTE``, 422 de rota).

Montagem identica a de ``test_app_comparacao.py``:
:class:`~fastapi.testclient.TestClient` sobre
``criar_app(Config(silver_root=..., limiar_agregacao=...))`` com uma *silver*
temporaria escrita por :func:`fixtures_silver.escrever_silver`. Como a Capacidade
e derivada **dos dados**, as tres Edicoes sinteticas reproduzem, por construcao
das colunas, as tres capacidades reais:

========================  ==================================================
Edicao sintetica          Colunas escritas
========================  ==================================================
:data:`EDICAO_COMPLETA`   notas **e** perfil na mesma linha (analoga a 2023)
:data:`EDICAO_SO_NOTAS`   notas, escola; perfil todo ``NULL`` (analoga a 2024)
:data:`EDICAO_SO_PERFIL`  perfil; todas as ``nota_*`` ``NULL`` (analoga a 2025)
========================  ==================================================

Nota de ambiente: ``radar_etl`` **nao** e importavel e nao ha arquivos de
Manifesto nesta *silver* temporaria, logo ``manifesto_id``/``data_carga`` vem
``None``. Isso e proposital: e o cenario da degradacao da Req 5.3/5.4 exercitada
por :func:`test_edicoes_sem_manifesto_ainda_sao_listadas_com_linhagem_nula`.

Cobertura: listagem como array ordenado com linhagem + Capacidade (Req 5.2);
linhagem ausente nao esconde a Edicao (Req 5.3/5.4); Capacidade coerente com as
colunas de cada Edicao (Req 2.1); consistencia interna entre os dois endpoints;
Edicao inexistente -> 404 ``EDICAO_AUSENTE`` (Req 5.4); *silver* vazia -> ``[]``;
``edicao`` nao inteira na rota -> 422 preservando o envelope.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver
from radar_api.app import CODIGO_REQUISICAO_INVALIDA, criar_app
from radar_api.config import Config
from radar_api.modelos import Dimensao

LIMIAR = 25
N_LINHAS = 30

# UF de todas as particoes: fixa a Dimensao REGIAO (derivada da UF pela fixture)
# e a Dimensao UF (coluna Hive do caminho) em *todas* as Edicoes.
UF = "SP"

# Notas e perfil na mesma linha: suporta perfil combinado com nota (como 2023).
EDICAO_COMPLETA = 2023
# Notas e colunas de escola, sem nenhuma coluna de perfil (como 2024).
EDICAO_SO_NOTAS = 2024
# Perfil sem nenhuma nota (como 2025).
EDICAO_SO_PERFIL = 2025
# Edicao que nao existe na *silver* de teste.
EDICAO_INEXISTENTE = 2099

TODAS_AS_EDICOES = [EDICAO_COMPLETA, EDICAO_SO_NOTAS, EDICAO_SO_PERFIL]

# Dimensoes que *toda* Edicao da fixture suporta: ``regiao`` e preenchida pela
# fixture a partir da UF e ``uf_prova`` vem do caminho Hive.
DIMS_GEOGRAFICAS = {Dimensao.REGIAO.value, Dimensao.UF.value}
DIMS_ESCOLA = {Dimensao.TIPO_ESCOLA.value, Dimensao.DEP_ADM.value}
DIMS_PERFIL_ESCRITAS = {Dimensao.RENDA.value, Dimensao.COR_RACA.value}

# Capacidade esperada por Edicao, derivada *das colunas escritas* abaixo.
# ``escolaridade_pai``/``escolaridade_mae`` nunca sao escritas, logo nenhuma
# Edicao as suporta.
DIMS_ESPERADAS: dict[int, set[str]] = {
    EDICAO_COMPLETA: DIMS_GEOGRAFICAS | DIMS_ESCOLA | DIMS_PERFIL_ESCRITAS,
    EDICAO_SO_NOTAS: DIMS_GEOGRAFICAS | DIMS_ESCOLA,
    EDICAO_SO_PERFIL: DIMS_GEOGRAFICAS | DIMS_PERFIL_ESCRITAS,
}


def _linhas_completas() -> list[dict[str, Any]]:
    """Linhas com ``nota_cn``, colunas de escola e perfil preenchidos."""
    return [
        {
            "nota_cn": float(i * 25),
            "renda_familiar": f"faixa_{i % 3}",
            "cor_raca": i % 5,
            "tipo_escola": 1,
            "dependencia_adm_escola": 2,
        }
        for i in range(N_LINHAS)
    ]


def _linhas_so_notas() -> list[dict[str, Any]]:
    """Linhas com notas e escola; todas as colunas de perfil ficam ``NULL``."""
    return [
        {
            "nota_cn": float(i * 25 + 10),
            "tipo_escola": 1,
            "dependencia_adm_escola": 2,
        }
        for i in range(N_LINHAS)
    ]


def _linhas_so_perfil() -> list[dict[str, Any]]:
    """Linhas de perfil sem nenhuma nota (todas as ``nota_*`` ``NULL``)."""
    return [{"renda_familiar": f"faixa_{i % 3}", "cor_raca": i % 5} for i in range(N_LINHAS)]


@pytest.fixture(scope="module")
def raiz_silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """*Silver* temporaria com as tres Edicoes sinteticas (somente leitura).

    Nenhum Manifesto e escrito: a linhagem degradada e parte do cenario testado.
    """
    raiz = tmp_path_factory.mktemp("silver_edicoes")
    escrever_silver(raiz, EDICAO_COMPLETA, _linhas_completas(), uf_padrao=UF)
    escrever_silver(raiz, EDICAO_SO_NOTAS, _linhas_so_notas(), uf_padrao=UF)
    escrever_silver(raiz, EDICAO_SO_PERFIL, _linhas_so_perfil(), uf_padrao=UF)
    return raiz


@pytest.fixture(scope="module")
def cliente(raiz_silver: Path) -> Iterator[TestClient]:
    """Cliente HTTP sobre a app apontando para :func:`raiz_silver`."""
    app = criar_app(Config(silver_root=raiz_silver, limiar_agregacao=LIMIAR))
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def cliente_silver_vazia(tmp_path: Path) -> Iterator[TestClient]:
    """Cliente sobre uma raiz de *silver* existente porem sem nenhuma Edicao."""
    app = criar_app(Config(silver_root=tmp_path, limiar_agregacao=LIMIAR))
    with TestClient(app) as cliente:
        yield cliente


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


def _por_edicao(corpo: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Indexa a listagem de ``GET /v1/edicoes`` por ``edicao``."""
    return {entrada["edicao"]: entrada for entrada in corpo}


# --------------------------------------------------------------------------- #
# GET /v1/edicoes — forma da listagem (Req 5.2)                               #
# --------------------------------------------------------------------------- #
def test_listagem_de_edicoes_e_um_array_ordenado_com_linhagem_e_capacidade(
    cliente: TestClient,
) -> None:
    """200 com um **array**, uma entrada por Edicao, em ordem crescente.

    A forma e o contrato consumido pelo cliente do frontend (``listarEdicoes``):
    uma lista de ``InfoEdicao`` com ``edicao``, a linhagem (``manifesto_id``,
    ``data_carga`` — Req 5.2) e a ``capacidade`` derivada (Req 2.1), sem
    envelope envolvente.
    """
    resposta = cliente.get("/v1/edicoes")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list)
    assert [entrada["edicao"] for entrada in corpo] == TODAS_AS_EDICOES
    for entrada in corpo:
        assert set(entrada) == {"edicao", "manifesto_id", "data_carga", "capacidade"}
        assert entrada["capacidade"]["edicao"] == entrada["edicao"]


def test_edicoes_sem_manifesto_ainda_sao_listadas_com_linhagem_nula(
    cliente: TestClient,
) -> None:
    """Sem Manifesto, a linhagem vem ``None`` — mas a Edicao **continua listada**.

    Esta e a garantia central da degradacao graciosa (Req 5.3/5.4): a *silver* e
    seus Manifestos sao contrato de entrada externo, e a ausencia da linhagem
    nunca pode esconder uma Edicao que existe nos dados — o cliente veria um
    catalogo incompleto em vez de um catalogo sem datas.
    """
    corpo = cliente.get("/v1/edicoes").json()

    assert [entrada["edicao"] for entrada in corpo] == TODAS_AS_EDICOES
    for entrada in corpo:
        assert entrada["manifesto_id"] is None
        assert entrada["data_carga"] is None


def test_silver_vazia_retorna_lista_vazia(cliente_silver_vazia: TestClient) -> None:
    """Raiz de *silver* sem Edicao alguma -> ``200 []``, nunca 500.

    Nao ha Edicao a listar, e isso nao e uma falha do servico: a resposta e um
    catalogo vazio (mesmo espirito de ``/health``, que degrada em vez de morrer).
    """
    resposta = cliente_silver_vazia.get("/v1/edicoes")

    assert resposta.status_code == 200
    assert resposta.json() == []


# --------------------------------------------------------------------------- #
# Capacidade coerente com o contrato/dados de cada Edicao (Req 2.1)           #
# --------------------------------------------------------------------------- #
def test_capacidade_de_cada_edicao_reflete_as_colunas_disponiveis(
    cliente: TestClient,
) -> None:
    """As ``dimensoes_suportadas`` de cada Edicao sao exatamente as esperadas.

    A Capacidade e derivada dos dados: uma dimensao e suportada sse a coluna
    tem ao menos um valor nao nulo na Edicao. ``escolaridade_pai``/
    ``escolaridade_mae`` nao sao escritas em nenhuma Edicao, logo nenhuma as
    suporta — a asercao e de igualdade, nao de continencia, para que uma
    derivacao permissiva demais tambem falhe.
    """
    por_edicao = _por_edicao(cliente.get("/v1/edicoes").json())

    for edicao, dims_esperadas in DIMS_ESPERADAS.items():
        capacidade = por_edicao[edicao]["capacidade"]
        assert set(capacidade["dimensoes_suportadas"]) == dims_esperadas


def test_edicao_so_com_notas_nao_combina_perfil_com_nota(cliente: TestClient) -> None:
    """Edicao com notas e sem perfil: ``possui_notas`` sem perfil combinavel.

    Reproduz 2024 (Req 9.2): existem notas, porem nenhuma dimensao de perfil, e
    portanto ``perfil_combinavel_com_notas`` e ``False`` e nenhuma dimensao de
    perfil aparece em ``dimensoes_suportadas``.
    """
    capacidade = _por_edicao(cliente.get("/v1/edicoes").json())[EDICAO_SO_NOTAS]["capacidade"]

    assert capacidade["possui_notas"] is True
    assert capacidade["perfil_combinavel_com_notas"] is False
    assert set(capacidade["dimensoes_suportadas"]).isdisjoint(DIMS_PERFIL_ESCRITAS)


def test_edicao_so_com_perfil_nao_possui_notas(cliente: TestClient) -> None:
    """Edicao sem nenhuma nota: ``possui_notas`` falso, perfil ainda suportado.

    Reproduz 2025 — o perfil existe e pode ser recortado, mas nao ha nota a
    posicionar, o que e exatamente o que o formulario precisa saber para
    desabilitar a submissao (Req 4.6).
    """
    capacidade = _por_edicao(cliente.get("/v1/edicoes").json())[EDICAO_SO_PERFIL]["capacidade"]

    assert capacidade["possui_notas"] is False
    assert capacidade["perfil_combinavel_com_notas"] is False
    assert DIMS_PERFIL_ESCRITAS <= set(capacidade["dimensoes_suportadas"])


def test_edicao_completa_combina_perfil_com_nota(cliente: TestClient) -> None:
    """Edicao com notas e perfil na mesma linha: combinacao permitida (como 2023).

    Contraparte necessaria dos dois testes acima: sem ela, uma implementacao que
    sempre respondesse ``perfil_combinavel_com_notas = False`` passaria.
    """
    capacidade = _por_edicao(cliente.get("/v1/edicoes").json())[EDICAO_COMPLETA]["capacidade"]

    assert capacidade["possui_notas"] is True
    assert capacidade["perfil_combinavel_com_notas"] is True


# --------------------------------------------------------------------------- #
# GET /v1/edicoes/{edicao}/capacidade                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("edicao", TODAS_AS_EDICOES)
def test_capacidade_do_endpoint_dedicado_e_um_objeto_nu(cliente: TestClient, edicao: int) -> None:
    """200 com a ``Capacidade`` *nua* (sem envelope nem embrulho).

    Forma consumida por ``obterCapacidade`` no cliente do frontend: os quatro
    campos do modelo no nivel de topo, com ``dimensoes_suportadas`` como array
    JSON.
    """
    resposta = cliente.get(f"/v1/edicoes/{edicao}/capacidade")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "edicao",
        "dimensoes_suportadas",
        "possui_notas",
        "perfil_combinavel_com_notas",
    }
    assert corpo["edicao"] == edicao
    assert isinstance(corpo["dimensoes_suportadas"], list)
    assert set(corpo["dimensoes_suportadas"]) == DIMS_ESPERADAS[edicao]


@pytest.mark.parametrize("edicao", TODAS_AS_EDICOES)
def test_capacidade_dedicada_coincide_com_a_embutida_na_listagem(
    cliente: TestClient, edicao: int
) -> None:
    """A Capacidade dos dois endpoints e a mesma (consistencia interna).

    Os dois caminhos leem o mesmo :class:`~radar_api.catalogo.Catalogo`; se
    divergissem, o formulario poderia filtrar dimensoes com base numa Capacidade
    diferente da que a analise vai aplicar. Comparacao insensivel a ordem do
    array (``dimensoes_suportadas`` vem de um ``set``).
    """
    embutida = _por_edicao(cliente.get("/v1/edicoes").json())[edicao]["capacidade"]
    dedicada = cliente.get(f"/v1/edicoes/{edicao}/capacidade").json()

    assert set(dedicada.pop("dimensoes_suportadas")) == set(embutida.pop("dimensoes_suportadas"))
    assert dedicada == embutida


def test_edicao_inexistente_retorna_404_edicao_ausente(cliente: TestClient) -> None:
    """Edicao sem particao na *silver* -> 404 ``EDICAO_AUSENTE`` (Req 5.4).

    O erro vem do handler de ``ErroRadar`` ja registrado, sem tratamento local
    na rota: o envelope legivel por maquina cita a Edicao pedida em ``detalhes``.
    """
    resposta = cliente.get(f"/v1/edicoes/{EDICAO_INEXISTENTE}/capacidade")

    assert resposta.status_code == 404
    detalhes = _assertar_envelope(resposta.json(), "EDICAO_AUSENTE")
    assert detalhes["edicao"] == EDICAO_INEXISTENTE


def test_edicao_nao_inteira_na_rota_retorna_422_no_envelope(cliente: TestClient) -> None:
    """``/v1/edicoes/abc/capacidade`` -> 422 preservando o formato do envelope.

    ``edicao`` fora da taxonomia nomeada pelo contrato (nao e ``nota`` nem
    ``area``) cai no codigo generico, com o campo violado em
    ``detalhes.violacoes`` — e nunca no ``{"detail": [...]}`` do FastAPI.
    """
    resposta = cliente.get("/v1/edicoes/abc/capacidade")

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), CODIGO_REQUISICAO_INVALIDA)
    assert [violacao["campo"] for violacao in detalhes["violacoes"]] == ["path.edicao"]
