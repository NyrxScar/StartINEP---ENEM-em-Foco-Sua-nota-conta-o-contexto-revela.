"""Camada HTTP fina (FastAPI) do servico Radar ENEM.

Implementa o nivel de transporte do modelo de dois niveis do design (AD-5): esta
camada **apenas** traduz requisicoes/respostas HTTP e delega toda a decisao
analitica ao nucleo puro (:mod:`radar_api.nucleo`) e ao catalogo
(:mod:`radar_api.catalogo`). Nenhuma regra de negocio e reimplementada aqui — em
particular, a guarda de capacidade e a *mesma* funcao
(:func:`~radar_api.nucleo.verificar_capacidade_recorte`) usada por
:func:`~radar_api.nucleo.comparar`, garantindo que a analise unica e a
comparacao aceitem exatamente os mesmos pedidos.

Rotas registradas ate aqui (tasks 7.1, 8.2, 9.1 e 11.2):

============  =====================================  ===================================
Metodo        Caminho                                Requisitos
============  =====================================  ===================================
``POST``      ``/v1/analise``                        1.1, 1.8, 2.2, 2.3, 2.4, 2.5, 5.1
``POST``      ``/v1/comparacao``                     3.1, 3.2, 3.3, 3.4, 5.1
``GET``       ``/v1/edicoes``                        2.1, 5.2, 5.3
``GET``       ``/v1/edicoes/{edicao}/capacidade``    2.1, 2.6, 5.4
``POST``      ``/v1/ml/inferencia``                  8.1, 8.4
``GET``       ``/health``                            7.1
============  =====================================  ===================================

Com ``POST /v1/ml/inferencia`` (task 11.2) o conjunto de rotas do design esta
completo. Cada rota entrou como um novo ``@app.post``/``@app.get`` sem alterar a
injecao de dependencia nem a traducao de erros.

**O Modelo_ML e lateral.** :mod:`radar_api.ml` e importado no escopo deste
modulo, e nao dentro do handler, porque ele e *lazy* por construcao: importa-lo
nao carrega artefato nem biblioteca de ML (ambos so acontecem na primeira
inferencia com o ML habilitado), logo a app sobe normalmente em uma implantacao
sem nenhuma dependencia de ML instalada. O que a arquitetura proibe e a
dependencia inversa: o nucleo analitico (:mod:`radar_api.nucleo`) **nao**
importa :mod:`radar_api.ml`, de modo que a analise estatistica e a comparacao
funcionam identicamente com o ML habilitado, desabilitado ou quebrado
(Req 8.2/8.3; AD-5, Property 12).

**Injecao de dependencia.** :func:`criar_app` recebe uma
:class:`~radar_api.config.Config` opcional (``None`` -> :func:`carregar_config`),
constroi o :class:`~radar_api.catalogo.Catalogo` uma unica vez e os guarda em
``app.state``. Os handlers os obtem via :func:`Depends` (:func:`obter_config` /
:func:`obter_catalogo`), lendo de ``request.app.state`` — nunca de globais. Assim
um teste (ou um segundo processo) monta uma app independente apontando para
outra *silver* apenas chamando ``criar_app(Config(silver_root=...))``.

**Traducao de erros.** Toda resposta de erro usa o
:class:`~radar_api.erros.EnvelopeErro` (``codigo``/``mensagem``/``detalhes``) —
o formato ``{"detail": ...}`` padrao do FastAPI **nao** e emitido, pois o
envelope legivel por maquina e parte do contrato da API (Req 1.8, 2.x, 5.4).
Ver :func:`_tratar_erro_radar` e :func:`_tratar_erro_validacao`.

**Nota de seguranca (deliberada).** Este conjunto de endpoints e
**nao autenticado por design**: serve estatisticas publicas agregadas dos
microdados abertos do ENEM. Nenhum dado pessoal cruza a fronteira — apenas
agregados k-anonimizados pela guarda de privacidade (Req 9.1/9.3), com recortes
pequenos suprimidos. Nao ha, portanto, camada de autenticacao/autorizacao nem
dados por usuario a proteger; controles de exposicao (rede, *rate limiting*,
*ingress*) ficam com a camada de implantacao (Req 7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from radar_api.catalogo import Catalogo, InfoEdicao
from radar_api.config import Config, carregar_config
from radar_api.erros import (
    EnvelopeErro,
    ErroAreaInvalida,
    ErroCapacidadeIndeterminada,
    ErroNotaForaIntervalo,
    ErroRadar,
)
from radar_api.ml import EntradaML, SaidaML, inferir
from radar_api.modelos import (
    Capacidade,
    RequisicaoAnalise,
    RequisicaoComparacao,
    ResultadoAnalise,
    ResultadoComparacao,
)
from radar_api.nucleo import analisar, comparar, verificar_capacidade_recorte

# Codigo usado quando a validacao de entrada falha em um campo *fora* dos casos
# nomeados pelo contrato (``nota``/``area``) — ex.: ``edicao`` nao inteira ou uma
# chave de recorte desconhecida. Nao pertence a taxonomia de
# ``radar_api.erros`` (que cobre as situacoes previstas nos requisitos), mas
# preserva o formato do envelope para o cliente.
CODIGO_REQUISICAO_INVALIDA = "REQUISICAO_INVALIDA"

# Status HTTP das falhas de validacao de entrada (coerente com
# NOTA_FORA_INTERVALO/AREA_INVALIDA em ``STATUS_POR_CODIGO``).
_STATUS_VALIDACAO = 422


# --------------------------------------------------------------------------- #
# Dependencias (injecao via app.state)                                        #
# --------------------------------------------------------------------------- #
def obter_config(request: Request) -> Config:
    """Dependencia: a :class:`Config` da app corrente.

    Args:
        request: Requisicao em curso (da acesso a ``request.app.state``).

    Returns:
        A :class:`~radar_api.config.Config` guardada por :func:`criar_app`.
    """
    config: Config = request.app.state.config
    return config


def obter_catalogo(request: Request) -> Catalogo:
    """Dependencia: o :class:`Catalogo` da app corrente.

    Instancia unica por app (as Capacidades derivadas ficam memoizadas nela).

    Args:
        request: Requisicao em curso (da acesso a ``request.app.state``).

    Returns:
        O :class:`~radar_api.catalogo.Catalogo` construido por :func:`criar_app`.
    """
    catalogo: Catalogo = request.app.state.catalogo
    return catalogo


ConfigInjetada = Annotated[Config, Depends(obter_config)]
CatalogoInjetado = Annotated[Catalogo, Depends(obter_catalogo)]


# --------------------------------------------------------------------------- #
# Traducao de erros para o envelope padronizado                               #
# --------------------------------------------------------------------------- #
def _resposta_envelope(envelope: EnvelopeErro, status_http: int) -> JSONResponse:
    """Serializa um :class:`EnvelopeErro` como resposta JSON.

    Args:
        envelope: Envelope de erro a serializar.
        status_http: Status HTTP da resposta.

    Returns:
        :class:`JSONResponse` cujo corpo e ``{codigo, mensagem, detalhes}``.
    """
    return JSONResponse(status_code=status_http, content=jsonable_encoder(envelope))


async def _tratar_erro_radar(request: Request, exc: Exception) -> JSONResponse:
    """Traduz qualquer :class:`~radar_api.erros.ErroRadar` no envelope + status.

    O status vem da propria excecao (``status_http``, constante por subclasse e
    espelhada em :data:`~radar_api.erros.STATUS_POR_CODIGO`): validacao -> 422,
    violacao de capacidade -> 409, recurso ausente -> 404. Cobre, entre outros,
    ``EDICAO_AUSENTE`` (Req 5.4), ``EDICAO_SEM_NOTAS`` (Req 2.3),
    ``PERFIL_NOTA_NAO_COMBINAVEL`` (Req 2.4) e ``RECORTE_INDISPONIVEL`` com
    ``edicoes_que_suportam`` em ``detalhes`` (Req 2.2/2.6).

    Args:
        request: Requisicao em curso (nao usada; exigida pela assinatura).
        exc: Excecao capturada; sempre um :class:`ErroRadar` para este handler.

    Returns:
        Resposta JSON com o envelope do erro.
    """
    del request
    assert isinstance(exc, ErroRadar)  # noqa: S101 — garantido pelo registro do handler
    return _resposta_envelope(exc.envelope(), exc.status_http)


async def _tratar_erro_validacao(request: Request, exc: Exception) -> JSONResponse:
    """Traduz falhas de validacao do pydantic nos codigos do contrato.

    O FastAPI responderia ``422 {"detail": [...]}``; aqui a resposta e
    convertida para o :class:`EnvelopeErro`, mapeando os campos nomeados pelos
    requisitos:

    * ``nota`` invalida (fora de 0..1000 **ou** nao numerica) ->
      ``NOTA_FORA_INTERVALO`` (Req 1.8);
    * ``area`` invalida (fora de cn/ch/lc/mt/redacao) -> ``AREA_INVALIDA``
      (Req 1.1);
    * qualquer outro campo -> :data:`CODIGO_REQUISICAO_INVALIDA`, com a lista de
      violacoes em ``detalhes.violacoes``.

    Quando ``nota`` **e** ``area`` sao invalidas na mesma requisicao, ``nota`` tem
    precedencia (ordem fixa, para que a resposta seja deterministica).

    Args:
        request: Requisicao em curso (nao usada; exigida pela assinatura).
        exc: :class:`RequestValidationError` levantada pela validacao do corpo.

    Returns:
        Resposta JSON 422 com o envelope do erro correspondente.
    """
    del request
    assert isinstance(exc, RequestValidationError)  # noqa: S101 — garantido pelo registro
    erros = exc.errors()

    erro_nota = _primeiro_erro_do_campo(erros, "nota")
    if erro_nota is not None:
        return _resposta_envelope(
            ErroNotaForaIntervalo(nota=_valor_numerico(erro_nota.get("input"))).envelope(),
            _STATUS_VALIDACAO,
        )

    erro_area = _primeiro_erro_do_campo(erros, "area")
    if erro_area is not None:
        entrada = erro_area.get("input")
        area = str(entrada) if isinstance(entrada, str) else None
        return _resposta_envelope(ErroAreaInvalida(area=area).envelope(), _STATUS_VALIDACAO)

    envelope = EnvelopeErro(
        codigo=CODIGO_REQUISICAO_INVALIDA,
        mensagem="A requisicao contem campos invalidos.",
        detalhes={"violacoes": _resumir_violacoes(erros)},
    )
    return _resposta_envelope(envelope, _STATUS_VALIDACAO)


def _primeiro_erro_do_campo(erros: list[dict[str, Any]], campo: str) -> dict[str, Any] | None:
    """Retorna a primeira violacao cujo ``loc`` referencia ``campo``.

    Args:
        erros: Lista de violacoes de :meth:`RequestValidationError.errors`.
        campo: Nome do campo do corpo (ex.: ``"nota"``).

    Returns:
        A violacao encontrada, ou ``None`` se o campo nao foi citado.
    """
    for erro in erros:
        if campo in tuple(erro.get("loc", ())):
            return erro
    return None


def _valor_numerico(entrada: object) -> float | None:
    """Converte o valor rejeitado em ``float``, quando ele for numerico.

    Args:
        entrada: Valor original enviado pelo cliente (``input`` da violacao).

    Returns:
        O valor como ``float``, ou ``None`` quando nao numerico (ex.: texto),
        caso em que o envelope simplesmente nao cita a nota recebida.
    """
    if isinstance(entrada, bool):
        return None
    if isinstance(entrada, int | float):
        return float(entrada)
    return None


def _resumir_violacoes(erros: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Resume as violacoes de validacao em uma lista serializavel.

    Descarta o ``ctx`` do pydantic (que pode conter objetos nao serializaveis) e
    mantem apenas ``campo``/``tipo``/``mensagem``.

    Args:
        erros: Lista de violacoes de :meth:`RequestValidationError.errors`.

    Returns:
        Uma lista de dicionarios ``{campo, tipo, mensagem}``.
    """
    violacoes: list[dict[str, str]] = []
    for erro in erros:
        partes = [str(parte) for parte in erro.get("loc", ()) if parte != "body"]
        violacoes.append(
            {
                "campo": ".".join(partes),
                "tipo": str(erro.get("type", "")),
                "mensagem": str(erro.get("msg", "")),
            }
        )
    return violacoes


