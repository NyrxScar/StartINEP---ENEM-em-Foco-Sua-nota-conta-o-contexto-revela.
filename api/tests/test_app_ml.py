"""Modelo_ML no nivel de API (``POST /v1/ml/inferencia``) — task 11.2.

Testes de **contrato HTTP**. O *gating*, o carregamento *lazy* e a classificacao
de falhas do Modelo_ML sao cobertos no nivel do modulo (``test_ml.py``, task
11.1); aqui verifica-se apenas o que a borda pode quebrar: que a rota existe e
delega, que os erros do ML chegam ao cliente no envelope padronizado com **409**
(e nao como 500 nem como ``{"detail": ...}``), que a saida 200 sai rotulada como
modelo/2023 (Req 8.4) e que a validacao de entrada e a mesma herdada das outras
rotas.

Montagem identica a de ``test_app_erros.py``/``test_app_comparacao.py``:
:class:`~fastapi.testclient.TestClient` sobre
``criar_app(Config(silver_root=..., ...))`` com uma *silver* temporaria escrita
por :func:`fixtures_silver.escrever_silver`. A *silver* e necessaria porque o
ultimo teste e a **guarda de regressao** da Req 8.2: com o ML desabilitado,
``POST /v1/analise`` continua respondendo 200 — o nucleo estatistico nao depende
do Modelo_ML.

O artefato do caminho feliz e um objeto *picklavel* (:class:`ArtefatoDeTeste`,
definido no escopo do modulo) serializado com o ``pickle`` da biblioteca padrao,
que e o carregador de fallback de :mod:`radar_api.ml`. Nenhuma biblioteca de ML
e necessaria para rodar esta suite.

Cobertura:

* ML desabilitado (o padrao da :class:`~radar_api.config.Config`) -> 409
  ``ML_DESABILITADO``, no envelope;
* habilitado sem ``ml_artefato`` -> 409 ``ML_INDISPONIVEL`` /
  ``artefato_nao_configurado``;
* habilitado com caminho inexistente -> 409 ``ML_INDISPONIVEL`` /
  ``artefato_inexistente``;
* habilitado com artefato valido -> 200 rotulado ``origem="modelo"``,
  ``edicao=2023``, com ``valor_previsto`` numerico e ``modelo_id`` (Req 8.4);
* ``area`` invalida -> 422 ``AREA_INVALIDA`` pelo handler de validacao herdado;
* regressao Req 8.2 — analise estatistica intacta com o ML desabilitado.
"""

from __future__ import annotations

import pickle
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.config import Config
from radar_api.ml import EDICAO_ML, MOTIVOS, limpar_cache
from radar_api.modelos import Area, Dimensao

LIMIAR = 25
# Linhas acima do limiar, para que a analise da guarda de regressao divulgue o
# resultado (e nao uma supressao por amostra insuficiente).
N_LINHAS = 30

# Edicao com notas e perfil na mesma linha (analoga a 2023) — a unica escrita
# nesta *silver*, ja que o ML tambem e restrito a ela.
EDICAO_COMPLETA = 2023

# Valor base do artefato de teste, para conferir a previsao esperada.
BASE_PREVISAO = 480.0

# Corpo valido de inferencia reusado pelos casos de erro.
ENTRADA_VALIDA: dict[str, Any] = {
    "area": Area.CN.value,
    "perfil": {Dimensao.REGIAO.value: "Sudeste", Dimensao.TIPO_ESCOLA.value: "1"},
}


class ArtefatoDeTeste:
    """Artefato minimo e *picklavel* que satisfaz o protocolo ``prever``.

    Definido no escopo do modulo para poder ser serializado com ``pickle`` — e
    assim exercitar o carregador **padrao** de :mod:`radar_api.ml` de ponta a
    ponta, sem nenhuma biblioteca de ML instalada e sem injetar carregador
    (a rota nao expoe esse ponto de extensao).
    """

    def __init__(self, base: float = BASE_PREVISAO) -> None:
        self.base = base

    def prever(self, caracteristicas: Mapping[str, str]) -> float:
        """Previsao deterministica: base + 10 por caracteristica informada."""
        return self.base + 10.0 * len(caracteristicas)


@pytest.fixture(autouse=True)
def _cache_limpo() -> Iterator[None]:
    """Isola o cache de modelos entre testes (a memoizacao e global ao modulo)."""
    limpar_cache()
    yield
    limpar_cache()


