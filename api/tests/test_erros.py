"""Testes unitarios da taxonomia de erros (``radar_api.erros``).

Cobrem o contrato de erros legivel por maquina:

* Formato do ``EnvelopeErro`` (codigo / mensagem / detalhes) para cada erro
  concreto, incluindo as chaves de ``detalhes`` esperadas (Req 1.8, 2.2, 5.4).
* Mapeamento codigo -> status HTTP para todos os codigos do contrato, verificado
  via ``STATUS_POR_CODIGO``, ``status_para_codigo`` e o ``status_http`` de cada
  instancia de excecao.
* Fallback de codigo desconhecido -> 500.
* Sobrescrita de mensagem (override de ``mensagem_padrao``) e independencia
  (copia) de ``detalhes`` no envelope.
"""

from __future__ import annotations

import pytest

from radar_api.erros import (
    STATUS_POR_CODIGO,
    EnvelopeErro,
    ErroAreaInvalida,
    ErroCapacidadeIndeterminada,
    ErroComparacaoSemEdicoesElegiveis,
    ErroEdicaoAusente,
    ErroEdicaoSemNotas,
    ErroManifestoAusente,
    ErroManifestoInvalido,
    ErroMLDesabilitado,
    ErroMLIndisponivel,
    ErroNotaForaIntervalo,
    ErroPerfilNotaNaoCombinavel,
    ErroRadar,
    ErroRecorteIndisponivel,
    status_para_codigo,
)

# Tabela de contrato: codigo -> status HTTP (design, secao taxonomia de erros).
CONTRATO_STATUS: dict[str, int] = {
    "NOTA_FORA_INTERVALO": 422,
    "AREA_INVALIDA": 422,
    "RECORTE_INDISPONIVEL": 409,
    "EDICAO_SEM_NOTAS": 409,
    "PERFIL_NOTA_NAO_COMBINAVEL": 409,
    "COMPARACAO_SEM_EDICOES_ELEGIVEIS": 409,
    "EDICAO_AUSENTE": 404,
    "MANIFESTO_AUSENTE": 404,
    "MANIFESTO_INVALIDO": 409,
    "CAPACIDADE_INDETERMINADA": 409,
    # Modelo_ML opcional (task 11.1): capacidade nao oferecida, nao falha
    # operacional -> mesma familia 409 de RECORTE_INDISPONIVEL.
    "ML_DESABILITADO": 409,
    "ML_INDISPONIVEL": 409,
}

# Chaves de detalhes esperadas para cada instancia construida em _instancias().
DETALHES_ESPERADOS: dict[str, set[str]] = {
    "NOTA_FORA_INTERVALO": {"minimo", "maximo", "nota"},
    "AREA_INVALIDA": {"areas_validas", "area"},
    "RECORTE_INDISPONIVEL": {"dimensao", "edicao", "edicoes_que_suportam"},
    "EDICAO_SEM_NOTAS": {"edicao"},
    "PERFIL_NOTA_NAO_COMBINAVEL": {"edicao", "dimensao"},
    "COMPARACAO_SEM_EDICOES_ELEGIVEIS": {"edicoes"},
    "EDICAO_AUSENTE": {"edicao"},
    "MANIFESTO_AUSENTE": {"edicao"},
    "MANIFESTO_INVALIDO": {"edicao"},
    "CAPACIDADE_INDETERMINADA": {"edicao"},
    "ML_DESABILITADO": {"ml_habilitado"},
    "ML_INDISPONIVEL": {"motivo", "artefato"},
}


def _instancias() -> dict[str, ErroRadar]:
    """Constroi uma instancia representativa de cada erro concreto do contrato.

    Cada chamada retorna instancias novas, evitando estado compartilhado entre
    testes que mutam ``detalhes``.
    """
    return {
        "NOTA_FORA_INTERVALO": ErroNotaForaIntervalo(nota=1200),
        "AREA_INVALIDA": ErroAreaInvalida(area="xyz"),
        "RECORTE_INDISPONIVEL": ErroRecorteIndisponivel("regiao", 2024, [2023, 2025]),
        "EDICAO_SEM_NOTAS": ErroEdicaoSemNotas(2025),
        "PERFIL_NOTA_NAO_COMBINAVEL": ErroPerfilNotaNaoCombinavel(2024, dimensao="cor_raca"),
        "COMPARACAO_SEM_EDICOES_ELEGIVEIS": ErroComparacaoSemEdicoesElegiveis([2023, 2024]),
        "EDICAO_AUSENTE": ErroEdicaoAusente(2099),
        "MANIFESTO_AUSENTE": ErroManifestoAusente(2023),
        "MANIFESTO_INVALIDO": ErroManifestoInvalido(2023),
        "CAPACIDADE_INDETERMINADA": ErroCapacidadeIndeterminada(2024),
        "ML_DESABILITADO": ErroMLDesabilitado(),
        "ML_INDISPONIVEL": ErroMLIndisponivel("artefato_inexistente", artefato="/tmp/modelo.pkl"),
    }