# --------------------------------------------------------------------------- #
# Health-check                                                                #
# --------------------------------------------------------------------------- #
def _silver_acessivel(raiz: Path) -> bool:
    """Indica se a raiz da *silver* e legivel (readiness — Req 7.1).

    A *silver* e um contrato de entrada externo (pode nao estar montada em
    runtime), portanto qualquer erro de sistema de arquivos e tratado como
    "inacessivel" em vez de propagado.

    Args:
        raiz: Caminho de ``config.silver_root``.

    Returns:
        ``True`` se ``raiz`` e um diretorio que pode ser listado.
    """
    try:
        if not raiz.is_dir():
            return False
        next(raiz.iterdir(), None)  # confirma permissao de leitura
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Fabrica da aplicacao                                                        #
# --------------------------------------------------------------------------- #
def criar_app(config: Config | None = None) -> FastAPI:
    """Monta a aplicacao FastAPI do Radar ENEM.

    Constroi (ou recebe) a :class:`Config`, deriva dela um
    :class:`~radar_api.catalogo.Catalogo` unico, publica ambos em ``app.state``
    para as dependencias :func:`obter_config`/:func:`obter_catalogo`, registra os
    handlers de erro (envelope padronizado) e as rotas desta task.

    Args:
        config: Configuracao a usar. Quando ``None``, e carregada do ambiente via
            :func:`~radar_api.config.carregar_config` (``RADAR_*``). Passar uma
            :class:`Config` explicita e o ponto de injecao usado pelos testes
            (ex.: ``silver_root`` apontando para uma *silver* temporaria).

    Returns:
        A instancia de :class:`FastAPI` configurada.
    """
    config_efetiva = config if config is not None else carregar_config()

    app = FastAPI(
        title="Radar ENEM — API de analise",
        version="0.1.0",
        description=(
            "Estatisticas agregadas do ENEM por recorte comparavel. Serve apenas "
            "agregados k-anonimizados; nenhuma linha individual e exposta."
        ),
    )
    app.state.config = config_efetiva
    app.state.catalogo = Catalogo(config_efetiva)

    app.add_exception_handler(ErroRadar, _tratar_erro_radar)
    app.add_exception_handler(RequestValidationError, _tratar_erro_validacao)

    # CORS: em desenvolvimento o frontend (Vite) roda em outra origem
    # (localhost:5173) e o navegador exige cabecalhos Access-Control-*. As
    # origens vem de RADAR_CORS_ORIGENS; lista vazia desliga o middleware
    # (caso de producao com mesma origem por roteamento de caminho).
    origens = config_efetiva.cors_origens_lista
    if origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origens,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    @app.get("/health", tags=["operacao"])
    def health(config: ConfigInjetada, catalogo: CatalogoInjetado) -> JSONResponse:
        """Health-check de *liveness/readiness* (Req 7.1).

        A readiness reflete a acessibilidade da raiz da *silver* (design, secao
        Implantacao): quando ela esta legivel, responde **200** com
        ``status="ok"``; quando nao esta, responde **503** com
        ``status="degradado"`` — assim uma *readiness probe* falha sem que o
        processo seja considerado morto. Nunca levanta excecao, mesmo com a
        *silver* ausente.

        Returns:
            JSON com ``status``, ``silver_acessivel``, ``edicoes`` (vazio quando
            inacessivel) e ``ambiente_referencia``.
        """
        acessivel = _silver_acessivel(config.silver_root)
        edicoes = catalogo.edicoes_disponiveis() if acessivel else []
        corpo = {
            "status": "ok" if acessivel else "degradado",
            "silver_acessivel": acessivel,
            "edicoes": edicoes,
            "ambiente_referencia": config.ambiente_referencia,
        }
        return JSONResponse(status_code=200 if acessivel else 503, content=corpo)

    @app.post("/v1/analise", response_model=ResultadoAnalise, tags=["analise"])
    def post_analise(requisicao: RequisicaoAnalise, catalogo: CatalogoInjetado) -> ResultadoAnalise:
        """Distribuicao + Percentil de uma nota dentro de um Recorte (Req 1.1).

        A validacao de entrada e **declarativa** (pydantic): ``nota`` fora de
        0..1000 e ``area`` invalida sao rejeitadas antes do handler e traduzidas
        por :func:`_tratar_erro_validacao` em ``NOTA_FORA_INTERVALO`` (Req 1.8) e
        ``AREA_INVALIDA``.

        Fluxo:

        1. ``catalogo.capacidade(edicao)`` — propaga ``EDICAO_AUSENTE`` (404)
           quando a Edicao nao existe na *silver* (Req 5.4).
        2. :func:`~radar_api.nucleo.verificar_capacidade_recorte` — guarda de
           capacidade compartilhada, que aplica ``EDICAO_SEM_NOTAS`` (Req 2.3),
           ``PERFIL_NOTA_NAO_COMBINAVEL`` (Req 2.4) e ``RECORTE_INDISPONIVEL``
           com ``edicoes_que_suportam`` (Req 2.2/2.6).
        3. :func:`~radar_api.nucleo.analisar` — calcula o resultado ja com a
           guarda de privacidade aplicada, embutindo ``capacidade`` (Req 2.5) e
           ``linhagem`` (Req 5.1).

        O handler e **sincrono** de proposito: as consultas DuckDB sao
        bloqueantes e o FastAPI as executa em *threadpool*, sem travar o laco de
        eventos.

        Returns:
            O :class:`~radar_api.modelos.ResultadoAnalise` da Edicao consultada.
        """
        capacidade = catalogo.capacidade(requisicao.edicao)
        verificar_capacidade_recorte(catalogo, requisicao.edicao, capacidade, requisicao.recorte)
        return analisar(
            catalogo,
            requisicao.edicao,
            requisicao.area,
            requisicao.nota,
            requisicao.recorte,
        )

    @app.post("/v1/comparacao", response_model=ResultadoComparacao, tags=["analise"])
    def post_comparacao(
        requisicao: RequisicaoComparacao, catalogo: CatalogoInjetado
    ) -> ResultadoComparacao:
        """Distribuicao + Percentil da mesma nota por Edicao elegivel (Req 3.1).

        Traducao fina: a decisao de elegibilidade e inteiramente de
        :func:`~radar_api.nucleo.comparar`, que reusa a *mesma* guarda de
        capacidade da analise unica — uma Edicao entra em ``resultados`` se, e
        somente se, seria aceita por ``POST /v1/analise``. Este handler nao
        reimplementa nem antecipa nenhuma dessas regras.

        Contrato da resposta 200:

        * ``resultados`` — um :class:`~radar_api.modelos.ResultadoAnalise` por
          Edicao elegivel, rotulado pela sua ``edicao`` (Req 3.1/3.4), em ordem
          crescente e sem duplicatas, cada um com ``capacidade`` (Req 2.5) e
          ``linhagem`` (Req 5.1) proprias;
        * ``omissoes`` — uma :class:`~radar_api.modelos.OmissaoEdicao` por Edicao
          nao elegivel, com o ``codigo`` legivel por maquina do motivo (Req 3.2).

        Toda Edicao solicitada aparece em exatamente um dos dois campos: nada e
        descartado em silencio.

        Erros sao herdados dos handlers ja registrados, sem tratamento local:

        * nenhuma Edicao elegivel -> ``ErroComparacaoSemEdicoesElegiveis``
          levantado pelo nucleo e traduzido por :func:`_tratar_erro_radar` em
          **409** ``COMPARACAO_SEM_EDICOES_ELEGIVEIS`` (Req 3.3);
        * ``nota`` fora de 0..1000 -> **422** ``NOTA_FORA_INTERVALO`` e ``area``
          invalida -> **422** ``AREA_INVALIDA``, via
          :func:`_tratar_erro_validacao` (os limites de ``nota`` sao identicos
          aos de :class:`~radar_api.modelos.RequisicaoAnalise`);
        * ``edicoes`` vazia -> **422** :data:`CODIGO_REQUISICAO_INVALIDA`.

        Sincrono de proposito, como :func:`post_analise`: as consultas DuckDB sao
        bloqueantes e o FastAPI as executa em *threadpool*.

        Returns:
            O :class:`~radar_api.modelos.ResultadoComparacao` das Edicoes pedidas.
        """
        return comparar(
            catalogo,
            requisicao.edicoes,
            requisicao.area,
            requisicao.nota,
            requisicao.recorte,
        )

    @app.get("/v1/edicoes", response_model=list[InfoEdicao], tags=["catalogo"])
    def get_edicoes(catalogo: CatalogoInjetado) -> list[InfoEdicao]:
        """Edicoes disponiveis na *silver*, com linhagem e Capacidade (Req 5.2).

        Traducao fina sobre o catalogo: itera ``edicoes_disponiveis()`` (ja em
        ordem crescente) e devolve, para cada Edicao, o
        :class:`~radar_api.catalogo.InfoEdicao` correspondente — ``manifesto_id``
        e ``data_carga`` (a linhagem que o Frontend exibe, Req 5.2/5.3) mais a
        ``capacidade`` derivada (Req 2.1), que permite ao formulario filtrar
        dimensoes de Recorte sem uma segunda requisicao.

        **Degradacao graciosa** (a *silver* e um contrato de entrada externo):

        * raiz ausente/vazia -> lista vazia, **nao** um erro: nao ha Edicao a
          listar, e isso nao e uma falha do servico;
        * Manifesto ausente/ilegivel -> a Edicao **continua listada**, com
          ``manifesto_id``/``data_carga`` iguais a ``None`` (a ausencia de
          linhagem nunca esconde a Edicao — Req 5.3/5.4). Isso e o que
          :meth:`~radar_api.catalogo.Catalogo.info_edicao` ja garante;
        * Capacidade indeterminavel (:class:`ErroCapacidadeIndeterminada`, ex.:
          Parquet ilegivel ou contrato inconsistente) -> a Edicao e **omitida**
          da listagem, em vez de derrubar a resposta inteira. Escolha
          deliberada, coerente com
          :meth:`~radar_api.catalogo.Catalogo.edicoes_que_suportam`, que ignora
          exatamente as mesmas Edicoes: uma Edicao cuja Capacidade nao pode ser
          determinada nao e utilizavel por nenhum endpoint analitico, e propagar
          409 aqui tornaria o catalogo inteiro indisponivel por causa de uma so
          particao defeituosa. Quem quiser o erro explicito de uma Edicao
          especifica pode consultar ``GET /v1/edicoes/{edicao}/capacidade``, que
          **propaga** ``CAPACIDADE_INDETERMINADA``.

        Sincrono de proposito, como as demais rotas: a derivacao de Capacidade
        consulta o DuckDB (bloqueante) e o FastAPI a executa em *threadpool*.

        Returns:
            Lista de :class:`~radar_api.catalogo.InfoEdicao` em ordem crescente
            de ``edicao`` (possivelmente vazia).
        """
        infos: list[InfoEdicao] = []
        for edicao in catalogo.edicoes_disponiveis():
            try:
                infos.append(catalogo.info_edicao(edicao))
            except ErroCapacidadeIndeterminada:
                continue
        return infos

    @app.get(
        "/v1/edicoes/{edicao}/capacidade",
        response_model=Capacidade,
        tags=["catalogo"],
    )
    def get_capacidade(edicao: int, catalogo: CatalogoInjetado) -> Capacidade:
        """Capacidade derivada de uma Edicao (Req 2.1/2.6).

        Devolve a :class:`~radar_api.modelos.Capacidade` *nua* — a mesma que o
        campo ``capacidade`` de ``GET /v1/edicoes`` e das respostas de analise
        embutem —, para que o formulario descubra quais dimensoes de Recorte a
        Edicao suporta e se a Area possui notas (Req 4.1/4.6) sem baixar o
        catalogo inteiro.

        Erros vem dos handlers ja registrados, sem tratamento local: Edicao
        inexistente na *silver* -> **404** ``EDICAO_AUSENTE`` (Req 5.4);
        Capacidade indeterminavel -> **409** ``CAPACIDADE_INDETERMINADA``
        (diferente de ``GET /v1/edicoes``, que omite a Edicao: aqui ela **e** o
        recurso pedido, logo o erro e a resposta correta); ``edicao`` nao inteira
        na rota -> **422** :data:`CODIGO_REQUISICAO_INVALIDA` via
        :func:`_tratar_erro_validacao`.

        Sincrono de proposito (consulta DuckDB bloqueante em *threadpool*).

        Returns:
            A :class:`~radar_api.modelos.Capacidade` da Edicao pedida.
        """
        return catalogo.capacidade(edicao)

    @app.post("/v1/ml/inferencia", response_model=SaidaML, tags=["ml"])
    def post_ml_inferencia(entrada: EntradaML, config: ConfigInjetada) -> SaidaML:
        """Previsao do Modelo_ML opcional, rotulada como modelo/2023 (Req 8.1/8.4).

        **A saida desta rota e secundaria e rotulada.** ``origem="modelo"`` e
        ``edicao=2023`` sao literais fixos de :class:`~radar_api.ml.SaidaML`:
        ``valor_previsto`` e a previsao de um artefato treinado exclusivamente
        sobre a Edicao 2023 (a unica em que notas e perfil socioeconomico
        coexistem por participante) e **nao** e uma estatistica observada da
        *silver*. Nada aqui substitui a Distribuicao/Percentil de
        ``POST /v1/analise``, que sao os numeros efetivamente medidos. Por isso
        :class:`~radar_api.ml.EntradaML` tambem nao aceita ``edicao``: nao existe
        requisicao capaz de pedir inferencia sobre 2024/2025.

        **A implantacao pode simplesmente nao oferecer o recurso.** O Modelo_ML e
        *gated* por ``RADAR_ML_HABILITADO`` (padrao ``False``), portanto a
        resposta esperada em uma implantacao puramente estatistica e **409**
        ``ML_DESABILITADO`` — uma recusa categorizada, nao uma falha do servico.
        Os endpoints estatisticos permanecem intactos nesse estado (Req 8.2/8.3).

        Casca fina sobre :func:`radar_api.ml.inferir`: todo o *gating*, o
        carregamento *lazy* e a classificacao de falhas vivem no modulo de ML e
        nenhuma dessas regras e reimplementada aqui. Os erros chegam ao cliente
        pelos handlers ja registrados, sem tratamento local:

        * ML desabilitado -> **409** ``ML_DESABILITADO``;
        * ML habilitado porem inutilizavel (artefato nao configurado,
          inexistente, ilegivel, incompativel, dependencia ausente) ou falha na
          inferencia -> **409** ``ML_INDISPONIVEL``, com o sub-motivo legivel por
          maquina em ``detalhes.motivo`` (ver :data:`radar_api.ml.MOTIVOS`);
        * ``area`` invalida -> **422** ``AREA_INVALIDA`` e qualquer outro campo
          invalido -> **422** :data:`CODIGO_REQUISICAO_INVALIDA`, via
          :func:`_tratar_erro_validacao`.

        Sincrono de proposito, como as demais rotas: a carga do artefato e a
        inferencia sao bloqueantes e o FastAPI as executa em *threadpool*.

        Returns:
            A :class:`~radar_api.ml.SaidaML` da inferencia, sempre com
            ``origem="modelo"``, ``edicao=2023`` e o ``modelo_id`` do artefato.
        """
        return inferir(config, entrada)

    return app


# Instancia de modulo para o servidor ASGI (``uvicorn radar_api.app:app``).
# Le a configuracao do ambiente; nao toca o disco na construcao (a descoberta de
# Edicoes acontece por requisicao), logo importar este modulo e seguro mesmo com
# a *silver* ausente.
app = criar_app()

__all__ = [
    "CODIGO_REQUISICAO_INVALIDA",
    "app",
    "criar_app",
    "obter_catalogo",
    "obter_config",
]