@pytest.fixture(scope="module")
def raiz_silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """*Silver* temporaria com a Edicao completa (somente leitura)."""
    raiz = tmp_path_factory.mktemp("silver_ml")
    escrever_silver(
        raiz,
        EDICAO_COMPLETA,
        [
            {
                "nota_cn": float(i * 25),
                "renda_familiar": f"faixa_{i % 3}",
                "cor_raca": i % 5,
                "tipo_escola": 1,
                "dependencia_adm_escola": 2,
            }
            for i in range(N_LINHAS)
        ],
    )
    return raiz


def _cliente(raiz_silver: Path, **ml: Any) -> TestClient:
    """Monta um cliente sobre a app com a configuracao de ML pedida."""
    config = Config(silver_root=raiz_silver, limiar_agregacao=LIMIAR, **ml)
    return TestClient(criar_app(config))


def _escrever_artefato(caminho: Path, objeto: object) -> Path:
    """Serializa ``objeto`` em ``caminho`` com ``pickle`` (stdlib)."""
    with caminho.open("wb") as arquivo:
        pickle.dump(objeto, arquivo)
    return caminho


def _assertar_envelope(corpo: dict[str, Any], codigo: str) -> dict[str, Any]:
    """Valida o envelope de erro da API e devolve seus ``detalhes``.

    O envelope ``{codigo, mensagem, detalhes}`` e o contrato de erro: o formato
    ``{"detail": ...}`` do FastAPI nunca pode vazar — nem por uma rota nova.
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
# Registro da rota                                                            #
# --------------------------------------------------------------------------- #
def test_rota_de_inferencia_esta_registrada(raiz_silver: Path) -> None:
    """A app expoe ``POST /v1/ml/inferencia`` independentemente do *gating*.

    A rota existe sempre; o que muda com ``ml_habilitado`` e a **resposta**, nao
    a existencia do recurso — assim o cliente distingue "nao implantado" (409
    categorizado) de "nao existe" (404 do roteador).
    """
    app = criar_app(Config(silver_root=raiz_silver))
    rotas = {(rota.path, tuple(sorted(rota.methods))) for rota in app.routes}  # type: ignore[attr-defined]

    assert ("/v1/ml/inferencia", ("POST",)) in rotas


# --------------------------------------------------------------------------- #
# ML desabilitado (padrao da implantacao) — 409 ML_DESABILITADO               #
# --------------------------------------------------------------------------- #
def test_ml_desabilitado_responde_409_categorizado(raiz_silver: Path) -> None:
    """Config padrao (ML desabilitado) -> 409 ``ML_DESABILITADO`` no envelope."""
    with _cliente(raiz_silver) as cliente:
        assert cliente.app.state.config.ml_habilitado is False  # type: ignore[attr-defined]
        resposta = cliente.post("/v1/ml/inferencia", json=ENTRADA_VALIDA)

    assert resposta.status_code == 409
    corpo = resposta.json()
    detalhes = _assertar_envelope(corpo, "ML_DESABILITADO")
    assert detalhes["ml_habilitado"] is False
    assert "detail" not in corpo


# --------------------------------------------------------------------------- #
# ML habilitado, porem inutilizavel — 409 ML_INDISPONIVEL + motivo            #
# --------------------------------------------------------------------------- #
def test_habilitado_sem_artefato_configurado_responde_409(raiz_silver: Path) -> None:
    """``ml_habilitado`` sem ``ml_artefato`` -> ``artefato_nao_configurado``."""
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=None) as cliente:
        resposta = cliente.post("/v1/ml/inferencia", json=ENTRADA_VALIDA)

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "ML_INDISPONIVEL")
    assert detalhes["motivo"] == "artefato_nao_configurado"
    assert detalhes["motivo"] in MOTIVOS


def test_habilitado_com_artefato_inexistente_responde_409(
    raiz_silver: Path, tmp_path: Path
) -> None:
    """Caminho de artefato inexistente -> ``artefato_inexistente``.

    A falha e do ambiente de implantacao, nao da requisicao: por isso e um 409
    categorizado, com o caminho ecoado para o operador diagnosticar.
    """
    ausente = tmp_path / "nao_existe.pkl"
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=ausente) as cliente:
        resposta = cliente.post("/v1/ml/inferencia", json=ENTRADA_VALIDA)

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "ML_INDISPONIVEL")
    assert detalhes["motivo"] == "artefato_inexistente"
    assert detalhes["artefato"] == str(ausente)


# --------------------------------------------------------------------------- #
# Caminho feliz — 200 rotulado modelo/2023 (Req 8.4)                          #
# --------------------------------------------------------------------------- #
def test_inferencia_bem_sucedida_e_rotulada_como_modelo_2023(
    raiz_silver: Path, tmp_path: Path
) -> None:
    """Artefato valido -> 200 com ``origem="modelo"`` e ``edicao=2023`` (Req 8.4).

    Os rotulos sao o ponto do requisito: qualquer consumidor sabe, sem inspecao
    adicional, que ``valor_previsto`` e saida de modelo (nao uma estatistica
    observada da *silver*) e que se refere apenas a Edicao 2023.
    """
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoDeTeste())
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=artefato) as cliente:
        resposta = cliente.post("/v1/ml/inferencia", json=ENTRADA_VALIDA)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"] == "modelo"
    assert corpo["edicao"] == EDICAO_ML == 2023
    assert corpo["area"] == Area.CN.value
    assert isinstance(corpo["valor_previsto"], float)
    # Duas caracteristicas informadas -> base + 2 * 10 (artefato deterministico).
    assert corpo["valor_previsto"] == pytest.approx(BASE_PREVISAO + 20.0)
    assert corpo["modelo_id"].startswith("modelo.pkl@")


def test_inferencia_aceita_perfil_vazio(raiz_silver: Path, tmp_path: Path) -> None:
    """``perfil`` e opcional: sem ele a rota ainda responde 200 rotulado."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoDeTeste())
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=artefato) as cliente:
        resposta = cliente.post("/v1/ml/inferencia", json={"area": Area.MT.value})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["area"] == Area.MT.value
    assert corpo["origem"] == "modelo"
    assert corpo["valor_previsto"] == pytest.approx(BASE_PREVISAO)