def test_tabelas_de_teste_cobrem_todos_os_codigos() -> None:
    """Sanidade: as tabelas de apoio cobrem exatamente os codigos do contrato."""
    assert set(CONTRATO_STATUS) == set(DETALHES_ESPERADOS) == set(_instancias())
    assert len(CONTRATO_STATUS) == 12


# --- 1. Formato do envelope -------------------------------------------------


@pytest.mark.parametrize("codigo", sorted(CONTRATO_STATUS))
def test_envelope_tem_codigo_mensagem_e_detalhes(codigo: str) -> None:
    """``.envelope()`` produz um EnvelopeErro com codigo exato, mensagem nao
    vazia e as chaves de detalhes esperadas (Req 1.8, 2.2, 5.4)."""
    erro = _instancias()[codigo]
    env = erro.envelope()

    assert isinstance(env, EnvelopeErro)
    assert env.codigo == codigo
    assert isinstance(env.mensagem, str)
    assert env.mensagem.strip() != ""
    assert set(env.detalhes) == DETALHES_ESPERADOS[codigo]


def test_recorte_indisponivel_carrega_edicoes_que_suportam() -> None:
    """RECORTE_INDISPONIVEL leva dimensao, edicao e a lista edicoes_que_suportam
    em detalhes, orientando o cliente (Req 2.2/2.6)."""
    env = ErroRecorteIndisponivel("regiao", 2024, [2023, 2025]).envelope()

    assert env.codigo == "RECORTE_INDISPONIVEL"
    assert env.detalhes["dimensao"] == "regiao"
    assert env.detalhes["edicao"] == 2024
    assert isinstance(env.detalhes["edicoes_que_suportam"], list)
    assert env.detalhes["edicoes_que_suportam"] == [2023, 2025]


def test_edicao_ausente_carrega_edicao() -> None:
    """EDICAO_AUSENTE leva a edicao alvo em detalhes (Req 5.4)."""
    env = ErroEdicaoAusente(2099).envelope()

    assert env.codigo == "EDICAO_AUSENTE"
    assert env.detalhes["edicao"] == 2099


# --- 2. Mapeamento codigo -> status HTTP ------------------------------------


@pytest.mark.parametrize(("codigo", "status"), sorted(CONTRATO_STATUS.items()))
def test_status_por_codigo_dict(codigo: str, status: int) -> None:
    """STATUS_POR_CODIGO reflete a tabela de contrato para cada codigo."""
    assert STATUS_POR_CODIGO[codigo] == status


@pytest.mark.parametrize(("codigo", "status"), sorted(CONTRATO_STATUS.items()))
def test_status_para_codigo_funcao(codigo: str, status: int) -> None:
    """status_para_codigo() reflete a tabela de contrato para cada codigo."""
    assert status_para_codigo(codigo) == status


@pytest.mark.parametrize(("codigo", "status"), sorted(CONTRATO_STATUS.items()))
def test_status_http_da_instancia(codigo: str, status: int) -> None:
    """O status_http de cada instancia coincide com o contrato e com o dict."""
    erro = _instancias()[codigo]
    assert erro.status_http == status
    assert erro.status_http == STATUS_POR_CODIGO[erro.codigo]


def test_status_por_codigo_cobre_exatamente_o_contrato() -> None:
    """O mapeamento exposto coincide, sem sobra nem falta, com o contrato."""
    assert STATUS_POR_CODIGO == CONTRATO_STATUS


# --- 3. Codigo desconhecido -> 500 ------------------------------------------


def test_status_para_codigo_desconhecido_e_500() -> None:
    """Codigo fora do contrato mapeia para 500 (erro interno inesperado)."""
    assert "CODIGO_DESCONHECIDO" not in STATUS_POR_CODIGO
    assert status_para_codigo("CODIGO_DESCONHECIDO") == 500


# --- 4. Sobrescrita de mensagem e copia de detalhes -------------------------


def test_mensagem_customizada_sobrescreve_padrao() -> None:
    """Passar ``mensagem`` sobrescreve a ``mensagem_padrao`` da subclasse."""
    padrao = ErroAreaInvalida()
    assert padrao.mensagem == ErroAreaInvalida.mensagem_padrao

    custom = ErroAreaInvalida(area="xyz", mensagem="Area 'xyz' desconhecida.")
    assert custom.mensagem == "Area 'xyz' desconhecida."
    assert custom.mensagem != ErroAreaInvalida.mensagem_padrao
    assert custom.envelope().mensagem == "Area 'xyz' desconhecida."


def test_envelope_detalhes_e_copia_independente() -> None:
    """Mutar ``envelope().detalhes`` nao deve afetar o ``detalhes`` da excecao."""
    erro = ErroRecorteIndisponivel("regiao", 2024, [2023, 2025])
    env = erro.envelope()

    env.detalhes["dimensao"] = "adulterado"
    env.detalhes["novo"] = 123

    assert erro.detalhes["dimensao"] == "regiao"
    assert "novo" not in erro.detalhes
