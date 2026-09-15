"""Testes unitarios dos modelos de dados pydantic (``radar_api.modelos``)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from radar_api.modelos import (
    Area,
    Dimensao,
    Recorte,
    RequisicaoAnalise,
)


@pytest.mark.parametrize("nota_valida", [0, 0.0, 500, 1000, 1000.0])
def test_nota_dentro_do_intervalo_e_aceita(nota_valida: float) -> None:
    """Notas em 0..1000 inclusive (bordas incluidas) devem ser aceitas (Req 1.8)."""
    req = RequisicaoAnalise(edicao=2023, area="cn", nota=nota_valida)
    assert req.nota == nota_valida


@pytest.mark.parametrize("nota_invalida", [-1, -0.01, 1000.01, 1001, 1500])
def test_nota_fora_do_intervalo_e_rejeitada(nota_invalida: float) -> None:
    """Notas fora de 0..1000 devem produzir ValidationError (Req 1.8)."""
    with pytest.raises(ValidationError):
        RequisicaoAnalise(edicao=2023, area="cn", nota=nota_invalida)


def test_recorte_default_e_independente_por_instancia() -> None:
    """O default de ``filtros`` nao deve ser compartilhado entre instancias.

    Garante que o default mutavel usa ``default_factory`` (uma nova dict por
    instancia) e nao um unico objeto compartilhado.
    """
    r1 = Recorte()
    r2 = Recorte()
    assert r1.filtros == {}
    assert r2.filtros == {}
    assert r1.filtros is not r2.filtros

    r1.filtros[Dimensao.REGIAO] = "Sudeste"
    assert r2.filtros == {}  # mutacao em r1 nao vaza para r2


def test_requisicao_recorte_default_e_independente_por_instancia() -> None:
    """O ``recorte`` default de ``RequisicaoAnalise`` tambem deve ser isolado."""
    a = RequisicaoAnalise(edicao=2023, area=Area.MT, nota=600)
    b = RequisicaoAnalise(edicao=2023, area=Area.MT, nota=600)
    assert a.recorte.filtros == {}
    assert a.recorte is not b.recorte

    a.recorte.filtros[Dimensao.UF] = "SP"
    assert b.recorte.filtros == {}


def test_dimensao_renda_mapeia_para_coluna_canonica() -> None:
    """O valor da dimensao de renda deve ser a coluna silver ``renda_familiar``."""
    assert Dimensao.RENDA.value == "renda_familiar"


def test_valores_das_dimensoes_sao_colunas_silver() -> None:
    """Os valores dos membros de ``Dimensao`` sao os nomes das colunas canonicas."""
    assert Dimensao.ESCOLARIDADE_PAI.value == "escolaridade_pai"
    assert Dimensao.ESCOLARIDADE_MAE.value == "escolaridade_mae"
    assert Dimensao.UF.value == "uf_prova"
    assert Dimensao.DEP_ADM.value == "dependencia_adm_escola"