# --------------------------------------------------------------------------- #
# Validacao de entrada herdada                                                #
# --------------------------------------------------------------------------- #
def test_area_invalida_usa_o_handler_de_validacao_herdado(
    raiz_silver: Path, tmp_path: Path
) -> None:
    """``area`` invalida -> 422 ``AREA_INVALIDA``, mesmo com o ML habilitado.

    A rota nao registra tratamento proprio: o handler de
    :class:`~fastapi.exceptions.RequestValidationError` da app ja converte a
    violacao no codigo do contrato. A recusa acontece **antes** do handler, logo
    nem o artefato e tocado.
    """
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoDeTeste())
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=artefato) as cliente:
        resposta = cliente.post("/v1/ml/inferencia", json={"area": "xx", "perfil": {}})

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "AREA_INVALIDA")
    assert detalhes["area"] == "xx"


def test_dimensao_de_perfil_desconhecida_usa_codigo_generico(
    raiz_silver: Path, tmp_path: Path
) -> None:
    """Chave de perfil fora das Dimensoes canonicas -> 422 ``REQUISICAO_INVALIDA``."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoDeTeste())
    with _cliente(raiz_silver, ml_habilitado=True, ml_artefato=artefato) as cliente:
        resposta = cliente.post(
            "/v1/ml/inferencia",
            json={"area": Area.CN.value, "perfil": {"nao_existe": "x"}},
        )

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "REQUISICAO_INVALIDA")
    assert detalhes["violacoes"]


# --------------------------------------------------------------------------- #
# Regressao Req 8.2 — o nucleo nao depende do Modelo_ML                       #
# --------------------------------------------------------------------------- #
def test_analise_estatistica_intacta_com_ml_desabilitado(raiz_silver: Path) -> None:
    """Req 8.2/8.3 — com o ML desabilitado, ``POST /v1/analise`` responde 200.

    Guarda de regressao da rota nova: registrar o endpoint de ML (e importar
    :mod:`radar_api.ml` no escopo de ``app.py``) nao pode introduzir dependencia
    do produto estatistico central no Modelo_ML. A mesma app que recusa a
    inferencia com 409 entrega a analise normalmente.
    """
    with _cliente(raiz_silver) as cliente:
        inferencia = cliente.post("/v1/ml/inferencia", json=ENTRADA_VALIDA)
        analise = cliente.post(
            "/v1/analise",
            json={"edicao": EDICAO_COMPLETA, "area": Area.CN.value, "nota": 500.0},
        )

    assert inferencia.status_code == 409
    assert inferencia.json()["codigo"] == "ML_DESABILITADO"

    assert analise.status_code == 200
    corpo = analise.json()
    assert corpo["edicao"] == EDICAO_COMPLETA
    assert corpo["tamanho_amostral"] == N_LINHAS
    assert corpo["estatisticamente_insuficiente"] is False
