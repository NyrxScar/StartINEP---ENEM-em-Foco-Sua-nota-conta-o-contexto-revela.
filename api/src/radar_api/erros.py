"""Taxonomia de erros legivel por maquina do servico Radar ENEM.

Este modulo e **auto-contido** (nao importa de ``modelos.py``) e define o
contrato de erros da API:

* :class:`EnvelopeErro` — o envelope padronizado (``codigo``, ``mensagem``,
  ``detalhes``) serializado nas respostas de erro.
* :class:`ErroRadar` — excecao interna base, com ``codigo`` e ``status_http``
  fixos por subclasse e ``mensagem``/``detalhes`` por instancia, convertivel em
  :class:`EnvelopeErro` via :meth:`ErroRadar.envelope`.
* Subclasses concretas, uma por codigo do contrato.
* :data:`STATUS_POR_CODIGO` — mapeamento ``codigo`` -> status HTTP, usado pela
  borda HTTP (FastAPI) para traduzir cada erro no status apropriado.

Os ``codigo`` sao parte do contrato da API e devem coincidir *verbatim* com os
identificadores abaixo. O mapeamento de status segue o principio: validacao de
entrada -> 422; violacao de capacidade -> 409; recurso ausente -> 404.

============================  ======  =========
Codigo                        HTTP    Requisito
============================  ======  =========
NOTA_FORA_INTERVALO           422     1.8
AREA_INVALIDA                 422     1.1
RECORTE_INDISPONIVEL          409     2.2, 2.6
EDICAO_SEM_NOTAS              409     2.3
PERFIL_NOTA_NAO_COMBINAVEL    409     2.4
COMPARACAO_SEM_EDICOES_...    409     3.3
EDICAO_AUSENTE                404     5.4
MANIFESTO_AUSENTE             404     5
MANIFESTO_INVALIDO            409     5
CAPACIDADE_INDETERMINADA      409     2
ML_DESABILITADO               409     8.1, 8.3
ML_INDISPONIVEL               409     8.1, 8.3
============================  ======  =========

Os dois codigos do Modelo_ML usam **409** (e nao 503) deliberadamente: o
Modelo_ML e um recurso **secundario e opcional** cuja presenca e uma *capacidade
declarada da implantacao* (``RADAR_ML_HABILITADO`` + ``RADAR_ML_ARTEFATO``), nao
um servico que caiu. Estar desabilitado ou sem artefato e uma configuracao
legitima e esperada do produto (Req 8.2/8.3), nao uma indisponibilidade
transitoria que convide o cliente a repetir a requisicao — logo pertencem a
mesma familia de ``RECORTE_INDISPONIVEL`` / ``EDICAO_SEM_NOTAS`` ("esta
implantacao/edicao nao oferece isso").
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field


class EnvelopeErro(BaseModel):
    """Envelope padronizado, legivel por maquina, de um erro da API.

    Attributes:
        codigo: Identificador categorizado do erro (parte do contrato da API).
        mensagem: Mensagem humana explicando o erro (em portugues).
        detalhes: Dados estruturados adicionais (ex.: ``edicoes_que_suportam``,
            ``dimensao``, ``edicao``). Vazio por padrao.
    """

    codigo: str
    mensagem: str
    detalhes: dict[str, object] = Field(default_factory=dict)


class ErroRadar(Exception):
    """Excecao interna base da API, convertivel em :class:`EnvelopeErro`.

    Subclasses fixam ``codigo`` e ``status_http`` (constantes de classe, parte
    do contrato) e, opcionalmente, uma ``mensagem_padrao``. Cada instancia
    carrega uma ``mensagem`` humana e um dicionario ``detalhes`` estruturado.

    Attributes:
        codigo: Codigo categorizado do erro (constante por subclasse).
        status_http: Status HTTP mapeado para o codigo (constante por subclasse).
        mensagem_padrao: Mensagem usada quando nenhuma e fornecida.
        mensagem: Mensagem humana desta instancia.
        detalhes: Detalhes estruturados desta instancia.
    """

    codigo: ClassVar[str] = "ERRO_RADAR"
    status_http: ClassVar[int] = 400
    mensagem_padrao: ClassVar[str] = "Erro ao processar a requisicao."

    def __init__(
        self,
        mensagem: str | None = None,
        *,
        detalhes: dict[str, object] | None = None,
    ) -> None:
        self.mensagem: str = mensagem if mensagem is not None else self.mensagem_padrao
        self.detalhes: dict[str, object] = dict(detalhes) if detalhes else {}
        super().__init__(self.mensagem)

    def envelope(self) -> EnvelopeErro:
        """Converte a excecao no :class:`EnvelopeErro` correspondente.

        Returns:
            Envelope com ``codigo``, ``mensagem`` e uma copia de ``detalhes``.
        """
        return EnvelopeErro(
            codigo=self.codigo,
            mensagem=self.mensagem,
            detalhes=dict(self.detalhes),
        )


class ErroNotaForaIntervalo(ErroRadar):
    """Nota informada fora do intervalo valido de 0 a 1000 (Req 1.8)."""

    codigo = "NOTA_FORA_INTERVALO"
    status_http = 422
    mensagem_padrao = "A nota informada esta fora do intervalo valido de 0 a 1000."

    def __init__(self, nota: float | None = None, mensagem: str | None = None) -> None:
        detalhes: dict[str, object] = {"minimo": 0, "maximo": 1000}
        if nota is not None:
            detalhes["nota"] = nota
        super().__init__(mensagem, detalhes=detalhes)


class ErroAreaInvalida(ErroRadar):
    """Area informada nao e uma das areas suportadas (Req 1.1)."""

    codigo = "AREA_INVALIDA"
    status_http = 422
    mensagem_padrao = "A area informada e invalida; use cn, ch, lc, mt ou redacao."
    areas_validas: ClassVar[tuple[str, ...]] = ("cn", "ch", "lc", "mt", "redacao")

    def __init__(self, area: str | None = None, mensagem: str | None = None) -> None:
        detalhes: dict[str, object] = {"areas_validas": list(self.areas_validas)}
        if area is not None:
            detalhes["area"] = area
        super().__init__(mensagem, detalhes=detalhes)


class ErroRecorteIndisponivel(ErroRadar):
    """Dimensao de recorte nao suportada pela edicao (Req 2.2, 2.6).

    Carrega em ``detalhes`` a ``dimensao`` solicitada, a ``edicao`` alvo e a
    lista ``edicoes_que_suportam`` o recorte, para orientar o cliente.
    """

    codigo = "RECORTE_INDISPONIVEL"
    status_http = 409

    def __init__(
        self,
        dimensao: str,
        edicao: int,
        edicoes_que_suportam: list[int],
        mensagem: str | None = None,
    ) -> None:
        msg = mensagem or (
            f"O recorte pela dimensao '{dimensao}' nao esta disponivel para a edicao {edicao}."
        )
        super().__init__(
            msg,
            detalhes={
                "dimensao": dimensao,
                "edicao": edicao,
                "edicoes_que_suportam": list(edicoes_que_suportam),
            },
        )


class ErroEdicaoSemNotas(ErroRadar):
    """Analise de nota pedida para uma edicao sem notas, ex.: 2025 (Req 2.3)."""

    codigo = "EDICAO_SEM_NOTAS"
    status_http = 409

    def __init__(self, edicao: int, mensagem: str | None = None) -> None:
        msg = mensagem or (
            f"A edicao {edicao} nao possui notas; analises de nota nao sao suportadas."
        )
        super().__init__(msg, detalhes={"edicao": edicao})


class ErroPerfilNotaNaoCombinavel(ErroRadar):
    """Perfil socioeconomico + nota nao combinaveis, ex.: 2024 (Req 2.4)."""

    codigo = "PERFIL_NOTA_NAO_COMBINAVEL"
    status_http = 409

    def __init__(
        self,
        edicao: int,
        dimensao: str | None = None,
        mensagem: str | None = None,
    ) -> None:
        msg = mensagem or (
            f"Na edicao {edicao}, perfil socioeconomico e notas nao sao combinaveis."
        )
        detalhes: dict[str, object] = {"edicao": edicao}
        if dimensao is not None:
            detalhes["dimensao"] = dimensao
        super().__init__(msg, detalhes=detalhes)


class ErroComparacaoSemEdicoesElegiveis(ErroRadar):
    """Nenhuma edicao solicitada suporta o recorte e a area (Req 3.3)."""

    codigo = "COMPARACAO_SEM_EDICOES_ELEGIVEIS"
    status_http = 409
    mensagem_padrao = "Nenhuma edicao solicitada suporta simultaneamente o recorte e a area."

    def __init__(
        self,
        edicoes: list[int] | None = None,
        mensagem: str | None = None,
    ) -> None:
        detalhes: dict[str, object] = {}
        if edicoes is not None:
            detalhes["edicoes"] = list(edicoes)
        super().__init__(mensagem, detalhes=detalhes)


class ErroEdicaoAusente(ErroRadar):
    """Edicao solicitada nao existe na camada silver (Req 5.4)."""

    codigo = "EDICAO_AUSENTE"
    status_http = 404

    def __init__(self, edicao: int, mensagem: str | None = None) -> None:
        msg = mensagem or f"A edicao {edicao} nao esta disponivel na camada silver."
        super().__init__(msg, detalhes={"edicao": edicao})


class ErroManifestoAusente(ErroRadar):
    """Manifesto da edicao nao encontrado (Req 5)."""

    codigo = "MANIFESTO_AUSENTE"
    status_http = 404
    mensagem_padrao = "O manifesto da edicao nao foi encontrado."

    def __init__(self, edicao: int | None = None, mensagem: str | None = None) -> None:
        detalhes: dict[str, object] = {}
        if edicao is not None:
            detalhes["edicao"] = edicao
        super().__init__(mensagem, detalhes=detalhes)


class ErroManifestoInvalido(ErroRadar):
    """Manifesto da edicao ilegivel ou invalido (Req 5)."""

    codigo = "MANIFESTO_INVALIDO"
    status_http = 409
    mensagem_padrao = "O manifesto da edicao e invalido ou ilegivel."

    def __init__(self, edicao: int | None = None, mensagem: str | None = None) -> None:
        detalhes: dict[str, object] = {}
        if edicao is not None:
            detalhes["edicao"] = edicao
        super().__init__(mensagem, detalhes=detalhes)


class ErroCapacidadeIndeterminada(ErroRadar):
    """Contrato ausente/inconsistente impede derivar a capacidade (Req 2)."""

    codigo = "CAPACIDADE_INDETERMINADA"
    status_http = 409
    mensagem_padrao = "Nao foi possivel determinar a capacidade da edicao a partir do contrato."

    def __init__(self, edicao: int | None = None, mensagem: str | None = None) -> None:
        detalhes: dict[str, object] = {}
        if edicao is not None:
            detalhes["edicao"] = edicao
        super().__init__(mensagem, detalhes=detalhes)


class ErroMLDesabilitado(ErroRadar):
    """Modelo_ML nao habilitado nesta implantacao (Req 8.1/8.3).

    Estado **normal** do produto: ``RADAR_ML_HABILITADO`` e ``False`` por padrao
    e o nucleo estatistico nunca depende do Modelo_ML. Sinalizado como 409 por
    ser uma capacidade nao oferecida, nao uma falha operacional.
    """

    codigo = "ML_DESABILITADO"
    status_http = 409
    mensagem_padrao = (
        "O modelo de machine learning esta desabilitado nesta implantacao; "
        "as analises estatisticas continuam disponiveis."
    )

    def __init__(self, mensagem: str | None = None) -> None:
        super().__init__(mensagem, detalhes={"ml_habilitado": False})


class ErroMLIndisponivel(ErroRadar):
    """Modelo_ML habilitado, porem inutilizavel (Req 8.1/8.3).

    Cobre toda falha isolada do componente secundario: artefato nao configurado,
    inexistente, ilegivel/invalido, dependencia de ML ausente no ambiente ou
    falha durante a inferencia. O sub-motivo legivel por maquina vai em
    ``detalhes['motivo']`` e o caminho configurado, quando houver, em
    ``detalhes['artefato']`` — nenhuma excecao crua (``ImportError``,
    ``FileNotFoundError``, erro do deserializador) escapa para o chamador.
    """

    codigo = "ML_INDISPONIVEL"
    status_http = 409
    mensagem_padrao = (
        "O modelo de machine learning esta habilitado, mas nao pode ser usado; "
        "as analises estatisticas continuam disponiveis."
    )

    def __init__(
        self,
        motivo: str,
        *,
        artefato: str | None = None,
        mensagem: str | None = None,
    ) -> None:
        detalhes: dict[str, object] = {"motivo": motivo}
        if artefato is not None:
            detalhes["artefato"] = artefato
        super().__init__(mensagem, detalhes=detalhes)


# Registro das subclasses concretas do contrato. Fonte unica para derivar o
# mapeamento codigo -> status HTTP, evitando divergencia entre as classes e a
# tabela de traducao usada pela borda HTTP.
_CLASSES_ERRO: tuple[type[ErroRadar], ...] = (
    ErroNotaForaIntervalo,
    ErroAreaInvalida,
    ErroRecorteIndisponivel,
    ErroEdicaoSemNotas,
    ErroPerfilNotaNaoCombinavel,
    ErroComparacaoSemEdicoesElegiveis,
    ErroEdicaoAusente,
    ErroManifestoAusente,
    ErroManifestoInvalido,
    ErroCapacidadeIndeterminada,
    ErroMLDesabilitado,
    ErroMLIndisponivel,
)

# Mapeamento codigo -> status HTTP (Req: traducao na borda HTTP, task 7.1).
STATUS_POR_CODIGO: dict[str, int] = {classe.codigo: classe.status_http for classe in _CLASSES_ERRO}


def status_para_codigo(codigo: str) -> int:
    """Retorna o status HTTP mapeado para um ``codigo`` do contrato.

    Args:
        codigo: Codigo categorizado do erro.

    Returns:
        O status HTTP correspondente; ``500`` para codigos desconhecidos
        (erro interno inesperado, fora do contrato).
    """
    return STATUS_POR_CODIGO.get(codigo, 500)


__all__ = [
    "STATUS_POR_CODIGO",
    "EnvelopeErro",
    "ErroAreaInvalida",
    "ErroCapacidadeIndeterminada",
    "ErroComparacaoSemEdicoesElegiveis",
    "ErroEdicaoAusente",
    "ErroEdicaoSemNotas",
    "ErroMLDesabilitado",
    "ErroMLIndisponivel",
    "ErroManifestoAusente",
    "ErroManifestoInvalido",
    "ErroNotaForaIntervalo",
    "ErroPerfilNotaNaoCombinavel",
    "ErroRadar",
    "ErroRecorteIndisponivel",
    "status_para_codigo",
]
