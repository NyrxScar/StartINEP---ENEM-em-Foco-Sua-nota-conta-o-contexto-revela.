"""Testes unitarios (exemplos) do nucleo analitico (``radar_api.nucleo.analisar``).

Sanidade baseada em exemplos, sobre *fixtures* Parquet minusculas escritas por
:mod:`fixtures_silver` no mesmo layout Hive da *silver* real, mais uma chamada
de integracao contra os dados reais em ``data/silver`` (pulada se ausentes). As
propriedades P1/P2/P3 (tasks 5.4/5.5/5.6) sao cobertas separadamente com
hypothesis, reutilizando o mesmo auxiliar de fixtures.

Cobre:

* (a) distribuicao conhecida -> ``tamanho_amostral`` esperado e Percentil em
  ``[0, 100]`` (Req 1.5, 1.7);
* (b) Recorte abaixo do limiar -> ``estatisticamente_insuficiente=True`` com
  ``distribuicao``/``percentil``/``tamanho_amostral`` todos ``None`` (Req 1.6);
* (c) Recorte vazio conta todas as linhas da Edicao com nota nao nula na Area
  (Req 1.2/1.3);
* (d) o resultado embute ``capacidade`` (Req 2.5) e ``linhagem`` com a Edicao
  listada (Req 5.1);
* o caso de **amostra vazia** (``tamanho_amostral == 0``) nao tenta construir
  quantis a partir de ``None``;
* injecao de conexao (``con``) e o valor-padrao de ``limiar`` vindo da config;
* Edicao ausente -> ``ErroEdicaoAusente`` (Req 5.4).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from fixtures_silver import escrever_silver, escrever_silver_fixture
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.erros import ErroEdicaoAusente
from radar_api.modelos import Area, Dimensao, Recorte, ResultadoAnalise
from radar_api.nucleo import analisar

LIMIAR = 25


def _catalogo(raiz: Path, *, limiar: int = LIMIAR) -> Catalogo:
    """Monta um :class:`Catalogo` sobre uma *silver* de teste em ``raiz``.

    O ``limiar_agregacao`` e fixado explicitamente para que a supressao nao
    dependa de variaveis de ambiente ``RADAR_*`` no ambiente de teste.
    """
    return Catalogo(Config(silver_root=raiz, limiar_agregacao=limiar))


# --------------------------------------------------------------------------- #
# (a) distribuicao conhecida -> tamanho amostral e percentil em [0, 100]      #
# --------------------------------------------------------------------------- #
def test_distribuicao_conhecida_tamanho_e_percentil(tmp_path: Path) -> None:
    """(a) Amostra >= limiar produz tamanho amostral exato e Percentil em [0,100]."""
    # 30 notas conhecidas: 0, 25, 50, ..., 725 (todas nao nulas).
    linhas = [{"nota_cn": float(i * 25), "tipo_escola": 1} for i in range(30)]
    escrever_silver(tmp_path, 2023, linhas)
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 375.0, Recorte())

    assert isinstance(resultado, ResultadoAnalise)
    assert resultado.estatisticamente_insuficiente is False
    assert resultado.tamanho_amostral == 30
    assert resultado.percentil is not None
    assert 0.0 <= resultado.percentil <= 100.0
    # Distribuicao presente e coerente: quantis dentro do intervalo das notas.
    assert resultado.distribuicao is not None
    quantis = resultado.distribuicao.quantis
    assert quantis.minimo == 0.0
    assert quantis.maximo == 725.0
    assert quantis.minimo <= quantis.mediana <= quantis.maximo
    assert resultado.distribuicao.faixas  # ao menos uma faixa


def test_percentil_meio_da_distribuicao_uniforme(tmp_path: Path) -> None:
    """Nota mediana de uma distribuicao uniforme cai perto de 50 (rank determinístico)."""
    linhas = [{"nota_mt": float(i * 10)} for i in range(101)]  # 0..1000
    escrever_silver(tmp_path, 2023, linhas)
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.MT, 500.0, Recorte())

    assert resultado.tamanho_amostral == 101
    assert resultado.percentil is not None
    # 50 notas < 500, 1 nota == 500 -> 100*(50 + 0.5)/101 ~= 49.5
    assert 45.0 <= resultado.percentil <= 55.0


# --------------------------------------------------------------------------- #
# (b) Recorte abaixo do limiar -> estatisticamente insuficiente               #
# --------------------------------------------------------------------------- #
def test_recorte_abaixo_do_limiar_e_insuficiente(tmp_path: Path) -> None:
    """(b) Recorte com amostra < limiar -> suprimido, campos sensiveis None (Req 1.6)."""
    # 10 linhas em RJ (< limiar 25) e 30 em SP (para a Edicao existir com dados).
    linhas = [{"nota_cn": float(500 + i), "uf_prova": "RJ"} for i in range(10)]
    linhas += [{"nota_cn": float(i), "uf_prova": "SP"} for i in range(30)]
    escrever_silver(tmp_path, 2023, linhas)
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 505.0, Recorte(filtros={Dimensao.UF: "RJ"}))

    assert resultado.estatisticamente_insuficiente is True
    assert resultado.distribuicao is None
    assert resultado.percentil is None
    assert resultado.tamanho_amostral is None
    # metadados nao sensiveis permanecem presentes
    assert resultado.capacidade.edicao == 2023
    assert 2023 in resultado.linhagem.edicoes


# --------------------------------------------------------------------------- #
# (c) Recorte vazio conta todas as linhas com nota nao nula na Area           #
# --------------------------------------------------------------------------- #
def test_recorte_vazio_conta_apenas_notas_nao_nulas(tmp_path: Path) -> None:
    """(c) Sem Recorte, o tamanho amostral = linhas com nota nao nula na Area (Req 1.2/1.3)."""
    # 28 linhas com nota_cn preenchida (>= limiar) + 5 com nota_cn NULL (ignoradas).
    linhas = [{"nota_cn": float(300 + i * 10)} for i in range(28)]
    linhas += [{"nota_cn": None, "nota_mt": 700.0} for _ in range(5)]
    escrever_silver(tmp_path, 2023, linhas)
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 400.0, Recorte())

    assert resultado.tamanho_amostral == 28  # as 5 linhas com nota_cn NULL nao contam
    assert resultado.estatisticamente_insuficiente is False


def test_recorte_vazio_abrange_todas_as_particoes(tmp_path: Path) -> None:
    """Sem Recorte, a analise abrange todas as UFs (particoes) da Edicao."""
    escrever_silver_fixture(
        tmp_path,
        {
            (2023, "SP"): [{"nota_ch": float(400 + i)} for i in range(20)],
            (2023, "MG"): [{"nota_ch": float(600 + i)} for i in range(20)],
        },
    )
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CH, 500.0, Recorte())

    assert resultado.tamanho_amostral == 40  # 20 SP + 20 MG


# --------------------------------------------------------------------------- #
# (d) o resultado embute capacidade e linhagem                                #
# --------------------------------------------------------------------------- #
def test_resultado_embute_capacidade_e_linhagem(tmp_path: Path) -> None:
    """(d) A resposta carrega a Capacidade (Req 2.5) e a Linhagem da Edicao (Req 5.1)."""
    linhas = [
        {"nota_cn": float(400 + i), "cor_raca": 1, "renda_familiar": "C"} for i in range(30)
    ]
    escrever_silver(tmp_path, 2023, linhas)
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 410.0, Recorte())

    # Capacidade (Req 2.5): a Edicao consultada, com notas presentes.
    assert resultado.capacidade.edicao == 2023
    assert resultado.capacidade.possui_notas is True
    assert resultado.capacidade == catalogo.capacidade(2023)

    # Linhagem (Req 5.1): a Edicao usada esta listada, com chaves de manifesto/data.
    assert resultado.linhagem.edicoes == [2023]
    assert 2023 in resultado.linhagem.manifestos
    assert 2023 in resultado.linhagem.datas_carga
    # Sem ETL/manifesto em runtime, a linhagem e anulavel mas a Edicao consta.
    assert resultado.linhagem.manifestos[2023] is None
    assert resultado.linhagem.datas_carga[2023] is None


# --------------------------------------------------------------------------- #
# Caso de amostra vazia (tamanho_amostral == 0)                               #
# --------------------------------------------------------------------------- #
def test_amostra_vazia_nao_constroi_quantis(tmp_path: Path) -> None:
    """Amostra vazia (0 linhas) -> distribuicao/percentil None sem erro de validacao.

    Usa ``limiar=0`` para observar o resultado *pre-supressao*: tamanho 0,
    distribuicao/percentil ``None`` e ``estatisticamente_insuficiente=False``.
    Confirma que o nucleo nao tenta construir ``Quantis`` a partir de ``None``.
    """
    # Todas as notas da Area sao NULL -> zero linhas apos o filtro de nao nulos.
    escrever_silver(tmp_path, 2023, [{"nota_cn": None, "nota_mt": 500.0} for _ in range(4)])
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 500.0, Recorte(), limiar=0)

    assert resultado.tamanho_amostral == 0
    assert resultado.distribuicao is None
    assert resultado.percentil is None
    assert resultado.estatisticamente_insuficiente is False


def test_amostra_vazia_com_limiar_padrao_e_suprimida(tmp_path: Path) -> None:
    """Amostra vazia sob o limiar padrao -> suprimida (insuficiente), sem erro."""
    escrever_silver(tmp_path, 2023, [{"nota_cn": None} for _ in range(4)])
    catalogo = _catalogo(tmp_path)

    resultado = analisar(catalogo, 2023, Area.CN, 500.0, Recorte())

    assert resultado.estatisticamente_insuficiente is True
    assert resultado.tamanho_amostral is None
    assert resultado.distribuicao is None
    assert resultado.percentil is None


# --------------------------------------------------------------------------- #
# Injecao de dependencia: conexao e limiar                                    #
# --------------------------------------------------------------------------- #
def test_conexao_injetada_e_reutilizada_e_nao_fechada(tmp_path: Path) -> None:
    """Uma conexao fornecida via ``con`` e reutilizada e permanece aberta."""
    escrever_silver(tmp_path, 2023, [{"nota_lc": float(300 + i * 5)} for i in range(30)])
    catalogo = _catalogo(tmp_path)

    conexao = duckdb.connect()
    try:
        resultado = analisar(catalogo, 2023, Area.LC, 350.0, Recorte(), con=conexao)
        assert resultado.tamanho_amostral == 30
        # A conexao continua utilizavel (nao foi fechada pelo nucleo).
        assert conexao.execute("SELECT 1").fetchone() == (1,)
    finally:
        conexao.close()


def test_limiar_explicito_sobrepoe_config(tmp_path: Path) -> None:
    """O ``limiar`` explicito sobrepoe o valor default da config."""
    # 30 linhas: acima do default (25), mas abaixo de um limiar explicito de 50.
    escrever_silver(tmp_path, 2023, [{"nota_cn": float(i * 20)} for i in range(30)])
    catalogo = _catalogo(tmp_path, limiar=25)

    # Com o limiar default (25): resultado presente.
    r_default = analisar(catalogo, 2023, Area.CN, 300.0, Recorte())
    assert r_default.estatisticamente_insuficiente is False
    assert r_default.tamanho_amostral == 30

    # Com limiar explicito 50 (> 30): suprimido.
    r_estrito = analisar(catalogo, 2023, Area.CN, 300.0, Recorte(), limiar=50)
    assert r_estrito.estatisticamente_insuficiente is True
    assert r_estrito.tamanho_amostral is None


# --------------------------------------------------------------------------- #
# Edicao ausente -> ErroEdicaoAusente (Req 5.4)                               #
# --------------------------------------------------------------------------- #
def test_edicao_ausente_propaga_erro(tmp_path: Path) -> None:
    """Analisar uma Edicao inexistente na *silver* propaga ErroEdicaoAusente."""
    escrever_silver(tmp_path, 2023, [{"nota_cn": 500.0}])
    catalogo = _catalogo(tmp_path)

    with pytest.raises(ErroEdicaoAusente):
        analisar(catalogo, 2099, Area.CN, 500.0, Recorte())


# --------------------------------------------------------------------------- #
# Integracao: chamada de sanidade contra a *silver* real                      #
# --------------------------------------------------------------------------- #
_RAIZ_REPO = Path(__file__).resolve().parents[2]
_SILVER_REAL = _RAIZ_REPO / "data" / "silver"


@pytest.mark.skipif(
    not (_SILVER_REAL / "ano=2023").is_dir(),
    reason="silver real (data/silver/ano=2023) ausente neste ambiente",
)
def test_integracao_silver_real_2023_cn_sp() -> None:
    """Sanidade de integracao: 2023/CN/{UF:SP} sobre a *silver* real.

    Confirma que ``analisar`` devolve um resultado populado (amostra grande, bem
    acima do limiar), com Percentil em ``[0, 100]``, Capacidade da Edicao 2023 e
    a Edicao listada na Linhagem.
    """
    catalogo = Catalogo(Config(silver_root=_SILVER_REAL))

    resultado = analisar(catalogo, 2023, Area.CN, 550.0, Recorte(filtros={Dimensao.UF: "SP"}))

    assert resultado.estatisticamente_insuficiente is False
    assert resultado.tamanho_amostral is not None
    assert resultado.tamanho_amostral > 0
    assert resultado.percentil is not None
    assert 0.0 <= resultado.percentil <= 100.0
    assert resultado.distribuicao is not None
    assert resultado.distribuicao.faixas
    assert resultado.capacidade.edicao == 2023
    assert resultado.capacidade.possui_notas is True
    assert 2023 in resultado.linhagem.edicoes
