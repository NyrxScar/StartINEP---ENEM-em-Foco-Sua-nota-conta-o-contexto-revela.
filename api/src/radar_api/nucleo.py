"""Nucleo analitico puro do servico Radar ENEM (``analisar``/``comparar``).

Este modulo hospeda o **nucleo analitico** do design (AD-5): funcoes puras de
consulta/agregacao sobre DuckDB, **sem** dependencia do framework web. A camada
HTTP fina (FastAPI, tasks 7.1/8.2) apenas traduz requisicoes/respostas e delega
para ele. Expoe tres funcoes publicas:

* :func:`analisar` — analise de recorte unico (Distribuicao + Percentil).
* :func:`verificar_capacidade_recorte` — guarda de capacidade **pura e
  reutilizavel** que decide se um pedido *baseado em nota* e permitido para uma
  Edicao, levantando o :class:`~radar_api.erros.ErroRadar` categorizado
  apropriado (``EDICAO_SEM_NOTAS``/``PERFIL_NOTA_NAO_COMBINAVEL``/
  ``RECORTE_INDISPONIVEL``). Tanto a borda HTTP (task 7.1) quanto
  :func:`comparar` a reutilizam — a fonte-de-verdade unica dessa decisao.
* :func:`comparar` — comparacao entre Edicoes (Req 3): roda :func:`analisar` por
  Edicao elegivel e registra as demais como :class:`~radar_api.modelos.OmissaoEdicao`.

Divisao de responsabilidades: :func:`analisar` permanece um **nucleo de calculo
puro** e *nao* aplica :func:`verificar_capacidade_recorte` — quem impoe a
capacidade sao a borda HTTP e :func:`comparar`. A validacao de entrada (nota
0..1000, area) e responsabilidade da borda HTTP; aqui a ausencia de Edicao
(``EDICAO_AUSENTE``) e propagada pelo :class:`~radar_api.catalogo.Catalogo`.

Fluxo de :func:`analisar` (Req 1.1/1.3/1.5/1.7, 2.5, 5.1):

1. Resolve ``silver_root`` e o ``limiar`` a partir da :class:`Catalogo`
   injetada (``catalogo.config``); obtem :class:`~radar_api.catalogo.InfoEdicao`
   (Capacidade + linhagem), o que **propaga** ``ErroEdicaoAusente`` quando a
   Edicao nao existe na *silver* — antes de qualquer leitura de dados.
2. Monta e executa, via :mod:`radar_api.consulta`, a consulta agregada
   (``count``/quantis/percentil) e a de histograma (faixas). Abre uma conexao
   DuckDB propria quando ``con`` nao e fornecida e fecha **apenas** o que abriu.
3. ``tamanho_amostral`` = ``count(*)`` do agregado (Req 1.5); o Percentil vem
   em 0..100 (Req 1.7). Recorte vazio = todas as linhas da Edicao com nota nao
   nula na Area (o construtor ja aplica ``nota_<area> IS NOT NULL``).
4. **Amostra vazia** (``tamanho_amostral == 0``): o DuckDB devolve quantis e
   percentil ``NULL``; nesse caso a Distribuicao e o percentil ficam ``None``
   (nao se tenta construir :class:`~radar_api.modelos.Quantis` a partir de
   ``None``). Distribuicao/percentil so sao materializados quando ha amostra e
   os quantis estao presentes.
5. Monta a :class:`~radar_api.modelos.Linhagem` a partir da ``InfoEdicao``
   (``manifesto_id``/``data_carga`` podem ser ``None`` — contrato externo).
6. Monta o :class:`~radar_api.modelos.ResultadoAnalise` e o faz passar pela
   guarda de privacidade (:func:`~radar_api.privacidade.aplicar_limiar`) antes
   de retornar (Req 1.6/9.3 centralizados em AD-4). A Capacidade (Req 2.5) e a
   Linhagem (Req 5.1) sempre acompanham a resposta.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import duckdb

from radar_api.catalogo import DIMENSOES_PERFIL
from radar_api.consulta import (
    LIMITE_GRUPOS_PADRAO,
    construir_consulta_agregada,
    construir_consulta_exploracao,
    construir_consulta_histograma,
    executar_agregada,
    executar_exploracao,
    executar_histograma,
)
from radar_api.erros import (
    ErroComparacaoSemEdicoesElegiveis,
    ErroEdicaoAusente,
    ErroEdicaoSemNotas,
    ErroPerfilNotaNaoCombinavel,
    ErroRadar,
    ErroRecorteIndisponivel,
)
from radar_api.modelos import (
    Dimensao,
    Distribuicao,
    FaixaHistograma,
    GrupoExploracao,
    Linhagem,
    OmissaoEdicao,
    Quantis,
    Recorte,
    ResultadoAnalise,
    ResultadoComparacao,
    ResultadoExploracao,
)
from radar_api.privacidade import aplicar_limiar

if TYPE_CHECKING:
    from radar_api.catalogo import Catalogo
    from radar_api.modelos import Area, Capacidade

# Chaves dos quantis na saida da consulta agregada (na ordem do modelo Quantis).
_CHAVES_QUANTIS: tuple[str, ...] = ("q_min", "q1", "mediana", "q3", "q_max")


def analisar(
    catalogo: Catalogo,
    edicao: int,
    area: Area,
    nota: float,
    recorte: Recorte,
    *,
    limiar: int | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ResultadoAnalise:
    """Analisa a distribuicao de uma Area num Recorte e o percentil de ``nota``.

    Nucleo analitico puro (sem HTTP). Le a *silver* via DuckDB em modo
    agregacao-only (nenhuma linha individual cruza a fronteira — Req 6.4/9.1),
    compoe a Distribuicao (faixas + quantis) e o Percentil (0..100 — Req 1.7), e
    aplica a guarda de privacidade (Req 1.6/9.3) antes de retornar. A resposta
    embute a Capacidade da Edicao (Req 2.5) e a Linhagem (Req 5.1).

    Args:
        catalogo: :class:`~radar_api.catalogo.Catalogo` injetado; fonte da
            ``config`` (``silver_root``/``limiar_agregacao``), da Capacidade e
            da linhagem (Manifesto/data de carga) da Edicao.
        edicao: Ano da Edicao a analisar.
        area: :class:`~radar_api.modelos.Area` de avaliacao (coluna
            ``nota_<area>``).
        nota: Nota informada cujo Percentil sera calculado. A validacao de
            intervalo (0..1000) e responsabilidade da borda HTTP; aqui a nota e
            usada como esta.
        recorte: :class:`~radar_api.modelos.Recorte` conjuntivo; vazio significa
            toda a Edicao com nota nao nula na Area (Req 1.3).
        limiar: ``Limite_Minimo_de_Agregacao`` a aplicar; quando ``None`` (o
            padrao), usa ``catalogo.config.limiar_agregacao``.
        con: Conexao DuckDB opcional (injecao de dependencia para testes). Se
            ``None``, uma conexao efemera e aberta e **fechada** por esta
            funcao; se fornecida, seu ciclo de vida permanece com o chamador.

    Returns:
        Um :class:`~radar_api.modelos.ResultadoAnalise` ja processado pela
        guarda de privacidade: com Distribuicao/percentil/tamanho amostral
        quando a amostra atinge o ``limiar``, ou marcado como
        ``estatisticamente_insuficiente`` (campos sensiveis ``None``) caso
        contrario.

    Raises:
        ErroEdicaoAusente: A Edicao nao existe na *silver* (Req 5.4), propagado
            por :meth:`~radar_api.catalogo.Catalogo.info_edicao`.
        ErroCapacidadeIndeterminada: A Capacidade da Edicao nao pode ser
            determinada (contrato/dados indisponiveis ou inconsistentes).
    """
    limiar_efetivo = limiar if limiar is not None else catalogo.config.limiar_agregacao
    silver_root = catalogo.config.silver_root

    # Resolve Capacidade + linhagem primeiro: propaga ErroEdicaoAusente antes de
    # tocar o DuckDB (evita um erro opaco de "arquivo nao encontrado" quando a
    # particao ``ano=<edicao>`` nao existe).
    info = catalogo.info_edicao(edicao)

    consulta_agregada = construir_consulta_agregada(silver_root, edicao, area, recorte, nota)
    consulta_histograma = construir_consulta_histograma(silver_root, edicao, area, recorte)

    conexao = con if con is not None else duckdb.connect()
    try:
        agregados = executar_agregada(conexao, consulta_agregada.sql, consulta_agregada.params)
        faixas_brutas = executar_histograma(
            conexao, consulta_histograma.sql, consulta_histograma.params
        )
    finally:
        if con is None:
            conexao.close()

    tamanho_amostral = int(agregados["tamanho_amostral"] or 0)

    distribuicao, percentil = _compor_distribuicao(tamanho_amostral, agregados, faixas_brutas)

    linhagem = Linhagem(
        edicoes=[edicao],
        manifestos={edicao: info.manifesto_id},
        datas_carga={edicao: info.data_carga},
    )

    resultado = ResultadoAnalise(
        edicao=edicao,
        area=area,
        distribuicao=distribuicao,
        percentil=percentil,
        tamanho_amostral=tamanho_amostral,
        estatisticamente_insuficiente=False,
        capacidade=info.capacidade,
        linhagem=linhagem,
    )
    return aplicar_limiar(resultado, limiar_efetivo)


def _compor_distribuicao(
    tamanho_amostral: int,
    agregados: dict[str, Any],
    faixas_brutas: list[dict[str, Any]],
) -> tuple[Distribuicao | None, float | None]:
    """Compoe ``(distribuicao, percentil)`` a partir dos agregados do DuckDB.

    Trata o caso de **amostra vazia** (Req 1.5): quando ``tamanho_amostral`` e 0,
    o DuckDB devolve quantis e percentil ``NULL`` e nenhuma faixa; construir
    :class:`~radar_api.modelos.Quantis` a partir de ``None`` violaria a validacao
    do modelo. Logo, so materializamos Distribuicao/percentil quando ha amostra
    (> 0) **e** todos os quantis estao presentes; caso contrario devolvemos
    ``(None, None)``, deixando a decisao final de supressao para a guarda de
    privacidade.

    Args:
        tamanho_amostral: ``count(*)`` do Recorte (linhas com nota nao nula).
        agregados: Dicionario da consulta agregada (chaves ``q_min``/``q1``/
            ``mediana``/``q3``/``q_max``/``percentil``).
        faixas_brutas: Faixas do histograma (``limite_inferior``/
            ``limite_superior``/``contagem``), possivelmente vazio.

    Returns:
        ``(Distribuicao, percentil)`` quando ha amostra e quantis; ``(None,
        None)`` para amostra vazia/quantis ausentes.
    """
    quantis_presentes = all(agregados.get(chave) is not None for chave in _CHAVES_QUANTIS)
    if tamanho_amostral <= 0 or not quantis_presentes:
        return (None, None)

    quantis = Quantis(
        minimo=agregados["q_min"],
        q1=agregados["q1"],
        mediana=agregados["mediana"],
        q3=agregados["q3"],
        maximo=agregados["q_max"],
    )
    faixas = [
        FaixaHistograma(
            limite_inferior=faixa["limite_inferior"],
            limite_superior=faixa["limite_superior"],
            contagem=int(faixa["contagem"]),
        )
        for faixa in faixas_brutas
    ]
    distribuicao = Distribuicao(faixas=faixas, quantis=quantis)
    percentil = float(agregados["percentil"])
    return (distribuicao, percentil)


def verificar_capacidade_recorte(
    catalogo: Catalogo,
    edicao: int,
    capacidade: Capacidade,
    recorte: Recorte,
) -> None:
    """Valida um pedido de analise *baseado em nota* contra a Capacidade da Edicao.

    Funcao **pura** e reutilizavel: e a fonte-de-verdade unica da decisao de
    capacidade para pedidos que dependem de nota. Tanto a borda HTTP (task 7.1)
    quanto :func:`comparar` a importam para nao duplicar a regra. Dado o
    :class:`~radar_api.modelos.Recorte` do pedido, levanta o
    :class:`~radar_api.erros.ErroRadar` categorizado apropriado quando a Edicao
    nao pode atende-lo, ou retorna ``None`` quando o pedido e permitido.

    As verificacoes sao aplicadas **da mais especifica para a mais generica**, e
    essa ordem importa porque uma mesma Dimensao pode satisfazer mais de uma
    condicao (ex.: em 2024, uma dimensao de perfil e *simultaneamente* "nao
    combinavel com notas" **e** "fora das dimensoes suportadas"):

    1. **``EDICAO_SEM_NOTAS``** (Req 2.3) — se a Edicao nao possui notas (ex.:
       2025), nenhum recorte de nota faz sentido; e a rejeicao mais fundamental,
       entao vem primeiro (independe do recorte).
    2. **``PERFIL_NOTA_NAO_COMBINAVEL``** (Req 2.4) — se o recorte inclui alguma
       dimensao de perfil (:data:`~radar_api.catalogo.DIMENSOES_PERFIL`) e a
       Edicao possui notas mas nao permite combina-las com perfil (ex.: 2024,
       cujo perfil foi desidentificado em arquivo separado, nao unificavel), o
       motivo *especifico* e a nao combinabilidade — mais informativo que o
       generico ``RECORTE_INDISPONIVEL``, por isso o precede.
    3. **``RECORTE_INDISPONIVEL``** (Req 2.2/2.6) — captura *generica* para
       qualquer dimensao fora de ``capacidade.dimensoes_suportadas``, informando
       tambem quais Edicoes suportam a dimensao (via
       :meth:`~radar_api.catalogo.Catalogo.edicoes_que_suportam`).

    Quando ha mais de uma Dimensao candidata a ser citada num erro, escolhe-se a
    de menor ``value`` (ordem lexicografica) para tornar o erro deterministico.

    Args:
        catalogo: :class:`~radar_api.catalogo.Catalogo` — consultado **apenas**
            no ramo ``RECORTE_INDISPONIVEL`` para listar ``edicoes_que_suportam``
            a dimensao indisponivel (Req 2.6).
        edicao: Ano da Edicao alvo (rotula os erros produzidos).
        capacidade: :class:`~radar_api.modelos.Capacidade` ja derivada da Edicao
            (tipicamente ``catalogo.capacidade(edicao)``).
        recorte: :class:`~radar_api.modelos.Recorte` do pedido (pode ser vazio).

    Returns:
        ``None`` quando o pedido de nota e permitido para a Edicao.

    Raises:
        ErroEdicaoSemNotas: A Edicao nao possui notas (Req 2.3).
        ErroPerfilNotaNaoCombinavel: O recorte inclui dimensao de perfil numa
            Edicao com notas nao combinaveis com perfil (Req 2.4).
        ErroRecorteIndisponivel: Alguma dimensao do recorte nao e suportada pela
            Edicao (Req 2.2/2.6).
    """
    if not capacidade.possui_notas:
        raise ErroEdicaoSemNotas(edicao=edicao)

    dims_recorte = set(recorte.filtros)

    dims_perfil = dims_recorte & set(DIMENSOES_PERFIL)
    if dims_perfil and not capacidade.perfil_combinavel_com_notas:
        dim_perfil = min(dims_perfil, key=lambda dim: dim.value)
        raise ErroPerfilNotaNaoCombinavel(edicao=edicao, dimensao=dim_perfil.value)

    dims_indisponiveis = dims_recorte - capacidade.dimensoes_suportadas
    if dims_indisponiveis:
        dim_indisponivel = min(dims_indisponiveis, key=lambda dim: dim.value)
        raise ErroRecorteIndisponivel(
            dimensao=dim_indisponivel.value,
            edicao=edicao,
            edicoes_que_suportam=catalogo.edicoes_que_suportam({dim_indisponivel}),
        )


def comparar(
    catalogo: Catalogo,
    edicoes: list[int],
    area: Area,
    nota: float,
    recorte: Recorte,
    *,
    limiar: int | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ResultadoComparacao:
    """Compara a Distribuicao/Percentil de ``nota`` entre varias Edicoes (Req 3).

    Para cada Edicao solicitada (deduplicada e emitida em **ordem crescente**,
    para tornar o resultado deterministico), decide a *elegibilidade* e:

    * Edicao inexistente na *silver* -> omitida com codigo ``EDICAO_AUSENTE``
      (Req 3.2), sem tocar o DuckDB.
    * Capacidade indeterminavel (:class:`~radar_api.erros.ErroCapacidadeIndeterminada`)
      -> omitida com codigo ``CAPACIDADE_INDETERMINADA`` (Req 3.2).
    * Recorte/Area nao suportados — :func:`verificar_capacidade_recorte` levanta
      -> omitida com o ``codigo`` categorizado do erro (``EDICAO_SEM_NOTAS`` /
      ``PERFIL_NOTA_NAO_COMBINAVEL`` / ``RECORTE_INDISPONIVEL``; Req 3.2).
    * Edicao **elegivel** -> :func:`analisar` e o resultado (rotulado pela sua
      ``edicao`` — Req 3.4) e adicionado a ``resultados`` (Req 3.1).

    Se **nenhuma** Edicao for elegivel, levanta
    :class:`~radar_api.erros.ErroComparacaoSemEdicoesElegiveis` (Req 3.3) — a
    comparacao vazia nao e um resultado valido.

    A checagem de elegibilidade reutiliza a *mesma* guarda usada pela borda HTTP
    (:func:`verificar_capacidade_recorte`), garantindo que uma Edicao seja
    incluida na comparacao se, e somente se, seria aceita numa analise unica.

    Args:
        catalogo: :class:`~radar_api.catalogo.Catalogo` injetado (edicoes
            disponiveis, capacidades e linhagem).
        edicoes: Edicoes solicitadas; duplicatas sao ignoradas e a ordem de
            saida e crescente.
        area: :class:`~radar_api.modelos.Area` de avaliacao.
        nota: Nota informada cujo Percentil sera calculado por Edicao elegivel.
        recorte: :class:`~radar_api.modelos.Recorte` conjuntivo aplicado a todas
            as Edicoes (pode ser vazio).
        limiar: ``Limite_Minimo_de_Agregacao`` repassado a :func:`analisar`;
            ``None`` usa ``catalogo.config.limiar_agregacao``.
        con: Conexao DuckDB opcional. Quando ``None``, uma conexao efemera e
            aberta, **reutilizada** por todas as analises e fechada ao final;
            quando fornecida, seu ciclo de vida permanece com o chamador.

    Returns:
        Um :class:`~radar_api.modelos.ResultadoComparacao` com ``resultados``
        (um :class:`~radar_api.modelos.ResultadoAnalise` por Edicao elegivel,
        rotulado) e ``omissoes`` (uma :class:`~radar_api.modelos.OmissaoEdicao`
        por Edicao nao elegivel, com o motivo legivel por maquina).

    Raises:
        ErroComparacaoSemEdicoesElegiveis: Nenhuma das Edicoes solicitadas e
            elegivel (Req 3.3).
    """
    disponiveis = set(catalogo.edicoes_disponiveis())
    resultados: list[ResultadoAnalise] = []
    omissoes: list[OmissaoEdicao] = []

    conexao = con if con is not None else duckdb.connect()
    try:
        for edicao in sorted(set(edicoes)):
            if edicao not in disponiveis:
                omissoes.append(OmissaoEdicao(edicao=edicao, codigo=ErroEdicaoAusente.codigo))
                continue
            try:
                capacidade = catalogo.capacidade(edicao)
                verificar_capacidade_recorte(catalogo, edicao, capacidade, recorte)
            except ErroRadar as erro:
                omissoes.append(OmissaoEdicao(edicao=edicao, codigo=erro.codigo))
                continue
            resultados.append(
                analisar(catalogo, edicao, area, nota, recorte, limiar=limiar, con=conexao)
            )
    finally:
        if con is None:
            conexao.close()

    if not resultados:
        raise ErroComparacaoSemEdicoesElegiveis(edicoes=edicoes)
    return ResultadoComparacao(resultados=resultados, omissoes=omissoes)


def explorar(
    catalogo: Catalogo,
    edicao: int,
    area: Area,
    dimensao: Dimensao,
    recorte: Recorte,
    *,
    limiar: int | None = None,
    limite_grupos: int = LIMITE_GRUPOS_PADRAO,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ResultadoExploracao:
    """Descreve uma Area quebrada por todos os valores de uma Dimensao.

    Responde "como a nota varia entre as UFs?" ou "entre escola publica e
    privada?" — perguntas que, com ``analisar`` sozinho, exigiriam uma
    requisicao por valor. Uma unica varredura com ``GROUP BY`` responde todas.

    **A mesma guarda de privacidade se aplica grupo a grupo.** Cada grupo abaixo
    do ``Limite_Minimo_de_Agregacao`` volta com os quantis anulados e
    ``estatisticamente_insuficiente``. O ``valor`` do grupo continua visivel, em
    coerencia com ``analisar``: a resposta admite que o grupo existe e que e
    pequeno demais para ser descrito, em vez de omiti-lo e deixar quem le supor
    que a lista e exaustiva.

    **A capacidade e validada incluindo a Dimensao de agrupamento.** Agrupar por
    uma Dimensao que a Edicao nao publica e tao invalido quanto filtrar por ela,
    entao ambas passam pela mesma
    :func:`verificar_capacidade_recorte` e produzem a mesma taxonomia de erro —
    inclusive ``edicoes_que_suportam`` em ``RECORTE_INDISPONIVEL`` (Req 2.6).

    Args:
        catalogo: :class:`~radar_api.catalogo.Catalogo` injetado.
        edicao: Ano da Edicao a explorar.
        area: :class:`~radar_api.modelos.Area` de avaliacao.
        dimensao: :class:`~radar_api.modelos.Dimensao` que define os grupos.
        recorte: Filtros conjuntivos aplicados antes do agrupamento; vazio
            significa explorar a Edicao inteira.
        limiar: ``Limite_Minimo_de_Agregacao``; ``None`` usa o da configuracao.
        limite_grupos: Teto de grupos devolvidos, do maior para o menor.
        con: Conexao DuckDB opcional (injecao para testes). Se ``None``, uma
            conexao efemera e aberta e fechada por esta funcao.

    Returns:
        Um :class:`~radar_api.modelos.ResultadoExploracao` com um grupo por valor
        da Dimensao, ja processado pela guarda de privacidade.

    Raises:
        ErroEdicaoAusente: A Edicao nao existe na *silver* (Req 5.4).
        ErroEdicaoSemNotas: A Edicao nao publica notas (Req 2.3).
        ErroPerfilNaoCombinavel: Recorte ou agrupamento de perfil numa Edicao que
            nao permite combina-lo com notas (Req 2.4).
        ErroRecorteIndisponivel: A Edicao nao sustenta alguma Dimensao pedida
            (Req 2.2/2.6).
    """
    limiar_efetivo = limiar if limiar is not None else catalogo.config.limiar_agregacao
    info = catalogo.info_edicao(edicao)

    # A Dimensao de agrupamento entra na validacao como se fosse um filtro: a
    # regra de capacidade olha as chaves do Recorte, nao os valores, entao este
    # Recorte sintetico reaproveita a taxonomia de erro inteira sem duplica-la.
    # O valor e irrelevante e nunca chega ao SQL da exploracao.
    recorte_validado = Recorte(filtros={**recorte.filtros, dimensao: ""})
    verificar_capacidade_recorte(catalogo, edicao, info.capacidade, recorte_validado)

    consulta = construir_consulta_exploracao(
        catalogo.config.silver_root,
        edicao,
        area,
        dimensao,
        recorte,
        limite_grupos=limite_grupos,
    )

    conexao = con if con is not None else duckdb.connect()
    try:
        linhas = executar_exploracao(conexao, consulta.sql, consulta.params)
    finally:
        if con is None:
            conexao.close()

    grupos: list[GrupoExploracao] = []
    for linha in linhas:
        tamanho = int(linha["tamanho_amostral"] or 0)
        insuficiente = tamanho < limiar_efetivo
        grupos.append(
            GrupoExploracao(
                valor=str(linha["valor"]),
                tamanho_amostral=None if insuficiente else tamanho,
                quantis=None
                if insuficiente
                else Quantis(
                    minimo=float(linha["q_min"]),
                    q1=float(linha["q1"]),
                    mediana=float(linha["mediana"]),
                    q3=float(linha["q3"]),
                    maximo=float(linha["q_max"]),
                ),
                estatisticamente_insuficiente=insuficiente,
            )
        )

    return ResultadoExploracao(
        edicao=edicao,
        area=area,
        dimensao=dimensao,
        grupos=grupos,
        # `==` e nao `>=`: o LIMIT corta exatamente no teto, entao bater o teto e
        # a unica evidencia disponivel de que havia mais valores.
        grupos_truncados=len(linhas) == limite_grupos,
        capacidade=info.capacidade,
        linhagem=Linhagem(
            edicoes=[edicao],
            manifestos={edicao: info.manifesto_id},
            datas_carga={edicao: info.data_carga},
        ),
    )


__all__ = ["analisar", "comparar", "explorar", "verificar_capacidade_recorte"]
