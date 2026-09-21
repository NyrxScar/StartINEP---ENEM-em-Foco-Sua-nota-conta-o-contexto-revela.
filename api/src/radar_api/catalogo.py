"""Catalogo do servico Radar ENEM: descoberta de edicoes, manifestos e capacidades.

Este modulo trata a camada *silver* e seus Manifestos como um **contrato de
entrada externo** (ver design, AD-3 e secao de Riscos): nada e assumido como
presente em runtime. O :class:`Catalogo`:

* **descobre** as Edicoes existentes varrendo ``config.silver_root`` por
  diretorios ``ano=<edicao>`` (Req 5.2);
* **le o Manifesto** de uma Edicao de forma tardia (import *lazy* de
  ``radar_etl.manifesto``), degradando de forma legivel por maquina quando o
  pacote do ETL ou o arquivo de manifesto estao ausentes/ilegiveis (Req 5);
* **deriva a Capacidade** de cada Edicao a partir dos proprios dados da
  *silver* (presenca de colunas nao nulas via DuckDB).

Degradacao graciosa (Req 5.4):

* Edicao inexistente na *silver* -> :class:`~radar_api.erros.ErroEdicaoAusente`.
* ``radar_etl`` inimportavel ou manifesto nao encontrado ->
  :class:`~radar_api.erros.ErroManifestoAusente`.
* Manifesto presente porem ilegivel/malformado ->
  :class:`~radar_api.erros.ErroManifestoInvalido`.
* Parquet da Edicao ilegivel ->
  :class:`~radar_api.erros.ErroCapacidadeIndeterminada`.

Nota sobre a derivacao de Capacidade (AD-3): a derivacao **primaria** e feita
a partir do contrato canonico da Edicao — a funcao pura
:func:`derivar_capacidade_do_contrato`, dirigida pelas colecoes
``mapeamento``/``derivadas``/``ausentes`` do contrato (regra *sse* de
:data:`SUSTENTACAO_CANONICA`). :meth:`Catalogo.capacidade` e *contract-first,
data-fallback*: tenta o contrato (import *lazy* de
``radar_etl.contracts.modelos``) e, quando o ETL nao e importavel em runtime ou
o contrato da Edicao nao pode ser localizado de forma limpa, cai na derivacao
**dos dados** (uma dimensao e suportada sse a coluna existe e possui ao menos um
valor nao nulo na Edicao). Enquanto o ETL nao esta instalado, o caminho ativo e
o data-fallback; a assinatura publica de :meth:`Catalogo.capacidade` permanece
inalterada.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import duckdb
from pydantic import BaseModel

from radar_api.erros import (
    ErroCapacidadeIndeterminada,
    ErroEdicaoAusente,
    ErroManifestoAusente,
    ErroManifestoInvalido,
)
from radar_api.modelos import Area, Capacidade, Dimensao

if TYPE_CHECKING:
    from radar_api.config import Config

# ---------------------------------------------------------------------------
# Mapeamento canonico (AD-3): colunas que sustentam cada Dimensao / as notas.
# Estas constantes sao PUBLICAS e importaveis: sao a fonte-de-verdade da regra
# *sse* de derivacao de Capacidade e o teste da Property 7 (task 3.3) as
# exercita com contratos sinteticos.
# ---------------------------------------------------------------------------

# Colunas de nota canonicas (``nota_cn``/``nota_ch``/``nota_lc``/``nota_mt``/
# ``nota_redacao``), derivadas das Areas. Sustentam ``possui_notas`` tanto na
# derivacao por contrato quanto no fallback data-driven (ausentes/nulas em 2025).
NOTAS_CANONICAS: tuple[str, ...] = tuple(f"nota_{area.value}" for area in Area)

# Dimensoes de perfil socioeconomico. ``perfil_combinavel_com_notas`` exige que
# ao menos uma destas esteja disponivel *junto* das notas; se nenhuma estiver, o
# perfil nao e combinavel com notas (caso de 2024, cujo perfil foi
# desidentificado e publicado em arquivo separado, nao unificavel — Req 9.2).
DIMENSOES_PERFIL: tuple[Dimensao, ...] = (
    Dimensao.RENDA,
    Dimensao.COR_RACA,
    Dimensao.ESCOLARIDADE_PAI,
    Dimensao.ESCOLARIDADE_MAE,
)

# Colunas canonicas que *sustentam* cada Dimensao de Recorte (AD-3). Uma
# Dimensao e suportada por uma Edicao sse TODAS as suas colunas de sustentacao
# estao disponiveis (em ``mapeamento``/``derivadas``) e NENHUMA em ``ausentes``.
# Por ora cada Dimensao e sustentada pela propria coluna canonica homonima (o
# *valor* do membro de ``Dimensao``); ``REGIAO`` e sustentada por ``regiao``,
# que o ETL materializa como *derivada* de ``uf_prova`` (logo tipicamente em
# ``contrato.derivadas``). A tupla admite, no futuro, dimensoes sustentadas por
# mais de uma coluna sem alterar a regra.
SUSTENTACAO_CANONICA: dict[Dimensao, tuple[str, ...]] = {
    Dimensao.REGIAO: (Dimensao.REGIAO.value,),
    Dimensao.UF: (Dimensao.UF.value,),
    Dimensao.MUNICIPIO: (Dimensao.MUNICIPIO.value,),
    Dimensao.LOCALIZACAO_ESCOLA: (Dimensao.LOCALIZACAO_ESCOLA.value,),
    Dimensao.CODIGO_ESCOLA: (Dimensao.CODIGO_ESCOLA.value,),
    Dimensao.TIPO_ESCOLA: (Dimensao.TIPO_ESCOLA.value,),
    Dimensao.DEP_ADM: (Dimensao.DEP_ADM.value,),
    Dimensao.RENDA: (Dimensao.RENDA.value,),
    Dimensao.COR_RACA: (Dimensao.COR_RACA.value,),
    Dimensao.ESCOLARIDADE_PAI: (Dimensao.ESCOLARIDADE_PAI.value,),
    Dimensao.ESCOLARIDADE_MAE: (Dimensao.ESCOLARIDADE_MAE.value,),
}


class InfoEdicao(BaseModel):
    """Metadados de uma Edicao disponivel na *silver* (Req 5.2).

    ``manifesto_id`` e ``data_carga`` sao anulaveis: quando o Manifesto da
    Edicao esta ausente (ou o ETL nao esta importavel), a Edicao ainda e
    descrita, porem sem linhagem — os dois campos vem como ``None``.
    """

    edicao: int
    manifesto_id: str | None
    data_carga: datetime | None
    capacidade: Capacidade


class _ManifestoExterno(Protocol):
    """Interface *documentada* esperada do Manifesto do ETL (contrato externo).

    Reflete o que a API consome de ``radar_etl.manifesto.Manifesto``: o hash
    SHA-256 da fonte, o ``Last-Modified`` da fonte e o timestamp ISO 8601 da
    carga. O adaptador :class:`_ManifestoInfo` isola a API desta forma exata e
    tolera nomes alternativos do campo de carga (ex.: ``baixado_em``).
    """

    fonte_sha256: str
    fonte_last_modified: str | None
    agora_iso: str


@dataclass(frozen=True)
class _ManifestoInfo:
    """Adaptador interno sobre o Manifesto externo, com a interface documentada.

    Normaliza os tres atributos que a API precisa (``fonte_sha256``,
    ``fonte_last_modified``, ``agora_iso``) e deriva deles o identificador de
    Manifesto e a data de carga usados na Linhagem (Req 5.1).
    """

    fonte_sha256: str | None
    fonte_last_modified: str | None
    agora_iso: str | None

    @classmethod
    def de_manifesto(cls, manifesto: _ManifestoExterno) -> _ManifestoInfo:
        """Constroi o adaptador lendo os atributos do Manifesto externo.

        A leitura e defensiva (``getattr``): alem do ``agora_iso`` documentado,
        aceita ``baixado_em``/``processado_em`` como origem do timestamp de
        carga, cobrindo a forma concreta do Manifesto da Sprint 1.
        """
        carga = (
            getattr(manifesto, "agora_iso", None)
            or getattr(manifesto, "baixado_em", None)
            or getattr(manifesto, "processado_em", None)
        )
        return cls(
            fonte_sha256=getattr(manifesto, "fonte_sha256", None),
            fonte_last_modified=getattr(manifesto, "fonte_last_modified", None),
            agora_iso=carga,
        )

    @property
    def manifesto_id(self) -> str:
        """Identificador de Manifesto: ``fonte_sha256`` + ``@`` + ``last_modified``."""
        return f"{self.fonte_sha256 or ''}@{self.fonte_last_modified or ''}"

    @property
    def data_carga(self) -> datetime | None:
        """Data de carga, parseada de ``agora_iso`` (ISO 8601); ``None`` se ausente/invalida."""
        if not self.agora_iso:
            return None
        try:
            return datetime.fromisoformat(self.agora_iso)
        except ValueError:
            return None


class ContratoCanonico(Protocol):
    """Interface documentada do contrato canonico de uma Edicao (AD-3).

    Reflete o ``ContratoEdicao`` de ``radar_etl.contracts.modelos``: tres
    colecoes de nomes de coluna canonicos. Por AD-3, cada coluna canonica esta
    em **exatamente um** destes conjuntos:

    * ``mapeamento`` — coluna presente na fonte e mapeada para a canonica;
    * ``derivadas`` — coluna computada pelo ETL (ex.: ``regiao`` a partir de
      ``uf_prova``);
    * ``ausentes`` — coluna indisponivel na Edicao (com justificativa textual
      no contrato real).
    """

    mapeamento: Collection[str]
    derivadas: Collection[str]
    ausentes: Collection[str]


def derivar_capacidade_do_contrato(edicao: int, contrato: ContratoCanonico) -> Capacidade:
    """Deriva a :class:`~radar_api.modelos.Capacidade` de uma Edicao do contrato (AD-3).

    Esta e a derivacao **primaria** de capacidade do design (AD-3): pura, sem
    I/O e testavel, dirigida exclusivamente pelo contrato canonico. E o que a
    Property 7 (task 3.3) exercita com contratos sinteticos.

    Regra (*sse*), aplicada sobre ``contrato.mapeamento``/``derivadas``/
    ``ausentes`` tratados como colecoes de nomes de coluna canonicos:

    * Uma :class:`~radar_api.modelos.Dimensao` e **suportada** se, e somente se,
      TODAS as colunas que a sustentam (:data:`SUSTENTACAO_CANONICA`) estao
      *disponiveis* — em ``mapeamento`` ou ``derivadas`` — e NENHUMA esta em
      ``ausentes``.
    * ``possui_notas`` segue a mesma regra sobre as colunas de nota
      (:data:`NOTAS_CANONICAS`).
    * ``perfil_combinavel_com_notas`` e verdadeiro sse ``possui_notas`` **e** ao
      menos uma dimensao de perfil (:data:`DIMENSOES_PERFIL`) e suportada pela
      mesma regra.

    Args:
        edicao: Ano da Edicao (rotula a Capacidade e os erros produzidos).
        contrato: Contrato canonico da Edicao (:class:`ContratoCanonico`).

    Returns:
        A :class:`~radar_api.modelos.Capacidade` derivada do contrato.

    Raises:
        ErroCapacidadeIndeterminada: Contrato **inconsistente** (uma coluna
            necessaria aparece ao mesmo tempo em ``ausentes`` e em
            ``mapeamento``/``derivadas``) ou **incompleto** (uma coluna
            necessaria nao aparece em nenhum dos tres conjuntos). Em ambos os
            casos a capacidade nao pode ser determinada (Req 2).
    """
    mapeamento = {str(col) for col in (getattr(contrato, "mapeamento", None) or ())}
    derivadas = {str(col) for col in (getattr(contrato, "derivadas", None) or ())}
    ausentes = {str(col) for col in (getattr(contrato, "ausentes", None) or ())}

    def _coluna_disponivel(coluna: str) -> bool:
        """True se ``coluna`` esta disponivel; valida a consistencia do contrato.

        Uma coluna esta *disponivel* quando em ``mapeamento``/``derivadas`` e
        *ausente* quando em ``ausentes``. Se ambas (contradicao) ou nenhuma
        (contrato incompleto), a capacidade e indeterminavel (Req 2).
        """
        disponivel = coluna in mapeamento or coluna in derivadas
        ausente = coluna in ausentes
        if disponivel and ausente:
            raise ErroCapacidadeIndeterminada(
                edicao=edicao,
                mensagem=(
                    f"Contrato inconsistente para a edicao {edicao}: a coluna canonica "
                    f"'{coluna}' aparece simultaneamente em 'ausentes' e em "
                    f"'mapeamento'/'derivadas'."
                ),
            )
        if not disponivel and not ausente:
            raise ErroCapacidadeIndeterminada(
                edicao=edicao,
                mensagem=(
                    f"Contrato incompleto para a edicao {edicao}: a coluna canonica "
                    f"'{coluna}' nao aparece em 'mapeamento', 'derivadas' nem 'ausentes'."
                ),
            )
        return disponivel

    def _grupo_disponivel(colunas: tuple[str, ...]) -> bool:
        """True sse TODAS as colunas do grupo estao disponiveis (regra *sse*).

        Avalia todas as colunas (sem *short-circuit*) para que cada uma seja
        checada quanto a consistencia do contrato, mesmo quando uma anterior ja
        tornaria o grupo indisponivel.
        """
        avaliacoes = [_coluna_disponivel(coluna) for coluna in colunas]
        return all(avaliacoes)

    dimensoes_suportadas: set[Dimensao] = {
        dim for dim, colunas in SUSTENTACAO_CANONICA.items() if _grupo_disponivel(colunas)
    }
    possui_notas = _grupo_disponivel(NOTAS_CANONICAS)
    perfil_disponivel = any(dim in dimensoes_suportadas for dim in DIMENSOES_PERFIL)
    perfil_combinavel_com_notas = possui_notas and perfil_disponivel

    # Invariante (Req 9.2): perfil e notas so sao combinaveis quando ha notas E
    # ao menos uma dimensao de perfil disponivel. Em 2024 o perfil foi publicado
    # em arquivo separado, desidentificado e nao unificavel com as notas — logo
    # nenhuma dimensao de perfil e sustentada e esta flag e sempre False: o
    # sistema jamais junta perfil e notas de 2024. A assercao protege a
    # invariante contra regressoes futuras.
    assert not perfil_combinavel_com_notas or (possui_notas and perfil_disponivel), (
        "Violacao da invariante Req 9.2: perfil socioeconomico combinado com notas "
        "sem que ambos estejam disponiveis."
    )

    return Capacidade(
        edicao=edicao,
        dimensoes_suportadas=dimensoes_suportadas,
        possui_notas=possui_notas,
        perfil_combinavel_com_notas=perfil_combinavel_com_notas,
    )


class Catalogo:
    """Descobre Edicoes, le Manifestos e deriva Capacidades sobre a *silver*.

    Construido por injecao de dependencia com a :class:`~radar_api.config.Config`
    do servico, de onde obtem ``silver_root`` (raiz dos Parquet particionados) e
    ``manifestos_root`` (raiz dos Manifestos). As Capacidades derivadas sao
    memoizadas por Edicao.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._cache_capacidade: dict[int, Capacidade] = {}

    @property
    def config(self) -> Config:
        """Configuracao injetada (``silver_root``, ``limiar_agregacao``, etc.).

        Acesso somente-leitura para colaboradores do mesmo pacote (ex.: o
        nucleo analitico) resolverem a raiz da *silver* e o limiar de agregacao
        sem alcancar o estado interno do :class:`Catalogo`.
        """
        return self._config

    # -- Descoberta de edicoes ------------------------------------------------

    def edicoes_disponiveis(self) -> list[int]:
        """Lista, em ordem crescente, as Edicoes presentes na *silver*.

        Varre ``silver_root`` por diretorios ``ano=<inteiro>``. Retorna ``[]``
        de forma graciosa quando a raiz nao existe ou nao contem particoes de
        Edicao (contrato de entrada externo pode estar ausente em runtime).
        """
        raiz = self._config.silver_root
        if not raiz.is_dir():
            return []
        edicoes: list[int] = []
        for filho in raiz.iterdir():
            if not filho.is_dir() or not filho.name.startswith("ano="):
                continue
            try:
                edicoes.append(int(filho.name[len("ano=") :]))
            except ValueError:
                continue
        return sorted(edicoes)

    # -- Manifestos -----------------------------------------------------------

    def manifesto(self, edicao: int) -> _ManifestoInfo:
        """Le o Manifesto de uma Edicao, adaptado para a interface documentada.

        Args:
            edicao: Ano da Edicao.

        Returns:
            :class:`_ManifestoInfo` com ``fonte_sha256``, ``fonte_last_modified``
            e ``agora_iso`` normalizados.

        Raises:
            ErroEdicaoAusente: A Edicao nao existe na *silver*.
            ErroManifestoAusente: ``radar_etl`` inimportavel ou manifesto nao
                encontrado sob ``manifestos_root``.
            ErroManifestoInvalido: Manifesto presente porem ilegivel/malformado.
        """
        if not self._edicao_existe(edicao):
            raise ErroEdicaoAusente(edicao)

        # Import tardio: o ETL e um contrato externo e pode nao estar instalado
        # em runtime; sua ausencia degrada para MANIFESTO_AUSENTE (Req 5).
        try:
            from radar_etl.manifesto import Manifesto
        except ImportError as exc:
            raise ErroManifestoAusente(edicao=edicao) from exc

        for caminho in self._candidatos_manifesto(edicao):
            try:
                bruto = Manifesto.carregar(caminho)
            except Exception as exc:  # manifesto presente porem ilegivel/invalido
                raise ErroManifestoInvalido(edicao=edicao) from exc
            if bruto is not None:
                return _ManifestoInfo.de_manifesto(bruto)

        raise ErroManifestoAusente(edicao=edicao)

    def _manifesto_meta(self, edicao: int) -> tuple[str | None, datetime | None]:
        """Retorna ``(manifesto_id, data_carga)`` de forma graciosa.

        Quando o Manifesto esta ausente (:class:`ErroManifestoAusente`),
        retorna ``(None, None)`` — este e o caminho usado por
        :meth:`info_edicao`, que deve funcionar mesmo sem linhagem.
        """
        try:
            info = self.manifesto(edicao)
        except ErroManifestoAusente:
            return (None, None)
        return (info.manifesto_id, info.data_carga)

    def _candidatos_manifesto(self, edicao: int) -> list[Path]:
        """Caminhos candidatos do arquivo de manifesto da Edicao.

        Convencao da Sprint 1: ``enem_<edicao>.json`` sob ``_manifests/``.
        Considera tanto ``manifestos_root`` apontando direto para a pasta de
        manifestos quanto apontando para uma raiz que a contem.
        """
        raiz = self._config.manifestos_root or self._config.silver_root
        nome = f"enem_{edicao}.json"
        return [raiz / nome, raiz / "_manifests" / nome]

    # -- Capacidades ----------------------------------------------------------

    def capacidade(self, edicao: int) -> Capacidade:
        """Deriva a :class:`~radar_api.modelos.Capacidade` — *contrato primeiro, dados fallback*.

        Ordem de resolucao (AD-3):

        1. **Contrato canonico** (primario): se ``radar_etl.contracts.modelos``
           for importavel, carrega o schema canonico e o contrato da Edicao e
           deriva via :func:`derivar_capacidade_do_contrato` (regra *sse*).
        2. **Dados** (fallback): se o ETL nao for importavel (``ImportError``) ou
           o contrato da Edicao nao puder ser localizado de forma limpa, deriva a
           Capacidade *dos dados* da *silver* (:meth:`_capacidade_dos_dados`).
           Enquanto o ETL nao esta instalado em runtime, este e o caminho ativo.

        Um contrato **presente porem inconsistente** nao cai no fallback: propaga
        :class:`ErroCapacidadeIndeterminada` (o contrato e a fonte-de-verdade e
        esta quebrado). Se contrato **e** dados forem indisponiveis/ilegiveis, o
        resultado tambem e :class:`ErroCapacidadeIndeterminada`. Memoizado por
        Edicao.

        Raises:
            ErroEdicaoAusente: A Edicao nao existe na *silver* (Req 5.4).
            ErroCapacidadeIndeterminada: Contrato inconsistente, ou contrato e
                dados ambos indisponiveis/ilegiveis para a Edicao (Req 2).
        """
        if not self._edicao_existe(edicao):
            raise ErroEdicaoAusente(edicao)
        em_cache = self._cache_capacidade.get(edicao)
        if em_cache is not None:
            return em_cache

        capac = self._capacidade_do_contrato(edicao)
        if capac is None:
            capac = self._capacidade_dos_dados(edicao)
        self._cache_capacidade[edicao] = capac
        return capac

    def edicoes_que_suportam(self, dims: set[Dimensao]) -> list[int]:
        """Edicoes disponiveis cuja Capacidade suporta todas as ``dims`` (Req 2.6).

        Retorna, em ordem crescente, as Edicoes cujas ``dimensoes_suportadas``
        contem ``dims`` (superconjunto). Edicoes cuja Capacidade nao pode ser
        determinada (:class:`ErroCapacidadeIndeterminada`) sao **ignoradas**,
        para que uma Edicao com contrato/dados problematicos nao quebre a
        consulta.

        Usado pelo erro ``RECORTE_INDISPONIVEL`` (Req 2.2) para informar ao
        cliente quais Edicoes suportam um Recorte indisponivel na Edicao pedida.

        Args:
            dims: Conjunto de Dimensoes exigidas (vazio = qualquer Edicao serve).

        Returns:
            Lista crescente de Edicoes que suportam todas as ``dims``.
        """
        suportam: list[int] = []
        for edicao in self.edicoes_disponiveis():  # ja em ordem crescente
            try:
                capac = self.capacidade(edicao)
            except ErroCapacidadeIndeterminada:
                continue  # edicao indeterminavel nao quebra a consulta
            if dims <= capac.dimensoes_suportadas:
                suportam.append(edicao)
        return suportam

    def _capacidade_do_contrato(self, edicao: int) -> Capacidade | None:
        """Tenta a derivacao *primaria* de Capacidade a partir do contrato (AD-3).

        Import *lazy* de ``radar_etl.contracts.modelos`` (contrato de entrada
        externo, pode estar ausente em runtime).

        Returns:
            A Capacidade derivada do contrato, ou ``None`` quando o contrato e
            *indisponivel* — o ETL nao e importavel (``ImportError``) ou o lookup
            do canonico/contrato falha de forma limpa —, sinalizando ao chamador
            para usar o fallback data-driven.

        Raises:
            ErroCapacidadeIndeterminada: O contrato foi carregado, porem e
                inconsistente/incompleto (propagado de
                :func:`derivar_capacidade_do_contrato`).
        """
        try:
            from radar_etl.contracts import modelos as contratos
        except ImportError:
            return None  # ETL ausente em runtime -> fallback data-driven

        try:
            canonico = contratos.carregar_canonico()
            contrato = contratos.carregar_contrato(edicao, canonico)
        except Exception:
            # Lookup do contrato falhou de forma limpa (ex.: contrato inexistente
            # para a Edicao, arquivo ilegivel): cai no fallback data-driven.
            return None
        if contrato is None:
            return None
        # Fora do try: uma inconsistencia do contrato deve *propagar*
        # ErroCapacidadeIndeterminada, nao cair no fallback.
        return derivar_capacidade_do_contrato(edicao, contrato)

    def _capacidade_dos_dados(self, edicao: int) -> Capacidade:
        """Deriva a Capacidade *dos dados* da *silver* (fallback do contrato).

        Uma :class:`~radar_api.modelos.Dimensao` e suportada sse sua coluna
        existe na *silver* e possui ao menos um valor nao nulo na Edicao;
        ``possui_notas`` sse alguma coluna ``nota_*`` tem valor nao nulo; e
        ``perfil_combinavel_com_notas`` sse ``possui_notas`` e ao menos uma
        coluna de perfil tem valor nao nulo. Usado quando o contrato canonico e
        indisponivel (ETL ausente em runtime).

        Raises:
            ErroCapacidadeIndeterminada: O Parquet da Edicao nao pode ser lido.
        """
        contagens, colunas = self._contar_nao_nulos(edicao)
        dimensoes = {
            dim
            for dim in Dimensao
            if dim.value in colunas and contagens.get(dim.value, 0) >= 1
        }
        possui_notas = any(contagens.get(coluna, 0) >= 1 for coluna in NOTAS_CANONICAS)
        perfil_combinavel = possui_notas and any(
            contagens.get(dim.value, 0) >= 1 for dim in DIMENSOES_PERFIL
        )
        return Capacidade(
            edicao=edicao,
            dimensoes_suportadas=dimensoes,
            possui_notas=possui_notas,
            perfil_combinavel_com_notas=perfil_combinavel,
        )

    def info_edicao(self, edicao: int) -> InfoEdicao:
        """Monta :class:`InfoEdicao` (linhagem anulavel + Capacidade) da Edicao.

        Raises:
            ErroEdicaoAusente: A Edicao nao existe na *silver* (Req 5.4).
        """
        if not self._edicao_existe(edicao):
            raise ErroEdicaoAusente(edicao)
        manifesto_id, data_carga = self._manifesto_meta(edicao)
        return InfoEdicao(
            edicao=edicao,
            manifesto_id=manifesto_id,
            data_carga=data_carga,
            capacidade=self.capacidade(edicao),
        )

    # -- Sondagem de dados (DuckDB) ------------------------------------------

    def _contar_nao_nulos(self, edicao: int) -> tuple[dict[str, int], set[str]]:
        """Conta valores nao nulos das colunas candidatas da Edicao via DuckDB.

        Le apenas os Parquet da particao ``ano=<edicao>`` (partition pruning) e
        projeta somente ``count(col)`` das colunas existentes, de modo que
        nenhuma linha individual cruza a fronteira do Motor_de_Consulta.

        Returns:
            Par ``(contagens, colunas)``: ``contagens`` mapeia cada coluna
            candidata existente ao seu numero de valores nao nulos; ``colunas``
            e o conjunto de nomes de coluna presentes no Parquet.

        Raises:
            ErroCapacidadeIndeterminada: O Parquet da Edicao nao pode ser lido.
        """
        padrao = self._glob_parquet(edicao)
        candidatas = [dim.value for dim in Dimensao] + list(NOTAS_CANONICAS)

        conexao = duckdb.connect()
        try:
            colunas = set(
                conexao.sql(
                    f"SELECT * FROM read_parquet('{padrao}', hive_partitioning = 1) LIMIT 0"
                ).columns
            )
            presentes = [coluna for coluna in candidatas if coluna in colunas]
            if not presentes:
                return ({}, colunas)
            projecao = ", ".join(f'count("{coluna}") AS "{coluna}"' for coluna in presentes)
            linha = conexao.sql(
                f"SELECT {projecao} FROM read_parquet('{padrao}', hive_partitioning = 1)"
            ).fetchone()
            if linha is None:
                return ({}, colunas)
            contagens = {
                coluna: int(valor) for coluna, valor in zip(presentes, linha, strict=True)
            }
            return (contagens, colunas)
        except duckdb.Error as exc:
            raise ErroCapacidadeIndeterminada(edicao=edicao) from exc
        finally:
            conexao.close()

    def _glob_parquet(self, edicao: int) -> str:
        """Padrao glob (aspas simples escapadas) dos Parquet da Edicao."""
        padrao = (self._config.silver_root / f"ano={edicao}" / "**" / "*.parquet").as_posix()
        return padrao.replace("'", "''")

    # -- Auxiliares -----------------------------------------------------------

    def _dir_edicao(self, edicao: int) -> Path:
        """Diretorio de particao da Edicao (``silver_root/ano=<edicao>``)."""
        return self._config.silver_root / f"ano={edicao}"

    def _edicao_existe(self, edicao: int) -> bool:
        """Indica se a particao ``ano=<edicao>`` existe na *silver*."""
        return self._dir_edicao(edicao).is_dir()
