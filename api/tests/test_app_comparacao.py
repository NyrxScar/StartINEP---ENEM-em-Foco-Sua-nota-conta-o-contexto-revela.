"""Comparacao entre Edicoes no nivel de API (``POST /v1/comparacao``) — task 8.4.

Testes de **contrato HTTP**. A logica de elegibilidade em si e coberta no nivel do
nucleo (``test_nucleo_comparar.py``, task 8.1) e pela propriedade P11
(``test_prop_comparar.py``, task 8.3); aqui verifica-se o que apenas a borda pode
quebrar: a forma do corpo 200 (``resultados`` rotulados + ``omissoes`` com
``codigo``), a *particao* das Edicoes pedidas entre os dois campos, a traducao do
409 ``COMPARACAO_SEM_EDICOES_ELEGIVEIS`` pelo handler de ``ErroRadar`` e a
validacao de entrada herdada de ``RequisicaoComparacao``.

Montagem identica a de ``test_app_analise.py``/``test_app_erros.py``:
:class:`~fastapi.testclient.TestClient` sobre
``criar_app(Config(silver_root=..., limiar_agregacao=...))`` com uma *silver*
temporaria escrita por :func:`fixtures_silver.escrever_silver`. Como a Capacidade
e derivada **dos dados**, as tres Edicoes sinteticas abaixo reproduzem, por
construcao das colunas, as tres capacidades reais:

========================  =================================================
Edicao sintetica          Colunas escritas
========================  =================================================
:data:`EDICAO_COMPLETA`   notas **e** perfil na mesma linha (analoga a 2023)
:data:`EDICAO_SO_NOTAS`   notas; perfil e ``tipo_escola`` todos ``NULL`` (2024)
:data:`EDICAO_SO_PERFIL`  perfil; todas as ``nota_*`` ``NULL`` (analoga a 2025)
========================  =================================================

Cobertura: caminho feliz com 2+ elegiveis (Req 3.1/3.4/5.1); elegibilidade
parcial com ``EDICAO_SEM_NOTAS`` e ``RECORTE_INDISPONIVEL`` em ``omissoes``
(Req 3.2); Edicao inexistente -> ``EDICAO_AUSENTE``; nenhuma elegivel -> 409
(Req 3.3); validacao herdada (``NOTA_FORA_INTERVALO``, ``AREA_INVALIDA``,
``edicoes`` vazia); deduplicacao e ordem crescente.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.config import Config
from radar_api.modelos import Dimensao

LIMIAR = 25
# Linhas por Edicao: acima do limiar, para que o caminho feliz divulgue o
# resultado (e nao uma supressao por amostra insuficiente).
N_LINHAS = 30

# Notas e perfil na mesma linha: suporta todos os recortes (analoga a 2023).
EDICAO_COMPLETA = 2023
# Notas sem perfil e sem ``tipo_escola`` (analoga a 2024).
EDICAO_SO_NOTAS = 2024
# Perfil sem nenhuma nota (analoga a 2025).
EDICAO_SO_PERFIL = 2025
# Edicao que nao existe na *silver* de teste.
EDICAO_INEXISTENTE = 2099

# Dimensao nao-perfil escrita apenas em EDICAO_COMPLETA: exercita a omissao
# *generica* RECORTE_INDISPONIVEL na Edicao so de notas.
DIM_SO_NA_COMPLETA = Dimensao.TIPO_ESCOLA


def _linhas_completas() -> list[dict[str, Any]]:
    """Linhas com ``nota_cn`` e todas as colunas de perfil preenchidas."""
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
    """Linhas com notas e perfil todo ``NULL``; ``tipo_escola`` tambem ``NULL``."""
    return [{"nota_cn": float(i * 25 + 10), "dependencia_adm_escola": 2} for i in range(N_LINHAS)]


def _linhas_so_perfil() -> list[dict[str, Any]]:
    """Linhas de perfil sem nenhuma nota (todas as ``nota_*`` ``NULL``)."""
    return [{"renda_familiar": f"faixa_{i % 3}", "cor_raca": i % 5} for i in range(N_LINHAS)]


@pytest.fixture(scope="module")
def raiz_silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """*Silver* temporaria com as tres Edicoes sinteticas (somente leitura)."""
    raiz = tmp_path_factory.mktemp("silver_comparacao")
    escrever_silver(raiz, EDICAO_COMPLETA, _linhas_completas())
    escrever_silver(raiz, EDICAO_SO_NOTAS, _linhas_so_notas())
    escrever_silver(raiz, EDICAO_SO_PERFIL, _linhas_so_perfil())
    return raiz


@pytest.fixture(scope="module")
def cliente(raiz_silver: Path) -> Iterator[TestClient]:
    """Cliente HTTP sobre a app apontando para :func:`raiz_silver`.

    Escopo de modulo: as Edicoes sao somente leitura e a Capacidade derivada fica
    memoizada no :class:`~radar_api.catalogo.Catalogo`.
    """
    app = criar_app(Config(silver_root=raiz_silver, limiar_agregacao=LIMIAR))
    with TestClient(app) as cliente:
        yield cliente


def _comparar(
    cliente: TestClient,
    *,
    edicoes: object = (EDICAO_COMPLETA, EDICAO_SO_NOTAS),
    area: object = "cn",
    nota: object = 500.0,
    recorte: dict[str, str] | None = None,
) -> Any:
    """Faz ``POST /v1/comparacao`` e devolve a resposta (corpo sempre JSON)."""
    corpo: dict[str, Any] = {
        "edicoes": list(edicoes) if isinstance(edicoes, tuple) else edicoes,
        "area": area,
        "nota": nota,
    }
    if recorte is not None:
        corpo["recorte"] = {"filtros": recorte}
    return cliente.post("/v1/comparacao", json=corpo)


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


def _assertar_particao(corpo: dict[str, Any], pedidas: set[int]) -> None:
    """Toda Edicao pedida aparece em **exatamente um** de ``resultados``/``omissoes``.

    Esta e a garantia central do contrato de comparacao: uma Edicao ou produz
    resultado (Req 3.1) ou e explicitamente omitida com motivo (Req 3.2) — nunca
    desaparece em silencio, nem e contada duas vezes.
    """
    em_resultados = [r["edicao"] for r in corpo["resultados"]]
    em_omissoes = [o["edicao"] for o in corpo["omissoes"]]
    assert len(set(em_resultados)) == len(em_resultados)
    assert len(set(em_omissoes)) == len(em_omissoes)
    assert set(em_resultados).isdisjoint(em_omissoes)
    assert set(em_resultados) | set(em_omissoes) == pedidas


# --------------------------------------------------------------------------- #
# Caminho feliz: 2+ Edicoes elegiveis (Req 3.1, 3.4, 5.1)                     #
# --------------------------------------------------------------------------- #
def test_comparacao_com_duas_edicoes_elegiveis(cliente: TestClient) -> None:
    """200 com um resultado rotulado por Edicao elegivel, sem omissoes.

    Ambas as Edicoes tem notas e o Recorte e vazio, portanto as duas sao
    elegiveis (Req 3.1); cada resultado se identifica pela sua ``edicao``
    (Req 3.4) e carrega ``capacidade`` (Req 2.5) e ``linhagem`` (Req 5.1).
    """
    resposta = _comparar(cliente)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [
        EDICAO_COMPLETA,
        EDICAO_SO_NOTAS,
    ]
    assert corpo["omissoes"] == []
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_SO_NOTAS})
    for resultado in corpo["resultados"]:
        assert resultado["area"] == "cn"
        assert resultado["estatisticamente_insuficiente"] is False
        assert resultado["tamanho_amostral"] == N_LINHAS
        assert 0.0 <= resultado["percentil"] <= 100.0
        # Req 2.5 — cada resultado traz a Capacidade da sua propria Edicao.
        assert resultado["capacidade"]["edicao"] == resultado["edicao"]
        # Req 5.1 — e a Linhagem da Edicao que o fundamenta.
        assert resultado["linhagem"]["edicoes"] == [resultado["edicao"]]
        assert str(resultado["edicao"]) in resultado["linhagem"]["manifestos"]


def test_comparacao_deduplica_e_ordena_as_edicoes(cliente: TestClient) -> None:
    """``[2024, 2023, 2024]`` -> uma entrada por Edicao distinta, em ordem crescente.

    A resposta nao pode depender da ordem nem da repeticao no pedido: o corpo e
    deterministico e cada Edicao e analisada uma unica vez.
    """
    resposta = _comparar(cliente, edicoes=(EDICAO_SO_NOTAS, EDICAO_COMPLETA, EDICAO_SO_NOTAS))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [
        EDICAO_COMPLETA,
        EDICAO_SO_NOTAS,
    ]
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_SO_NOTAS})


# --------------------------------------------------------------------------- #
# Elegibilidade parcial: omissao com motivo (Req 3.2)                         #
# --------------------------------------------------------------------------- #
def test_edicao_sem_notas_e_omitida_com_motivo(cliente: TestClient) -> None:
    """A Edicao so de perfil sai de ``resultados`` e entra em ``omissoes``.

    O motivo e o codigo *especifico* ``EDICAO_SEM_NOTAS`` (Req 3.2): a Edicao nao
    tem notas, logo nao ha percentil a calcular, mas isso nao invalida a
    comparacao das demais.
    """
    resposta = _comparar(cliente, edicoes=(EDICAO_COMPLETA, EDICAO_SO_NOTAS, EDICAO_SO_PERFIL))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [
        EDICAO_COMPLETA,
        EDICAO_SO_NOTAS,
    ]
    assert corpo["omissoes"] == [{"edicao": EDICAO_SO_PERFIL, "codigo": "EDICAO_SEM_NOTAS"}]
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_SO_NOTAS, EDICAO_SO_PERFIL})


def test_recorte_indisponivel_em_uma_edicao_gera_omissao(cliente: TestClient) -> None:
    """Recorte por dimensao que so uma Edicao possui -> a outra e omitida.

    ``tipo_escola`` esta preenchido apenas em :data:`EDICAO_COMPLETA`; na Edicao
    so de notas a coluna e toda ``NULL``, logo a dimensao nao e suportada e a
    omissao usa ``RECORTE_INDISPONIVEL`` (Req 3.2).
    """
    resposta = _comparar(
        cliente,
        edicoes=(EDICAO_COMPLETA, EDICAO_SO_NOTAS),
        recorte={DIM_SO_NA_COMPLETA.value: "1"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [EDICAO_COMPLETA]
    assert corpo["omissoes"] == [{"edicao": EDICAO_SO_NOTAS, "codigo": "RECORTE_INDISPONIVEL"}]
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_SO_NOTAS})


def test_perfil_com_nota_omite_a_edicao_desidentificada(cliente: TestClient) -> None:
    """Recorte de perfil + nota: a Edicao desidentificada e omitida, nao unida.

    Contraparte da Req 9.2 no caminho de comparacao — o codigo e o especifico
    ``PERFIL_NOTA_NAO_COMBINAVEL``, e a Edicao nunca aparece em ``resultados``.
    """
    resposta = _comparar(
        cliente,
        edicoes=(EDICAO_COMPLETA, EDICAO_SO_NOTAS),
        recorte={Dimensao.RENDA.value: "faixa_0"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [EDICAO_COMPLETA]
    assert corpo["omissoes"] == [
        {"edicao": EDICAO_SO_NOTAS, "codigo": "PERFIL_NOTA_NAO_COMBINAVEL"}
    ]
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_SO_NOTAS})


def test_edicao_inexistente_e_omitida_com_edicao_ausente(cliente: TestClient) -> None:
    """Edicao sem particao na *silver* -> ``omissoes`` com ``EDICAO_AUSENTE``.

    Diferente de ``POST /v1/analise`` (onde a Edicao ausente e um 404), na
    comparacao ela e apenas uma omissao: as Edicoes existentes continuam a ser
    comparadas (Req 3.2).
    """
    resposta = _comparar(cliente, edicoes=(EDICAO_COMPLETA, EDICAO_INEXISTENTE))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [EDICAO_COMPLETA]
    assert corpo["omissoes"] == [{"edicao": EDICAO_INEXISTENTE, "codigo": "EDICAO_AUSENTE"}]
    _assertar_particao(corpo, {EDICAO_COMPLETA, EDICAO_INEXISTENTE})


# --------------------------------------------------------------------------- #
# Nenhuma Edicao elegivel (Req 3.3)                                           #
# --------------------------------------------------------------------------- #
def test_nenhuma_edicao_elegivel_retorna_409(cliente: TestClient) -> None:
    """Sem nenhuma Edicao elegivel -> 409 ``COMPARACAO_SEM_EDICOES_ELEGIVEIS``.

    Uma comparacao vazia nao e um resultado valido (Req 3.3): o nucleo levanta e
    o handler de ``ErroRadar`` ja registrado traduz para o envelope, sem que a
    rota trate o erro localmente.
    """
    resposta = _comparar(cliente, edicoes=(EDICAO_SO_PERFIL, EDICAO_INEXISTENTE))

    assert resposta.status_code == 409
    detalhes = _assertar_envelope(resposta.json(), "COMPARACAO_SEM_EDICOES_ELEGIVEIS")
    assert detalhes["edicoes"] == [EDICAO_SO_PERFIL, EDICAO_INEXISTENTE]


def test_recorte_que_nenhuma_edicao_suporta_retorna_409(cliente: TestClient) -> None:
    """Recorte por dimensao ausente em todas as Edicoes -> 409 (Req 3.3)."""
    resposta = _comparar(
        cliente,
        edicoes=(EDICAO_COMPLETA, EDICAO_SO_NOTAS),
        recorte={Dimensao.ESCOLARIDADE_PAI.value: "nivel_0"},
    )

    assert resposta.status_code == 409
    _assertar_envelope(resposta.json(), "COMPARACAO_SEM_EDICOES_ELEGIVEIS")


# --------------------------------------------------------------------------- #
# Validacao de entrada herdada da borda                                       #
# --------------------------------------------------------------------------- #
def test_nota_fora_do_intervalo_retorna_422(cliente: TestClient) -> None:
    """``nota=1500`` -> 422 ``NOTA_FORA_INTERVALO``, como em ``/v1/analise`` (Req 1.8).

    Os limites de ``RequisicaoComparacao.nota`` sao os mesmos de
    ``RequisicaoAnalise.nota``, portanto o mapeamento de codigo e herdado sem
    tratamento novo na rota.
    """
    resposta = _comparar(cliente, nota=1500.0)

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "NOTA_FORA_INTERVALO")
    assert detalhes["minimo"] == 0
    assert detalhes["maximo"] == 1000


def test_area_invalida_retorna_422(cliente: TestClient) -> None:
    """``area="xx"`` -> 422 ``AREA_INVALIDA`` no envelope."""
    resposta = _comparar(cliente, area="xx")

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "AREA_INVALIDA")
    assert detalhes["area"] == "xx"


def test_lista_de_edicoes_vazia_retorna_422(cliente: TestClient) -> None:
    """``edicoes: []`` -> 422 ``REQUISICAO_INVALIDA`` citando o campo.

    Uma comparacao sem Edicao alguma nao e interpretavel; ``min_length=1``
    recusa na borda, e o envelope segue o formato padrao (o campo violado
    aparece em ``detalhes.violacoes``).
    """
    resposta = _comparar(cliente, edicoes=[])

    assert resposta.status_code == 422
    detalhes = _assertar_envelope(resposta.json(), "REQUISICAO_INVALIDA")
    assert [violacao["campo"] for violacao in detalhes["violacoes"]] == ["edicoes"]


def test_uma_unica_edicao_e_aceita(cliente: TestClient) -> None:
    """Uma Edicao so e um pedido valido: a recusa da lista vazia nao e exagerada.

    Contraparte necessaria do teste anterior — sem ela, uma implementacao que
    exigisse duas Edicoes passaria na verificacao acima.
    """
    resposta = _comparar(cliente, edicoes=(EDICAO_COMPLETA,))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [r["edicao"] for r in corpo["resultados"]] == [EDICAO_COMPLETA]
    assert corpo["omissoes"] == []
