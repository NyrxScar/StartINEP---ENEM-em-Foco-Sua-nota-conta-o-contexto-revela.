"""Testes unitarios do Modelo_ML opcional (``radar_api.ml``).

Cobre o contrato da task 11.1: *gating* por ``config.ml_habilitado``,
carregamento *lazy* e memoizado, falhas sempre categorizadas na taxonomia de
erros e saida rotulada como modelo/2023 (Req 8.1, 8.3, 8.4).

Cobre:

* (a) config padrao (ML desabilitado) -> ``ML_DESABILITADO`` e **nada** e
  carregado (o carregador injetado nunca e chamado; cache permanece vazio);
* (b) habilitado sem ``ml_artefato`` -> ``ML_INDISPONIVEL``/``artefato_nao_configurado``;
* (c) habilitado com caminho inexistente -> ``ML_INDISPONIVEL``/``artefato_inexistente``;
* (d) os codigos mapeiam para 409 via ``STATUS_POR_CODIGO``/``status_para_codigo``;
* (e) importar ``radar_api.ml`` nao tem efeito colateral (subprocesso limpo:
  nenhuma biblioteca de ML importada, nenhum acesso a artefato);
* caminho felizardo com o carregador padrao (``pickle`` da stdlib) e prova de que
  o artefato e lido **uma unica vez** (memoizacao);
* dependencia ausente, artefato incompativel e falha na inferencia -> sub-motivos
  categorizados, sem excecao crua escapando.
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

import radar_api.ml as radar_api_ml
from radar_api.config import Config
from radar_api.erros import (
    STATUS_POR_CODIGO,
    ErroMLDesabilitado,
    ErroMLIndisponivel,
    ErroRadar,
    status_para_codigo,
)
from radar_api.ml import (
    EDICAO_ML,
    MOTIVOS,
    EntradaML,
    carregar_modelo,
    inferir,
    limpar_cache,
    ml_disponivel,
    modelos_em_cache,
)
from radar_api.modelos import Area, Dimensao


class ArtefatoFalso:
    """Artefato minimo (e *picklavel*) que satisfaz o protocolo ``prever``.

    Definido no escopo do modulo justamente para poder ser serializado com
    ``pickle`` e assim exercitar o carregador **padrao** de
    :mod:`radar_api.ml` — sem exigir nenhuma biblioteca de ML instalada.
    """

    def __init__(self, base: float = 500.0) -> None:
        self.base = base

    def prever(self, caracteristicas: Mapping[str, str]) -> float:
        """Previsao deterministica: base + 10 por caracteristica informada."""
        return self.base + 10.0 * len(caracteristicas)


class ArtefatoQuePreveErrado:
    """Artefato que falha ao inferir (simula um modelo mal treinado/corrompido)."""

    def prever(self, caracteristicas: Mapping[str, str]) -> float:
        """Levanta erro para exercitar o isolamento da falha do ML."""
        raise RuntimeError("features desconhecidas")


@pytest.fixture(autouse=True)
def _cache_limpo() -> Iterator[None]:
    """Isola o cache de modelos entre testes (memoizacao e global ao modulo)."""
    limpar_cache()
    yield
    limpar_cache()


def _escrever_artefato(caminho: Path, objeto: object) -> Path:
    """Serializa ``objeto`` em ``caminho`` com ``pickle`` (stdlib)."""
    with caminho.open("wb") as arquivo:
        pickle.dump(objeto, arquivo)
    return caminho


def _entrada() -> EntradaML:
    """Entrada de exemplo: area CN com duas caracteristicas de perfil."""
    return EntradaML(
        area=Area.CN,
        perfil={Dimensao.REGIAO: "Sudeste", Dimensao.TIPO_ESCOLA: "publica"},
    )


# --------------------------------------------------------------------------- #
# (a) config padrao: ML desabilitado, nada carregado                          #
# --------------------------------------------------------------------------- #
def test_config_padrao_ml_desabilitado_nao_carrega_nada() -> None:
    """(a) Com o padrao (``ml_habilitado=False``) a inferencia falha sem efeitos."""
    config = Config()
    assert config.ml_habilitado is False
    assert ml_disponivel(config) is False

    def carregador_proibido(caminho: Path) -> object:
        raise AssertionError(f"o carregador nao deveria ser chamado (caminho={caminho})")

    with pytest.raises(ErroMLDesabilitado) as excinfo:
        inferir(config, _entrada(), carregador=carregador_proibido)

    erro = excinfo.value
    assert erro.codigo == "ML_DESABILITADO"
    assert erro.envelope().detalhes["ml_habilitado"] is False
    # Nada foi lido do disco nem memoizado.
    assert modelos_em_cache() == 0


def test_ml_desabilitado_ignora_artefato_existente(tmp_path: Path) -> None:
    """Mesmo com artefato valido no disco, desabilitado nao carrega (Req 8.1)."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoFalso())
    config = Config(ml_habilitado=False, ml_artefato=artefato)

    assert ml_disponivel(config) is False
    with pytest.raises(ErroMLDesabilitado):
        carregar_modelo(config)
    assert modelos_em_cache() == 0


