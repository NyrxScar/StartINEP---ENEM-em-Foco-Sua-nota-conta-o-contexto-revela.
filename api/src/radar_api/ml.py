"""Modelo_ML opcional do Radar ENEM — carregamento *lazy*, *gated* por config.

**Status: secundario.** O produto e a camada estatistica (Distribuicao,
Percentil, comparacao entre Edicoes). O Modelo_ML e um acessorio exploratorio:
o design (AD-5 e a secao ``radar_api.ml``) fixa que o nucleo analitico
(:mod:`radar_api.nucleo`) **nao depende** deste modulo — nenhum caminho do
nucleo o importa — e que toda falha do ML e **isolada aqui**, nunca propagada
para as analises estatisticas (Req 8.2/8.3; Property 12). Se este arquivo fosse
removido, a API estatistica continuaria completa.

Contrato deste modulo:

* **Gating por configuracao** (Req 8.1). Com ``config.ml_habilitado`` em
  ``False`` (o padrao), nada e importado nem lido do disco: :func:`ml_disponivel`
  responde ``False`` e :func:`inferir` levanta :class:`~radar_api.erros.
  ErroMLDesabilitado` antes de qualquer efeito colateral.
* **Carregamento *lazy* e memoizado.** O artefato e a biblioteca de ML (quando
  houver) sao importados/lidos apenas na **primeira** inferencia com o ML
  habilitado — dentro das funcoes, nunca no escopo do modulo. Importar
  ``radar_api.ml`` tem custo zero e funciona em um ambiente **sem nenhuma
  biblioteca de ML instalada**. Cargas subsequentes reusam o cache
  (:func:`limpar_cache`, para testes/recarga).
* **Falha categorizada.** Habilitado mas sem ``ml_artefato``, com caminho
  inexistente, sem a dependencia de ML, com artefato ilegivel/incompativel ou
  com erro durante a inferencia -> :class:`~radar_api.erros.ErroMLIndisponivel`
  com ``detalhes['motivo']`` legivel por maquina (ver :data:`MOTIVOS`). Nenhuma
  ``ImportError``/``OSError``/excecao do deserializador escapa.
* **Saida rotulada** (Req 8.4). :class:`SaidaML` carrega sempre
  ``origem="modelo"`` e ``edicao=2023``: o Modelo_ML e treinado e usado
  **exclusivamente** sobre a Edicao 2023, a unica em que notas e perfil
  socioeconomico coexistem por participante. :class:`EntradaML` nao aceita
  Edicao justamente para tornar essa restricao estrutural.

A rota ``POST /v1/ml/inferencia`` (task 11.2) e uma casca fina sobre
:func:`inferir` / :func:`ml_disponivel`: a traducao de erro ja existente na app
converte :class:`~radar_api.erros.ErroRadar` em envelope + status via
``STATUS_POR_CODIGO``, sem regra nova.

**Nota de seguranca.** O artefato e desserializado do caminho apontado por
``RADAR_ML_ARTEFATO``, uma variavel de ambiente definida pelo **operador** da
implantacao; desserializar artefatos de terceiros nao confiaveis permite
execucao de codigo arbitrario. Trate o artefato como parte da imagem/volume
confiavel da implantacao, nunca como entrada de usuario. Nenhuma requisicao
HTTP influencia o caminho carregado.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from radar_api.config import Config
from radar_api.erros import ErroMLDesabilitado, ErroMLIndisponivel
from radar_api.modelos import Area, Dimensao

# Unica Edicao usada pelo Modelo_ML (treino e inferencia) — Req 8.1/8.4.
EDICAO_ML: Final[int] = 2023

# Rotulo de origem de toda saida do Modelo_ML — Req 8.4.
ORIGEM_MODELO: Final[str] = "modelo"

# Sub-motivos legiveis por maquina de ``ML_INDISPONIVEL`` (detalhes['motivo']).
MOTIVOS: Final[tuple[str, ...]] = (
    "artefato_nao_configurado",  # ml_habilitado=True, porem ml_artefato is None
    "artefato_inexistente",  # caminho configurado nao existe / nao e arquivo
    "dependencia_ausente",  # biblioteca de ML nao instalada no ambiente
    "artefato_ilegivel",  # erro de I/O ao ler o arquivo
    "artefato_invalido",  # desserializacao falhou
    "artefato_incompativel",  # objeto carregado nao expoe prever/predict
    "falha_inferencia",  # o artefato levantou excecao ao prever
)


# --------------------------------------------------------------------------- #
# Contratos (entrada, saida, artefato)                                        #
# --------------------------------------------------------------------------- #
class EntradaML(BaseModel):
    """Entrada de uma inferencia do Modelo_ML.

    Nao ha campo ``edicao``: o Modelo_ML e restrito a 2023 por construcao
    (:data:`EDICAO_ML`), de modo que nao existe requisicao capaz de pedir
    inferencia sobre 2024/2025 (Req 8.1).

    Attributes:
        area: Area de avaliacao alvo da previsao.
        perfil: Caracteristicas do participante, nas mesmas
            :class:`~radar_api.modelos.Dimensao` (colunas canonicas) usadas nos
            Recortes estatisticos. Vazio significa "sem perfil informado".
    """

    area: Area
    perfil: dict[Dimensao, str] = Field(default_factory=dict)

    def caracteristicas(self) -> dict[str, str]:
        """Serializa o perfil no formato consumido pelo artefato.

        Returns:
            Mapa ``nome_da_coluna_canonica -> valor``, com as chaves em texto
            (valor dos membros de :class:`~radar_api.modelos.Dimensao`).
        """
        return {dimensao.value: valor for dimensao, valor in self.perfil.items()}


class SaidaML(BaseModel):
    """Saida do Modelo_ML, sempre rotulada como derivada de modelo (Req 8.4).

    ``origem`` e ``edicao`` sao literais fixos: qualquer consumidor sabe, sem
    inspecao adicional, que o numero **nao** e uma estatistica observada da
    *silver* e que se refere apenas a Edicao 2023.

    Attributes:
        origem: Sempre ``"modelo"``.
        edicao: Sempre ``2023``.
        area: Area de avaliacao da previsao.
        valor_previsto: Valor produzido pelo artefato para a entrada.
        modelo_id: Identificador do artefato carregado (nome + versao no disco),
            para rastreabilidade da resposta.
    """

    origem: Literal["modelo"] = ORIGEM_MODELO
    edicao: Literal[2023] = EDICAO_ML
    area: Area
    valor_previsto: float
    modelo_id: str


@runtime_checkable
class ArtefatoML(Protocol):
    """Protocolo minimo que um artefato de Modelo_ML deve satisfazer.

    O artefato pode expor ``prever(caracteristicas) -> float`` (interface
    preferida, propria do projeto) ou o classico ``predict([caracteristicas])``
    de bibliotecas do ecossistema scikit-learn — :class:`ModeloML` aceita ambos.
    """

    def prever(self, caracteristicas: Mapping[str, str]) -> float:
        """Preve o valor para um conjunto de caracteristicas."""
        ...


# Assinatura de um carregador de artefato: recebe o caminho e devolve o objeto
# desserializado. Injetavel em :func:`carregar_modelo` para testes ou para
# trocar o formato de serializacao sem alterar o gating/cache.
Carregador = Callable[[Path], Any]


class ModeloML:
    """Envoltorio de um artefato de Modelo_ML ja carregado.

    Adapta o artefato (``prever`` ou ``predict``) para :class:`EntradaML` /
    :class:`SaidaML` e garante que qualquer excecao levantada por ele seja
    convertida em :class:`~radar_api.erros.ErroMLIndisponivel` — isolando a
    falha do ML (Req 8.3).

    Attributes:
        modelo_id: Identificador do artefato (nome + versao no disco).
    """

    def __init__(self, artefato: Any, modelo_id: str) -> None:
        self._artefato = artefato
        self.modelo_id = modelo_id

    def inferir(self, entrada: EntradaML) -> SaidaML:
        """Executa a inferencia para ``entrada``.

        Args:
            entrada: Area e perfil do participante.

        Returns:
            :class:`SaidaML` rotulada com ``origem="modelo"`` e ``edicao=2023``.

        Raises:
            ErroMLIndisponivel: Com ``motivo='falha_inferencia'`` se o artefato
                levantar qualquer excecao ou devolver algo nao numerico.
        """
        caracteristicas = entrada.caracteristicas()
        try:
            valor = self._prever(caracteristicas)
        except ErroMLIndisponivel:
            raise
        except Exception as exc:  # noqa: BLE001 — falha do ML e isolada aqui (Req 8.3)
            raise ErroMLIndisponivel(
                "falha_inferencia",
                artefato=self.modelo_id,
                mensagem=f"O modelo falhou ao inferir: {exc}",
            ) from exc
        return SaidaML(area=entrada.area, valor_previsto=valor, modelo_id=self.modelo_id)

    def _prever(self, caracteristicas: dict[str, str]) -> float:
        """Chama o artefato pela interface disponivel e normaliza para ``float``."""
        metodo_prever = getattr(self._artefato, "prever", None)
        if callable(metodo_prever):
            return float(metodo_prever(caracteristicas))
        metodo_predict = getattr(self._artefato, "predict", None)
        if callable(metodo_predict):
            return float(metodo_predict([caracteristicas])[0])
        raise ErroMLIndisponivel(
            "artefato_incompativel",
            artefato=self.modelo_id,
            mensagem="O artefato de ML nao expoe 'prever' nem 'predict'.",
        )


# --------------------------------------------------------------------------- #
# Cache do artefato (memoizacao do carregamento lazy)                         #
# --------------------------------------------------------------------------- #
# Chave = caminho absoluto do artefato + versao no disco (mtime_ns), de modo que
# substituir o arquivo em runtime invalida a entrada naturalmente. Preenchido
# **apenas** na primeira inferencia com o ML habilitado.
_CACHE: dict[str, ModeloML] = {}


def limpar_cache() -> None:
    """Descarta o(s) modelo(s) memoizado(s).

    Util em testes e para forcar recarga apos substituir o artefato.
    """
    _CACHE.clear()


def modelos_em_cache() -> int:
    """Quantidade de artefatos atualmente memoizados.

    Returns:
        0 enquanto nada foi carregado — o que, com o ML desabilitado, e
        permanente (nenhum acesso a disco acontece).
    """
    return len(_CACHE)


# --------------------------------------------------------------------------- #
# Carregamento lazy                                                           #
# --------------------------------------------------------------------------- #
def _carregar_artefato_padrao(caminho: Path) -> Any:
    """Desserializa o artefato do disco, importando a biblioteca sob demanda.

    Tenta ``joblib`` (formato usual do ecossistema scikit-learn) e, se ele nao
    estiver instalado, recorre ao ``pickle`` da biblioteca padrao. Os imports
    acontecem **dentro** desta funcao: o modulo permanece importavel em
    ambientes sem nenhuma biblioteca de ML.

    Args:
        caminho: Caminho do arquivo de artefato (existencia ja verificada).

    Returns:
        O objeto desserializado.
    """
    try:
        import joblib  # noqa: PLC0415 — import lazy e o ponto desta funcao
    except ImportError:
        joblib = None  # type: ignore[assignment]

    if joblib is not None:
        return joblib.load(caminho)

    import pickle  # noqa: PLC0415 — import lazy (stdlib, sem custo relevante)

    with caminho.open("rb") as arquivo:
        return pickle.load(arquivo)  # noqa: S301 — artefato confiavel do operador


def _resolver_artefato(config: Config) -> Path:
    """Valida e resolve o caminho do artefato configurado.

    Args:
        config: Configuracao da API (ja com o ML habilitado).

    Returns:
        Caminho do arquivo de artefato existente.

    Raises:
        ErroMLIndisponivel: ``artefato_nao_configurado`` se ``ml_artefato`` e
            ``None``; ``artefato_inexistente`` se o caminho nao aponta para um
            arquivo.
    """
    if config.ml_artefato is None:
        raise ErroMLIndisponivel(
            "artefato_nao_configurado",
            mensagem=("O modelo esta habilitado, mas RADAR_ML_ARTEFATO nao foi configurado."),
        )
    caminho = Path(config.ml_artefato)
    if not caminho.is_file():
        raise ErroMLIndisponivel(
            "artefato_inexistente",
            artefato=str(caminho),
            mensagem=f"O artefato de ML configurado nao existe: {caminho}",
        )
    return caminho


def ml_disponivel(config: Config) -> bool:
    """Informa se uma inferencia tem chance de ser atendida agora.

    Nunca levanta excecao e nunca carrega o modelo: com o ML desabilitado
    responde ``False`` **sem tocar o disco**; habilitado, faz apenas um ``stat``
    no artefato configurado. Serve para a rota da task 11.2 (e para o
    ``/health``) decidirem se anunciam o recurso.

    Args:
        config: Configuracao da API.

    Returns:
        ``True`` sse o ML esta habilitado e o artefato configurado existe.
    """
    if not config.ml_habilitado:
        return False
    if config.ml_artefato is None:
        return False
    return Path(config.ml_artefato).is_file()


def carregar_modelo(config: Config, *, carregador: Carregador | None = None) -> ModeloML:
    """Devolve o :class:`ModeloML` pronto para uso, carregando-o sob demanda.

    Primeira chamada com o ML habilitado: resolve o artefato, desserializa
    (importando a dependencia de ML somente aqui) e memoiza. Chamadas seguintes
    reusam o objeto memoizado — o arquivo nao e lido de novo enquanto o artefato
    no disco nao mudar (a chave de cache inclui o ``mtime``).

    Args:
        config: Configuracao da API.
        carregador: Carregador alternativo (``Path -> objeto``). ``None`` usa
            :func:`_carregar_artefato_padrao`.

    Returns:
        O :class:`ModeloML` correspondente ao artefato configurado.

    Raises:
        ErroMLDesabilitado: Se ``config.ml_habilitado`` e ``False``. Nada e
            importado nem lido do disco nesse caso.
        ErroMLIndisponivel: Para qualquer falha de configuracao, ambiente ou
            carga do artefato, com ``detalhes['motivo']`` em :data:`MOTIVOS`.
    """
    if not config.ml_habilitado:
        raise ErroMLDesabilitado()

    caminho = _resolver_artefato(config)
    versao = caminho.stat().st_mtime_ns
    chave = f"{caminho.resolve()}@{versao}"
    memoizado = _CACHE.get(chave)
    if memoizado is not None:
        return memoizado

    carregar = carregador if carregador is not None else _carregar_artefato_padrao
    try:
        artefato = carregar(caminho)
    except ErroMLIndisponivel:
        raise
    except ImportError as exc:
        raise ErroMLIndisponivel(
            "dependencia_ausente",
            artefato=str(caminho),
            mensagem=f"A dependencia de ML necessaria nao esta instalada: {exc}",
        ) from exc
    except OSError as exc:
        raise ErroMLIndisponivel(
            "artefato_ilegivel",
            artefato=str(caminho),
            mensagem=f"Nao foi possivel ler o artefato de ML: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — falha do ML e isolada aqui (Req 8.3)
        raise ErroMLIndisponivel(
            "artefato_invalido",
            artefato=str(caminho),
            mensagem=f"O artefato de ML nao pode ser carregado: {exc}",
        ) from exc

    if not _artefato_utilizavel(artefato):
        raise ErroMLIndisponivel(
            "artefato_incompativel",
            artefato=str(caminho),
            mensagem="O artefato de ML nao expoe 'prever' nem 'predict'.",
        )

    modelo = ModeloML(artefato, modelo_id=f"{caminho.name}@{versao}")
    _CACHE[chave] = modelo
    return modelo


def _artefato_utilizavel(artefato: Any) -> bool:
    """Verifica se o objeto carregado expoe ``prever`` ou ``predict``."""
    return callable(getattr(artefato, "prever", None)) or callable(
        getattr(artefato, "predict", None)
    )


def inferir(
    config: Config,
    entrada: EntradaML,
    *,
    carregador: Carregador | None = None,
) -> SaidaML:
    """Ponto de entrada de inferencia do Modelo_ML (Req 8.1/8.4).

    Args:
        config: Configuracao da API (faz o *gating* por ``ml_habilitado``).
        entrada: Area e perfil do participante.
        carregador: Carregador alternativo do artefato (ver
            :func:`carregar_modelo`).

    Returns:
        :class:`SaidaML` rotulada com ``origem="modelo"`` e ``edicao=2023``.

    Raises:
        ErroMLDesabilitado: ML desabilitado (padrao) — nenhum efeito colateral.
        ErroMLIndisponivel: ML habilitado, porem inutilizavel, ou falha na
            inferencia.
    """
    modelo = carregar_modelo(config, carregador=carregador)
    return modelo.inferir(entrada)


__all__ = [
    "EDICAO_ML",
    "MOTIVOS",
    "ORIGEM_MODELO",
    "ArtefatoML",
    "Carregador",
    "EntradaML",
    "ModeloML",
    "SaidaML",
    "carregar_modelo",
    "inferir",
    "limpar_cache",
    "ml_disponivel",
    "modelos_em_cache",
]
