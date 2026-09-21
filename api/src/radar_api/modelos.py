"""Modelos de dados pydantic do servico Radar ENEM.

Define os enums e modelos de requisicao/resposta que trafegam entre a camada
HTTP (FastAPI), o nucleo analitico e o catalogo. Todos os resultados sao
*agregados* (distribuicoes, quantis, contagens, percentil) — nenhuma linha
individual da camada *silver* e representada aqui, honrando a desidentificacao
do INEP (Req 9).

Requisitos atendidos por estes modelos:

* **1.3 / 1.4** — ``Recorte`` com filtros conjuntivos (AND); dicionario vazio
  significa "sem recorte" (toda a Edicao).
* **1.7** — ``ResultadoAnalise.percentil`` representa a posicao 0..100 (anulavel
  quando suprimido).
* **1.8** — ``RequisicaoAnalise.nota`` restrita ao intervalo 0..1000 inclusive
  via ``Field(ge=0, le=1000)``; fora do intervalo produz ``ValidationError``.
* **2.5** — ``ResultadoAnalise.capacidade`` carrega a ``Capacidade`` da Edicao.
* **5.1** — ``ResultadoAnalise.linhagem`` carrega as Edicoes/Manifestos que
  fundamentam a resposta.

Os valores dos membros de ``Dimensao`` sao *exatamente* os nomes das colunas
canonicas da camada *silver* (ex.: ``renda_familiar`` para renda), pois sao
usados para montar o SQL do Motor_de_Consulta mais adiante.

Observacao de arquitetura: ``Capacidade`` (um modelo de dados puro) e definida
aqui — e nao em ``catalogo`` — para que ``ResultadoAnalise`` possa referencia-la
sem introduzir importacao circular; ``catalogo`` importara ``Capacidade`` deste
modulo.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Area(str, Enum):  # noqa: UP042 — forma (str, Enum) fixada pelo design
    """Area de avaliacao do ENEM.

    Cada membro corresponde ao sufixo da coluna de nota na camada *silver*
    (``nota_<area>``): ``nota_cn``, ``nota_ch``, ``nota_lc``, ``nota_mt`` e
    ``nota_redacao``.
    """

    CN = "cn"
    CH = "ch"
    LC = "lc"
    MT = "mt"
    REDACAO = "redacao"


class Dimensao(str, Enum):  # noqa: UP042 — forma (str, Enum) fixada pelo design
    """Dimensao de Recorte suportada pela camada *silver*.

    O *valor* de cada membro e o nome da coluna canonica correspondente na
    *silver*, usado diretamente na montagem das clausulas SQL (ex.:
    ``renda_familiar`` para renda, ``escolaridade_pai``/``escolaridade_mae``
    para escolaridade dos pais).

    Nem toda Edicao sustenta todas as Dimensoes, e a diferenca nao e uniforme:
    ``municipio_prova`` existe em todas as Edicoes verificadas, ``codigo_escola``
    so em 2024 (o INEP removeu o identificador de instituicao dos microdados e
    voltou a publica-lo naquela edicao) e ``localizacao_escola`` depende de a
    Edicao trazer atributos de escola. Quem sustenta o que e responsabilidade de
    :class:`Capacidade`, derivada por Edicao — nunca presumida aqui.
    """

    REGIAO = "regiao"
    UF = "uf_prova"
    MUNICIPIO = "municipio_prova"
    TIPO_ESCOLA = "tipo_escola"
    DEP_ADM = "dependencia_adm_escola"
    LOCALIZACAO_ESCOLA = "localizacao_escola"
    CODIGO_ESCOLA = "codigo_escola"
    RENDA = "renda_familiar"
    COR_RACA = "cor_raca"
    ESCOLARIDADE_PAI = "escolaridade_pai"
    ESCOLARIDADE_MAE = "escolaridade_mae"


class Recorte(BaseModel):
    """Conjunto de filtros aplicados de forma conjuntiva (AND) sobre a *silver*.

    ``filtros`` mapeia cada :class:`Dimensao` selecionada ao valor exigido para
    aquela coluna. Um dicionario vazio significa "sem recorte", isto e, a
    analise considera todas as linhas da Edicao (Req 1.3); quando ha filtros,
    todos sao aplicados em conjunto (Req 1.4).
    """

    filtros: dict[Dimensao, str] = Field(default_factory=dict)


class RequisicaoAnalise(BaseModel):
    """Requisicao de analise de distribuicao e percentil por recorte.

    A ``nota`` e validada na borda para o intervalo 0..1000 inclusive (Req 1.8):
    valores fora desse intervalo produzem um ``ValidationError`` do pydantic,
    posteriormente mapeado para o codigo ``NOTA_FORA_INTERVALO``.
    """

    edicao: int
    area: Area
    nota: float = Field(ge=0, le=1000)
    recorte: Recorte = Field(default_factory=Recorte)


class RequisicaoExploracao(BaseModel):
    """Requisicao de exploracao de uma Area por uma Dimensao (Req 1.1/2.2).

    Irma de :class:`RequisicaoAnalise`, sem ``nota``: aqui a pergunta nao e
    "onde estou?" e sim "como esta Area se distribui entre os valores desta
    Dimensao?". Por isso nao ha percentil na resposta — nao existe nota de
    referencia para posicionar.

    ``recorte`` e aplicado **antes** do agrupamento, o que permite perguntas
    encadeadas: agrupar por UF dentro do Nordeste, por exemplo.
    """

    edicao: int
    area: Area
    dimensao: Dimensao
    recorte: Recorte = Field(default_factory=Recorte)


class RequisicaoComparacao(BaseModel):
    """Requisicao de comparacao da mesma nota entre varias Edicoes (Req 3.1).

    Irma de :class:`RequisicaoAnalise`: mesma Area, Nota e Recorte, porem com
    uma *lista* de Edicoes em vez de uma so. A ``nota`` mantem exatamente os
    mesmos limites (``ge=0``, ``le=1000``) para que a violacao seja traduzida
    pelo mesmo codigo ``NOTA_FORA_INTERVALO`` da analise unica (Req 1.8), e o
    ``recorte`` e aplicado de forma identica a todas as Edicoes.

    ``edicoes`` exige ao menos um elemento (``min_length=1``): uma comparacao sem
    Edicao nenhuma nao e um pedido interpretavel e e recusada na borda como
    requisicao invalida, antes de qualquer acesso a *silver*. Duplicatas e ordem
    sao irrelevantes — :func:`~radar_api.nucleo.comparar` deduplica e emite os
    resultados em ordem crescente de Edicao.
    """

    edicoes: list[int] = Field(min_length=1)
    area: Area
    nota: float = Field(ge=0, le=1000)
    recorte: Recorte = Field(default_factory=Recorte)


class Quantis(BaseModel):
    """Resumo por quantis da distribuicao de notas de um Recorte."""

    minimo: float
    q1: float
    mediana: float
    q3: float
    maximo: float


class FaixaHistograma(BaseModel):
    """Uma faixa (bucket) do histograma da distribuicao de notas."""

    limite_inferior: float
    limite_superior: float
    contagem: int


class Distribuicao(BaseModel):
    """Distribuicao agregada das notas de um Recorte: histograma + quantis."""

    faixas: list[FaixaHistograma]
    quantis: Quantis


class Capacidade(BaseModel):
    """Capacidade analitica de uma Edicao (Req 2.1/2.5).

    Modelo de dados puro definido neste modulo (e nao em ``catalogo``) para
    evitar importacao circular com :class:`ResultadoAnalise`. Descreve quais
    dimensoes de Recorte a Edicao suporta, se ela possui notas e se seu perfil
    socioeconomico pode ser combinado com notas (ambos ``False`` para as
    edicoes desidentificadas de 2024/2025 conforme o contrato).
    """

    edicao: int
    dimensoes_suportadas: set[Dimensao]
    possui_notas: bool
    perfil_combinavel_com_notas: bool


class Linhagem(BaseModel):
    """Linhagem de uma resposta: Edicoes, Manifestos e datas de carga (Req 5.1).

    ``manifestos`` associa cada Edicao ao identificador do seu Manifesto
    (``fonte_sha256`` + ``fonte_last_modified``) e ``datas_carga`` ao timestamp
    de carga correspondente.

    Os *valores* de ``manifestos`` e ``datas_carga`` sao anulaveis: a *silver* e
    seus Manifestos sao um contrato de entrada externo que pode estar ausente em
    runtime (ver design, AD-3/Riscos). Quando o Manifesto de uma Edicao usada
    esta ausente/ilegivel (ou o ETL nao e importavel), a Edicao ainda e listada
    em ``edicoes`` — honrando Req 5.1 —, porem com ``manifesto_id``/``data_carga``
    iguais a ``None`` para aquela Edicao. Chaves sempre presentes para cada
    Edicao de ``edicoes``; apenas o valor pode ser ``None``.
    """

    edicoes: list[int]
    manifestos: dict[int, str | None]
    datas_carga: dict[int, datetime | None]


class GrupoExploracao(BaseModel):
    """Um valor de Dimensao e as estatisticas da Area dentro dele.

    Os campos estatisticos sao anulaveis pela mesma razao de
    :class:`ResultadoAnalise`: quando o grupo nao atinge o
    ``Limite_Minimo_de_Agregacao``, a guarda de privacidade anula os detalhes e
    marca ``estatisticamente_insuficiente``. O grupo continua na resposta, com o
    ``valor`` visivel — a interface diz que o grupo existe e que e pequeno demais
    para ser descrito, em vez de fingir que ele nao existe (Req 1.6/9.3).

    Attributes:
        valor: Valor da Dimensao, sempre como texto (e o que a *silver* compara).
        tamanho_amostral: Pessoas com nota valida na Area dentro do grupo.
        quantis: Resumo por quantis das notas do grupo.
        estatisticamente_insuficiente: Grupo abaixo do limiar de divulgacao.
    """

    valor: str
    tamanho_amostral: int | None
    quantis: Quantis | None
    estatisticamente_insuficiente: bool


class ResultadoExploracao(BaseModel):
    """Resposta de ``POST /v1/exploracao``: uma Area vista por uma Dimensao.

    Attributes:
        edicao: Edicao explorada.
        area: Area de avaliacao.
        dimensao: Dimensao usada para agrupar.
        grupos: Um item por valor da Dimensao, do maior grupo para o menor.
        grupos_truncados: ``True`` quando existiam mais valores do que o teto de
            grupos da consulta, de modo que a lista nao e exaustiva. Explicito
            para que a interface possa dizer isso, em vez de a pessoa supor que
            viu todos os municipios do pais.
        capacidade: Capacidade da Edicao (Req 2.5).
        linhagem: Procedencia dos dados (Req 5.1).
    """

    edicao: int
    area: Area
    dimensao: Dimensao
    grupos: list[GrupoExploracao]
    grupos_truncados: bool
    capacidade: Capacidade
    linhagem: Linhagem


class ResultadoAnalise(BaseModel):
    """Resultado de uma analise de recorte unico.

    Os campos ``distribuicao``, ``percentil`` e ``tamanho_amostral`` sao
    anulaveis: quando o Recorte cai abaixo do ``Limite_Minimo_de_Agregacao``, a
    guarda de privacidade os anula e marca ``estatisticamente_insuficiente``
    como ``True`` (Req 1.6 / 4.4 / 9.3), sem expor detalhes. Toda resposta
    carrega a ``capacidade`` da Edicao (Req 2.5) e a ``linhagem`` (Req 5.1).
    """

    edicao: int
    area: Area
    distribuicao: Distribuicao | None
    percentil: float | None
    tamanho_amostral: int | None
    estatisticamente_insuficiente: bool
    capacidade: Capacidade
    linhagem: Linhagem


class OmissaoEdicao(BaseModel):
    """Registro de uma Edicao omitida de uma comparacao (Req 3.2).

    ``codigo`` e o motivo legivel por maquina da omissao (ex.: recorte nao
    suportado pela Edicao), reutilizando a taxonomia de erros.
    """

    edicao: int
    codigo: str


class ResultadoComparacao(BaseModel):
    """Resultado de uma comparacao entre Edicoes.

    ``resultados`` traz um :class:`ResultadoAnalise` por Edicao elegivel, cada
    um rotulado com sua Edicao (Req 3.4); ``omissoes`` lista as Edicoes que nao
    suportam o Recorte/Area solicitados, com o motivo (Req 3.2).
    """

    resultados: list[ResultadoAnalise]
    omissoes: list[OmissaoEdicao]