# --------------------------------------------------------------------------- #
# (b) e (c) habilitado, porem inutilizavel                                    #
# --------------------------------------------------------------------------- #
def test_habilitado_sem_artefato_configurado() -> None:
    """(b) ``ml_artefato=None`` -> ``ML_INDISPONIVEL``/``artefato_nao_configurado``."""
    config = Config(ml_habilitado=True, ml_artefato=None)

    assert ml_disponivel(config) is False
    with pytest.raises(ErroMLIndisponivel) as excinfo:
        inferir(config, _entrada())

    envelope = excinfo.value.envelope()
    assert envelope.codigo == "ML_INDISPONIVEL"
    assert envelope.detalhes["motivo"] == "artefato_nao_configurado"
    assert "artefato" not in envelope.detalhes
    assert modelos_em_cache() == 0


def test_habilitado_com_artefato_inexistente(tmp_path: Path) -> None:
    """(c) Caminho inexistente -> ``ML_INDISPONIVEL``/``artefato_inexistente``."""
    ausente = tmp_path / "nao_existe.pkl"
    config = Config(ml_habilitado=True, ml_artefato=ausente)

    assert ml_disponivel(config) is False
    with pytest.raises(ErroMLIndisponivel) as excinfo:
        inferir(config, _entrada())

    envelope = excinfo.value.envelope()
    assert envelope.detalhes["motivo"] == "artefato_inexistente"
    assert envelope.detalhes["artefato"] == str(ausente)
    assert modelos_em_cache() == 0


def test_dependencia_de_ml_ausente_e_categorizada(tmp_path: Path) -> None:
    """``ImportError`` do carregador -> ``dependencia_ausente`` (nao vaza crua)."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoFalso())
    config = Config(ml_habilitado=True, ml_artefato=artefato)

    def carregador_sem_dependencia(caminho: Path) -> object:
        raise ImportError("No module named 'sklearn'")

    with pytest.raises(ErroMLIndisponivel) as excinfo:
        inferir(config, _entrada(), carregador=carregador_sem_dependencia)

    assert excinfo.value.envelope().detalhes["motivo"] == "dependencia_ausente"
    assert modelos_em_cache() == 0


def test_artefato_incompativel_e_categorizado(tmp_path: Path) -> None:
    """Objeto sem ``prever``/``predict`` -> ``artefato_incompativel``."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", {"nao": "sou um modelo"})
    config = Config(ml_habilitado=True, ml_artefato=artefato)

    with pytest.raises(ErroMLIndisponivel) as excinfo:
        inferir(config, _entrada())

    assert excinfo.value.envelope().detalhes["motivo"] == "artefato_incompativel"
    assert modelos_em_cache() == 0


