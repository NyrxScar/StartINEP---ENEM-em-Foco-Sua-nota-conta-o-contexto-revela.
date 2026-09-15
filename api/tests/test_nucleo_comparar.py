"""Testes unitarios da comparacao entre Edicoes (``radar_api.nucleo.comparar``)
e da guarda de capacidade reutilizavel (``verificar_capacidade_recorte``) — task 8.1.

Testes *exemplo* (pytest puro, sem hypothesis) sobre *fixtures* Parquet
minusculas escritas por :mod:`fixtures_silver` no mesmo layout Hive da *silver*
real. A propriedade P11 (task 8.3) e coberta separadamente com hypothesis.

Como ``radar_etl`` nao esta importavel em runtime, a Capacidade e derivada *dos
dados* pelo :class:`~radar_api.catalogo.Catalogo`: uma Dimensao e suportada sse
sua coluna existe e tem ao menos um valor nao nulo; ``possui_notas`` sse alguma
``nota_*`` tem valor nao nulo. As fixtures exploram isso para montar Edicoes com
capacidades distintas (com/sem notas; com/sem uma dimensao).

Cobre :func:`~radar_api.nucleo.comparar` (Req 3.1-3.4):

* duas Edicoes elegiveis -> 2 resultados rotulados por Edicao, sem omissoes;
* uma elegivel + uma com dimensao de recorte indisponivel -> 1 resultado + 1
  omissao com ``RECORTE_INDISPONIVEL``;
* Edicao sem notas -> omitida com ``EDICAO_SEM_NOTAS``;
* Edicao inexistente -> omitida com ``EDICAO_AUSENTE``;
* nenhuma Edicao elegivel -> ``ErroComparacaoSemEdicoesElegiveis``.

E :func:`~radar_api.nucleo.verificar_capacidade_recorte` (Req 2.2/2.3/2.4), um
ramo por vez: sem notas, perfil nao combinavel, recorte indisponivel e o caso
permitido (retorna ``None``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures_silver import escrever_silver, escrever_silver_fixture
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.erros import (
    ErroComparacaoSemEdicoesElegiveis,
    ErroEdicaoSemNotas,
    ErroPerfilNotaNaoCombinavel,
    ErroRecorteIndisponivel,
)
from radar_api.modelos import Area, Capacidade, Dimensao, Recorte, ResultadoComparacao
from radar_api.nucleo import comparar, verificar_capacidade_recorte


def _catalogo(raiz: Path, *, limiar: int = 1) -> Catalogo:
    """Monta um :class:`Catalogo` sobre uma *silver* de teste em ``raiz``.

    ``limiar_agregacao`` e baixo por padrao (1) para que amostras pequenas de
    fixture nao sejam suprimidas — o foco destes testes e a elegibilidade da
    comparacao, nao a guarda de privacidade (coberta em ``test_nucleo``).
    """
    return Catalogo(Config(silver_root=raiz, limiar_agregacao=limiar))


# --------------------------------------------------------------------------- #
# comparar: duas Edicoes elegiveis -> 2 resultados rotulados, sem omissoes     #
# --------------------------------------------------------------------------- #
def test_comparar_duas_edicoes_elegiveis(tmp_path: Path) -> None:
    """Duas Edicoes com notas e Recorte vazio -> ambas elegiveis (Req 3.1/3.4).

    Passa as Edicoes fora de ordem e com duplicata para exercer a deduplicacao
    e a emissao em ordem crescente (determinismo).
    """
    escrever_silver_fixture(
        tmp_path,
        {
            (2023, "SP"): [{"nota_cn": float(400 + i)} for i in range(5)],
            (2024, "SP"): [{"nota_cn": float(500 + i)} for i in range(5)],
        },
    )
    catalogo = _catalogo(tmp_path)

    resultado = comparar(catalogo, [2024, 2023, 2024], Area.CN, 450.0, Recorte())

    assert isinstance(resultado, ResultadoComparacao)
    # Rotulada por Edicao (Req 3.4), deduplicada e em ordem crescente.
    assert [r.edicao for r in resultado.resultados] == [2023, 2024]
    assert resultado.omissoes == []
    for r in resultado.resultados:
        assert r.estatisticamente_insuficiente is False
        assert r.tamanho_amostral == 5
        assert r.percentil is not None


# --------------------------------------------------------------------------- #
# comparar: uma elegivel + uma com dimensao indisponivel -> omissao com motivo #
# --------------------------------------------------------------------------- #
def test_comparar_omite_edicao_com_recorte_indisponivel(tmp_path: Path) -> None:
    """Edicao que nao suporta a dimensao do Recorte e omitida (Req 3.2).

    2023 tem ``tipo_escola`` preenchido (suporta a dimensao); 2024 tem
    ``tipo_escola`` sempre NULL (nao suporta). Ambas tem notas.
    """
    escrever_silver_fixture(
        tmp_path,
        {
            (2023, "SP"): [{"nota_cn": float(400 + i), "tipo_escola": 1} for i in range(5)],
            (2024, "SP"): [{"nota_cn": float(500 + i)} for i in range(5)],
        },
    )
    catalogo = _catalogo(tmp_path)
    recorte = Recorte(filtros={Dimensao.TIPO_ESCOLA: "1"})

    resultado = comparar(catalogo, [2023, 2024], Area.CN, 450.0, recorte)

    assert [r.edicao for r in resultado.resultados] == [2023]
    assert len(resultado.omissoes) == 1
    assert resultado.omissoes[0].edicao == 2024
    assert resultado.omissoes[0].codigo == "RECORTE_INDISPONIVEL"


# --------------------------------------------------------------------------- #
# comparar: Edicao sem notas -> omitida com EDICAO_SEM_NOTAS                    #
# --------------------------------------------------------------------------- #
def test_comparar_omite_edicao_sem_notas(tmp_path: Path) -> None:
    """Edicao cujas ``nota_*`` sao todas NULL e omitida com ``EDICAO_SEM_NOTAS``.

    2025 e escrita apenas com perfil (``renda_familiar``) e nenhuma nota (como a
    Edicao 2025 real, desidentificada e sem notas — Req 2.3).
    """
    escrever_silver_fixture(
        tmp_path,
        {
            (2023, "SP"): [{"nota_cn": float(400 + i)} for i in range(5)],
            (2025, "SP"): [{"renda_familiar": "C"} for _ in range(5)],
        },
    )
    catalogo = _catalogo(tmp_path)

    resultado = comparar(catalogo, [2023, 2025], Area.CN, 450.0, Recorte())

    assert [r.edicao for r in resultado.resultados] == [2023]
    assert len(resultado.omissoes) == 1
    assert resultado.omissoes[0].edicao == 2025
    assert resultado.omissoes[0].codigo == "EDICAO_SEM_NOTAS"


# --------------------------------------------------------------------------- #
# comparar: Edicao inexistente -> omitida com EDICAO_AUSENTE                    #
# --------------------------------------------------------------------------- #
def test_comparar_omite_edicao_inexistente(tmp_path: Path) -> None:
    """Edicao ausente na *silver* e omitida com ``EDICAO_AUSENTE`` (Req 3.2)."""
    escrever_silver(tmp_path, 2023, [{"nota_cn": float(400 + i)} for i in range(5)])
    catalogo = _catalogo(tmp_path)

    resultado = comparar(catalogo, [2023, 2099], Area.CN, 450.0, Recorte())

    assert [r.edicao for r in resultado.resultados] == [2023]
    assert len(resultado.omissoes) == 1
    assert resultado.omissoes[0].edicao == 2099
    assert resultado.omissoes[0].codigo == "EDICAO_AUSENTE"


# --------------------------------------------------------------------------- #
# comparar: nenhuma Edicao elegivel -> ErroComparacaoSemEdicoesElegiveis        #
# --------------------------------------------------------------------------- #
def test_comparar_sem_edicoes_elegiveis_levanta_erro(tmp_path: Path) -> None:
    """Nenhuma Edicao elegivel (uma sem notas, outra inexistente) -> erro (Req 3.3)."""
    escrever_silver_fixture(
        tmp_path,
        {(2025, "SP"): [{"renda_familiar": "C"} for _ in range(5)]},
    )
    catalogo = _catalogo(tmp_path)

    with pytest.raises(ErroComparacaoSemEdicoesElegiveis) as exc:
        comparar(catalogo, [2025, 2099], Area.CN, 450.0, Recorte())

    assert exc.value.codigo == "COMPARACAO_SEM_EDICOES_ELEGIVEIS"
    # As Edicoes solicitadas acompanham o erro para diagnostico (Req 3.3).
    assert exc.value.detalhes["edicoes"] == [2025, 2099]


# --------------------------------------------------------------------------- #
# verificar_capacidade_recorte: um ramo por vez                                #
# --------------------------------------------------------------------------- #
def test_verificar_sem_notas_levanta_edicao_sem_notas(tmp_path: Path) -> None:
    """Capacidade sem notas -> ``ErroEdicaoSemNotas`` (Req 2.3), antes do recorte."""
    catalogo = _catalogo(tmp_path)  # nao consultado neste ramo
    capacidade = Capacidade(
        edicao=2025,
        dimensoes_suportadas={Dimensao.REGIAO, Dimensao.RENDA},
        possui_notas=False,
        perfil_combinavel_com_notas=False,
    )

    with pytest.raises(ErroEdicaoSemNotas) as exc:
        verificar_capacidade_recorte(catalogo, 2025, capacidade, Recorte())

    assert exc.value.codigo == "EDICAO_SEM_NOTAS"
    assert exc.value.detalhes["edicao"] == 2025


def test_verificar_perfil_nao_combinavel_precede_recorte_indisponivel(tmp_path: Path) -> None:
    """Dimensao de perfil em Edicao com notas nao combinaveis -> ``PERFIL_NOTA_NAO_COMBINAVEL``.

    ``renda_familiar`` e simultaneamente uma dimensao de perfil E ausente das
    dimensoes suportadas de 2024; a guarda reporta o motivo *especifico* (perfil
    nao combinavel) antes do generico ``RECORTE_INDISPONIVEL`` (Req 2.4).
    """
    catalogo = _catalogo(tmp_path)  # nao consultado neste ramo
    capacidade = Capacidade(
        edicao=2024,
        dimensoes_suportadas={Dimensao.REGIAO, Dimensao.UF, Dimensao.DEP_ADM},
        possui_notas=True,
        perfil_combinavel_com_notas=False,
    )
    recorte = Recorte(filtros={Dimensao.RENDA: "C"})

    with pytest.raises(ErroPerfilNotaNaoCombinavel) as exc:
        verificar_capacidade_recorte(catalogo, 2024, capacidade, recorte)

    assert exc.value.codigo == "PERFIL_NOTA_NAO_COMBINAVEL"
    assert exc.value.detalhes["edicao"] == 2024
    assert exc.value.detalhes["dimensao"] == "renda_familiar"


def test_verificar_recorte_indisponivel_lista_edicoes_que_suportam(tmp_path: Path) -> None:
    """Dimensao (nao-perfil) fora da Capacidade -> ``RECORTE_INDISPONIVEL`` + edicoes (Req 2.2/2.6).

    A ``tipo_escola`` nao e dimensao de perfil, entao cai no ramo generico. O
    catalogo (com 2023 suportando ``tipo_escola``) fornece ``edicoes_que_suportam``.
    """
    escrever_silver(tmp_path, 2023, [{"nota_cn": 500.0, "tipo_escola": 1}])
    catalogo = _catalogo(tmp_path)
    capacidade = Capacidade(
        edicao=2024,
        dimensoes_suportadas={Dimensao.REGIAO, Dimensao.UF, Dimensao.DEP_ADM},
        possui_notas=True,
        perfil_combinavel_com_notas=False,
    )
    recorte = Recorte(filtros={Dimensao.TIPO_ESCOLA: "1"})

    with pytest.raises(ErroRecorteIndisponivel) as exc:
        verificar_capacidade_recorte(catalogo, 2024, capacidade, recorte)

    assert exc.value.codigo == "RECORTE_INDISPONIVEL"
    assert exc.value.detalhes["dimensao"] == "tipo_escola"
    assert exc.value.detalhes["edicao"] == 2024
    assert exc.value.detalhes["edicoes_que_suportam"] == [2023]


def test_verificar_permitido_retorna_none(tmp_path: Path) -> None:
    """Edicao com notas, perfil combinavel e todas as dimensoes -> permitido (``None``)."""
    catalogo = _catalogo(tmp_path)  # nao consultado quando permitido
    capacidade = Capacidade(
        edicao=2023,
        dimensoes_suportadas=set(Dimensao),
        possui_notas=True,
        perfil_combinavel_com_notas=True,
    )
    recorte = Recorte(filtros={Dimensao.RENDA: "C", Dimensao.TIPO_ESCOLA: "1"})

    assert verificar_capacidade_recorte(catalogo, 2023, capacidade, recorte) is None
