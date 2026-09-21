"""Testes unitarios do catalogo (``radar_api.catalogo``) — task 3.4.

Testes *exemplo* (pytest puro, sem hypothesis) que exercitam o
:class:`~radar_api.catalogo.Catalogo` como um contrato de entrada externo (AD-3
e secao de Riscos do design): descoberta de Edicoes, degradacao graciosa de
linhagem quando o Manifesto/ETL estao ausentes e derivacao de Capacidade.

Cobertura:

* **Descoberta** (Req 5.2): ``edicoes_disponiveis()`` varre ``silver_root`` por
  ``ano=<inteiro>``, retorna em ordem crescente, ignora diretorios/arquivos que
  nao sejam particoes de Edicao e devolve ``[]`` quando a raiz nao existe.
* **Edicao ausente** (Req 5.4): ``info_edicao``/``capacidade`` de uma Edicao
  inexistente levantam :class:`~radar_api.erros.ErroEdicaoAusente`
  (codigo ``EDICAO_AUSENTE``).
* **Manifesto ausente** (Req 5): sem ``radar_etl`` importavel, ``manifesto()``
  degrada para :class:`~radar_api.erros.ErroManifestoAusente` e ``info_edicao``
  descreve a Edicao com linhagem nula (``manifesto_id``/``data_carga`` = None).
* **Manifesto malformado**: com ``radar_etl`` ausente em runtime, um manifesto
  invalido surge como ``MANIFESTO_AUSENTE`` (o import tardio falha antes da
  leitura); o caminho ``MANIFESTO_INVALIDO`` e exercitado na integracao, quando
  ``radar_etl`` esta presente.
* **``edicoes_que_suportam``** (Req 2.6) e **derivacao esperada** de Capacidade
  para 2023/2024/2025 contra a *silver* real do repositorio (pulados quando a
  *silver* real nao esta disponivel no ambiente).

As fixtures de descoberta/manifesto usam uma *silver* temporaria isolada,
construida com Parquet minimos escritos via DuckDB.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.erros import (
    ErroEdicaoAusente,
    ErroManifestoAusente,
    ErroManifestoInvalido,
)
from radar_api.modelos import Dimensao

# --------------------------------------------------------------------------- #
# Silver real do repositorio (para os testes de capacidade orientados a dados) #
# api/tests/test_catalogo.py -> parents[2] == raiz do repositorio.            #
# --------------------------------------------------------------------------- #
_SILVER_REAL = Path(__file__).resolve().parents[2] / "data" / "silver"

_requer_silver_real = pytest.mark.skipif(
    not _SILVER_REAL.is_dir(),
    reason=f"silver real ausente em {_SILVER_REAL}; teste orientado a dados pulado",
)

# Tabela de Capacidade VERIFICADA das Edicoes reais (restricao de
# desidentificacao do INEP — Req 2.1): dimensoes suportadas, presenca de notas e
# combinabilidade perfil+notas por Edicao.
# 2020 a 2023 publicam o arquivo unico que liga nota e perfil na mesma linha, e
# por isso sustentam as dez dimensoes. 2024 separou o questionario em um arquivo
# de chave propria (ADR-0004) e perdeu o perfil, mas e a unica que traz
# ``codigo_escola`` — o INEP retirou o identificador de instituicao dos
# microdados e so o republicou nessa edicao. 2025 ainda nao teve resultados
# publicados, entao nao tem notas nem atributo de escola.
_CAPACIDADES_ESPERADAS: dict[int, dict[str, object]] = {
    2020: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.TIPO_ESCOLA,
            Dimensao.DEP_ADM,
            Dimensao.LOCALIZACAO_ESCOLA,
            Dimensao.RENDA,
            Dimensao.COR_RACA,
            Dimensao.ESCOLARIDADE_PAI,
            Dimensao.ESCOLARIDADE_MAE,
        },
        "possui_notas": True,
        "perfil_combinavel_com_notas": True,
    },
    2021: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.TIPO_ESCOLA,
            Dimensao.DEP_ADM,
            Dimensao.LOCALIZACAO_ESCOLA,
            Dimensao.RENDA,
            Dimensao.COR_RACA,
            Dimensao.ESCOLARIDADE_PAI,
            Dimensao.ESCOLARIDADE_MAE,
        },
        "possui_notas": True,
        "perfil_combinavel_com_notas": True,
    },
    2022: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.TIPO_ESCOLA,
            Dimensao.DEP_ADM,
            Dimensao.LOCALIZACAO_ESCOLA,
            Dimensao.RENDA,
            Dimensao.COR_RACA,
            Dimensao.ESCOLARIDADE_PAI,
            Dimensao.ESCOLARIDADE_MAE,
        },
        "possui_notas": True,
        "perfil_combinavel_com_notas": True,
    },
    2023: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.TIPO_ESCOLA,
            Dimensao.DEP_ADM,
            Dimensao.LOCALIZACAO_ESCOLA,
            Dimensao.RENDA,
            Dimensao.COR_RACA,
            Dimensao.ESCOLARIDADE_PAI,
            Dimensao.ESCOLARIDADE_MAE,
        },
        "possui_notas": True,
        "perfil_combinavel_com_notas": True,
    },
    2024: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.DEP_ADM,
            Dimensao.LOCALIZACAO_ESCOLA,
            Dimensao.CODIGO_ESCOLA,
        },
        "possui_notas": True,
        "perfil_combinavel_com_notas": False,
    },
    2025: {
        "dims": {
            Dimensao.REGIAO,
            Dimensao.UF,
            Dimensao.MUNICIPIO,
            Dimensao.RENDA,
            Dimensao.COR_RACA,
            Dimensao.ESCOLARIDADE_PAI,
            Dimensao.ESCOLARIDADE_MAE,
        },
        "possui_notas": False,
        "perfil_combinavel_com_notas": False,
    },
}


# --------------------------------------------------------------------------- #
# Auxiliares                                                                  #
# --------------------------------------------------------------------------- #
def _radar_etl_importavel() -> bool:
    """Indica se o pacote externo ``radar_etl`` esta importavel em runtime."""
    try:
        return importlib.util.find_spec("radar_etl") is not None
    except (ImportError, ValueError):
        return False


def _escrever_particao(silver_root: Path, ano: int, uf: str) -> Path:
    """Escreve um Parquet minimo em ``ano=<ano>/uf_prova=<uf>/dados_0.parquet``.

    Usa DuckDB (dependencia dura da API) para materializar um Parquet valido e
    diminuto — uma unica coluna/linha ``marcador`` basta para a descoberta e
    para tornar a particao legivel pela sondagem de dados do catalogo.
    """
    destino = silver_root / f"ano={ano}" / f"uf_prova={uf}" / "dados_0.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    caminho_sql = str(destino).replace("'", "''")
    conexao = duckdb.connect()
    try:
        conexao.execute(f"COPY (SELECT 1 AS marcador) TO '{caminho_sql}' (FORMAT PARQUET)")
    finally:
        conexao.close()
    return destino


def _construir_silver(base: Path, particoes: list[tuple[int, str]]) -> Path:
    """Constroi uma *silver* temporaria com as ``particoes`` (ano, uf) dadas."""
    raiz = base / "silver"
    for ano, uf in particoes:
        _escrever_particao(raiz, ano, uf)
    return raiz


def _catalogo(silver_root: Path) -> Catalogo:
    """Instancia um :class:`Catalogo` sobre ``silver_root`` (manifestos = silver)."""
    return Catalogo(Config(silver_root=silver_root, manifestos_root=silver_root))


# --------------------------------------------------------------------------- #
# 1. Descoberta de edicoes (Req 5.2)                                          #
# --------------------------------------------------------------------------- #
def test_edicoes_disponiveis_retorna_ordenado(tmp_path: Path) -> None:
    """As Edicoes descobertas vem em ordem crescente, independentemente da
    ordem de criacao das particoes (Req 5.2)."""
    raiz = _construir_silver(tmp_path, [(2020, "SP"), (2019, "RJ"), (2018, "MG")])
    catalogo = _catalogo(raiz)

    assert catalogo.edicoes_disponiveis() == [2018, 2019, 2020]


def test_edicoes_disponiveis_ignora_nao_particoes(tmp_path: Path) -> None:
    """Diretorios que nao sao ``ano=<inteiro>`` e arquivos soltos sao ignorados
    na descoberta (Req 5.2)."""
    raiz = _construir_silver(tmp_path, [(2019, "RJ"), (2020, "SP")])
    (raiz / "outra_coisa").mkdir()  # nao comeca com "ano="
    (raiz / "ano=rascunho").mkdir()  # comeca com "ano=" mas sufixo nao-inteiro
    (raiz / "_manifests").mkdir()  # pasta irma de manifestos
    (raiz / "leiame.txt").write_text("x", encoding="utf-8")  # arquivo solto

    catalogo = _catalogo(raiz)

    assert catalogo.edicoes_disponiveis() == [2019, 2020]


def test_edicoes_disponiveis_raiz_inexistente_retorna_vazio(tmp_path: Path) -> None:
    """Raiz *silver* inexistente degrada para lista vazia, sem erro (Req 5.2)."""
    catalogo = _catalogo(tmp_path / "silver_inexistente")

    assert catalogo.edicoes_disponiveis() == []


# --------------------------------------------------------------------------- #
# 2. Edicao ausente (Req 5.4)                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("metodo", ["info_edicao", "capacidade"])
def test_edicao_ausente_levanta_erro(tmp_path: Path, metodo: str) -> None:
    """``info_edicao``/``capacidade`` de uma Edicao inexistente levantam
    ``ErroEdicaoAusente`` (codigo ``EDICAO_AUSENTE``), carregando a Edicao alvo
    em ``detalhes`` (Req 5.4)."""
    raiz = _construir_silver(tmp_path, [(2023, "SP")])
    catalogo = _catalogo(raiz)

    with pytest.raises(ErroEdicaoAusente) as exc:
        getattr(catalogo, metodo)(9999)

    assert exc.value.codigo == "EDICAO_AUSENTE"
    assert exc.value.envelope().codigo == "EDICAO_AUSENTE"
    assert exc.value.detalhes["edicao"] == 9999


# --------------------------------------------------------------------------- #
# 3. Manifesto ausente e linhagem graciosa (Req 5)                            #
# --------------------------------------------------------------------------- #
def test_manifesto_ausente_para_edicao_existente(tmp_path: Path) -> None:
    """Edicao existente sem Manifesto (ETL ausente em runtime) -> ``manifesto()``
    degrada para ``ErroManifestoAusente`` (codigo ``MANIFESTO_AUSENTE``)."""
    raiz = _construir_silver(tmp_path, [(2023, "SP")])
    catalogo = _catalogo(raiz)

    with pytest.raises(ErroManifestoAusente) as exc:
        catalogo.manifesto(2023)

    assert exc.value.codigo == "MANIFESTO_AUSENTE"


def test_info_edicao_sem_manifesto_tem_linhagem_nula(tmp_path: Path) -> None:
    """Sem Manifesto, ``info_edicao`` ainda descreve a Edicao, porem com linhagem
    nula: ``manifesto_id`` e ``data_carga`` sao ``None`` (Req 5)."""
    raiz = _construir_silver(tmp_path, [(2023, "SP")])
    catalogo = _catalogo(raiz)

    info = catalogo.info_edicao(2023)

    assert info.edicao == 2023
    assert info.manifesto_id is None
    assert info.data_carga is None


# --------------------------------------------------------------------------- #
# 4. Manifesto malformado (comportamento atual: degrada para ausente)         #
# --------------------------------------------------------------------------- #
def test_manifesto_malformado_degrada_para_ausente_sem_etl(tmp_path: Path) -> None:
    """Manifesto malformado presente na *silver*.

    Comportamento ATUAL do ambiente (``radar_etl`` inimportavel): o import
    tardio de ``radar_etl.manifesto`` falha ANTES de o arquivo malformado ser
    lido, degradando para ``MANIFESTO_AUSENTE``. O caminho ``MANIFESTO_INVALIDO``
    (manifesto presente porem ilegivel) so e alcancavel na integracao, quando
    ``radar_etl`` esta instalado e chega a tentar carregar o arquivo — por isso
    a assercao e condicionada a importabilidade do ETL, mantendo o teste robusto
    em ambos os cenarios.
    """
    raiz = _construir_silver(tmp_path, [(2023, "SP")])
    manifestos = raiz / "_manifests"
    manifestos.mkdir(parents=True, exist_ok=True)
    (manifestos / "enem_2023.json").write_text("{ manifesto: invalido, ", encoding="utf-8")

    catalogo = _catalogo(raiz)

    with pytest.raises((ErroManifestoAusente, ErroManifestoInvalido)) as exc:
        catalogo.manifesto(2023)

    if _radar_etl_importavel():
        assert isinstance(exc.value, ErroManifestoInvalido)
        assert exc.value.codigo == "MANIFESTO_INVALIDO"
    else:
        assert isinstance(exc.value, ErroManifestoAusente)
        assert exc.value.codigo == "MANIFESTO_AUSENTE"


# --------------------------------------------------------------------------- #
# 5. edicoes_que_suportam sobre a silver real (Req 2.6)                        #
# --------------------------------------------------------------------------- #
@_requer_silver_real
@pytest.mark.parametrize(
    ("dims", "esperado"),
    [
        ({Dimensao.REGIAO}, [2020, 2021, 2022, 2023, 2024, 2025]),
        ({Dimensao.MUNICIPIO}, [2020, 2021, 2022, 2023, 2024, 2025]),
        ({Dimensao.RENDA}, [2020, 2021, 2022, 2023, 2025]),
        ({Dimensao.TIPO_ESCOLA}, [2020, 2021, 2022, 2023]),
        ({Dimensao.CODIGO_ESCOLA}, [2024]),
        ({Dimensao.CODIGO_ESCOLA, Dimensao.RENDA}, []),
    ],
)
def test_edicoes_que_suportam_dados_reais(dims: set[Dimensao], esperado: list[int]) -> None:
    """``edicoes_que_suportam`` retorna, em ordem crescente, as Edicoes cuja
    Capacidade contem as dimensoes pedidas (Req 2.6), conforme a tabela
    verificada: regiao e municipio em todas; renda em todas menos 2024; tipo de
    escola nas quatro com arquivo unico; codigo de escola so em 2024.

    O ultimo caso e o que prova a regra: nenhuma Edicao sustenta ao mesmo tempo
    o codigo da escola e a renda, porque quem tem um perdeu o outro."""
    catalogo = Catalogo(Config(silver_root=_SILVER_REAL))

    assert catalogo.edicoes_que_suportam(dims) == esperado


# --------------------------------------------------------------------------- #
# 6. Derivacao esperada de Capacidade 2023/2024/2025 (Req 2.1, dados reais)    #
# --------------------------------------------------------------------------- #
@_requer_silver_real
@pytest.mark.parametrize("edicao", sorted(_CAPACIDADES_ESPERADAS))
def test_capacidade_derivada_dados_reais(edicao: int) -> None:
    """A Capacidade derivada de cada Edicao real coincide com a tabela
    verificada de dimensoes/notas/combinabilidade (restricao de
    desidentificacao — Req 2.1)."""
    catalogo = Catalogo(Config(silver_root=_SILVER_REAL))
    assert edicao in catalogo.edicoes_disponiveis()

    esperado = _CAPACIDADES_ESPERADAS[edicao]
    capac = catalogo.capacidade(edicao)

    assert capac.edicao == edicao
    assert capac.dimensoes_suportadas == esperado["dims"]
    assert capac.possui_notas == esperado["possui_notas"]
    assert capac.perfil_combinavel_com_notas == esperado["perfil_combinavel_com_notas"]