def test_falha_de_inferencia_e_categorizada(tmp_path: Path) -> None:
    """Excecao do artefato durante a previsao -> ``falha_inferencia`` (Req 8.3)."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoQuePreveErrado())
    config = Config(ml_habilitado=True, ml_artefato=artefato)

    with pytest.raises(ErroMLIndisponivel) as excinfo:
        inferir(config, _entrada())

    assert excinfo.value.envelope().detalhes["motivo"] == "falha_inferencia"


def test_motivos_usados_estao_declarados(tmp_path: Path) -> None:
    """Todo sub-motivo emitido pertence ao conjunto documentado ``MOTIVOS``."""
    config = Config(ml_habilitado=True, ml_artefato=None)
    with pytest.raises(ErroMLIndisponivel) as excinfo:
        carregar_modelo(config)
    assert excinfo.value.detalhes["motivo"] in MOTIVOS


# --------------------------------------------------------------------------- #
# (d) mapeamento codigo -> status HTTP                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("erro", "codigo"),
    [
        (ErroMLDesabilitado(), "ML_DESABILITADO"),
        (ErroMLIndisponivel("artefato_nao_configurado"), "ML_INDISPONIVEL"),
    ],
)
def test_codigos_ml_mapeiam_para_409(erro: ErroRadar, codigo: str) -> None:
    """(d) Ambos os codigos do ML sao capacidade nao oferecida -> 409."""
    assert erro.codigo == codigo
    assert erro.status_http == 409
    assert STATUS_POR_CODIGO[codigo] == 409
    assert status_para_codigo(codigo) == 409
    assert isinstance(erro, ErroRadar)


# --------------------------------------------------------------------------- #
# (e) importar radar_api.ml nao tem efeito colateral                          #
# --------------------------------------------------------------------------- #
def test_import_sem_efeito_colateral() -> None:
    """(e) Import limpo: nenhuma biblioteca de ML entra em ``sys.modules``."""
    codigo = (
        "import sys\n"
        "import radar_api.ml as ml\n"
        "raizes = {n.split('.')[0] for n in sys.modules}\n"
        "assert not raizes & {'joblib', 'sklearn', 'numpy', 'pandas', 'duckdb'}, raizes\n"
        "assert ml.modelos_em_cache() == 0\n"
        "from radar_api.config import Config\n"
        "assert ml.ml_disponivel(Config()) is False\n"
        "print('ok')\n"
    )
    # Garante que o subprocesso encontre ``radar_api`` mesmo sem instalacao
    # editavel (o pacote vive em ``api/src``, injetado no pytest via pythonpath).
    raiz_src = Path(radar_api_ml.__file__).resolve().parents[1]
    ambiente = {**os.environ, "PYTHONPATH": str(raiz_src)}
    processo = subprocess.run(  # noqa: S603 — interpretador do proprio venv
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        check=False,
        env=ambiente,
    )
    assert processo.returncode == 0, processo.stderr
    assert processo.stdout.strip() == "ok"


# --------------------------------------------------------------------------- #
# Caminho felizardo + memoizacao                                              #
# --------------------------------------------------------------------------- #
def test_inferencia_rotulada_como_modelo_2023(tmp_path: Path) -> None:
    """Habilitado com artefato valido -> saida rotulada modelo/2023 (Req 8.4)."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoFalso(base=480.0))
    config = Config(ml_habilitado=True, ml_artefato=artefato)

    assert ml_disponivel(config) is True
    saida = inferir(config, _entrada())

    assert saida.origem == "modelo"
    assert saida.edicao == EDICAO_ML == 2023
    assert saida.area is Area.CN
    # ArtefatoFalso: base + 10 por caracteristica (duas no perfil de exemplo).
    assert saida.valor_previsto == pytest.approx(500.0)
    assert saida.modelo_id.startswith("modelo.pkl@")


def test_artefato_carregado_uma_unica_vez(tmp_path: Path) -> None:
    """A memoizacao garante uma leitura do artefato por versao no disco."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoFalso())
    config = Config(ml_habilitado=True, ml_artefato=artefato)
    chamadas: list[Path] = []

    def carregador_contado(caminho: Path) -> object:
        chamadas.append(caminho)
        return ArtefatoFalso(base=100.0)

    primeira = inferir(config, _entrada(), carregador=carregador_contado)
    segunda = inferir(config, _entrada(), carregador=carregador_contado)

    assert len(chamadas) == 1
    assert modelos_em_cache() == 1
    assert primeira.valor_previsto == segunda.valor_previsto == pytest.approx(120.0)
    # O modelo memoizado e o mesmo objeto entre chamadas.
    assert carregar_modelo(config) is carregar_modelo(config)
    assert len(chamadas) == 1


def test_entrada_sem_perfil_e_aceita(tmp_path: Path) -> None:
    """Perfil vazio e uma inferencia valida (nenhuma caracteristica informada)."""
    artefato = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoFalso(base=300.0))
    config = Config(ml_habilitado=True, ml_artefato=artefato)

    saida = inferir(config, EntradaML(area=Area.MT))

    assert saida.valor_previsto == pytest.approx(300.0)
    assert saida.edicao == 2023
