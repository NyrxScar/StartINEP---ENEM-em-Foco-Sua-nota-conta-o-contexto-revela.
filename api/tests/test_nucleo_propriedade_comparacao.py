# A etiqueta obrigatoria da propriedade (primeira linha do docstring do teste)
# precisa casar *exatamente* com o texto do design — "Feature:
# radar-enem-analise-api, Property 11: Comparação inclui apenas edições que
# suportam o Recorte" tem 101 caracteres, que somados ao recuo e as aspas passam
# do limite de 100 colunas e nao podem ser quebrados sem alterar a etiqueta. E501
# e desligado neste arquivo por isso; nenhuma outra linha aqui excede o limite.
# ruff: noqa: E501
"""Teste de propriedade da comparacao entre Edicoes (``radar_api.nucleo.comparar``).

Property 11 (task 8.3) — **Comparacao inclui apenas edicoes que suportam o
Recorte**: para *qualquer* conjunto de Edicoes solicitadas, o
:class:`~radar_api.modelos.ResultadoComparacao` deve conter resultados
**exatamente** para as Edicoes que suportam o Recorte e a Area pedidos, cada um
rotulado pela sua Edicao, e **toda** Edicao excluida deve aparecer em
``omissoes`` com um motivo legivel por maquina — nunca um descarte silencioso
(Req 3.1, 3.2, 3.4). Quando *nenhuma* Edicao e elegivel, a comparacao nao e um
resultado valido e :class:`~radar_api.erros.ErroComparacaoSemEdicoesElegiveis` e
levantado (Req 3.3).

Complementa os testes *exemplo* de ``test_nucleo_comparar.py`` (task 8.1): la
cada ramo de omissao e verificado individualmente com fixtures fixas; aqui a
*particao* solicitadas = resultados ⊎ omissoes e a igualdade com o conjunto
elegivel esperado sao verificadas sobre universos gerados.

Montagem dos exemplos:

* De 2 a 4 Edicoes candidatas (anos do :data:`_POOL_EDICOES` sao meros rotulos:
  a Capacidade e derivada **dos dados** pelo :class:`~radar_api.catalogo.Catalogo`,
  nao do ano). Cada candidata recebe tres flags — se **existe** na *silver*, se
  tem **notas** na Area pedida e se tem a **dimensao** do Recorte preenchida —
  mais uma contagem pequena de linhas (3 a 6, para manter o teste rapido).
* As Edicoes existentes sao escritas por :func:`fixtures_silver.escrever_silver_fixture`
  no layout Hive real. Coluna omitida => ``NULL``, e a regra data-driven do
  catalogo (dimensao suportada *sse* a coluna tem >= 1 valor nao nulo;
  ``possui_notas`` *sse* alguma ``nota_*`` e nao nula) transforma essas flags em
  Capacidades distintas por Edicao.
* O Recorte e **vazio** ou filtra **uma** dimensao *nao* de perfil
  (``tipo_escola``/``dependencia_adm_escola``). A restricao e deliberada: uma
  dimensao de perfil poderia disparar ``PERFIL_NOTA_NAO_COMBINAVEL`` em vez de
  ``RECORTE_INDISPONIVEL``, tornando o codigo esperado ambiguo — a elegibilidade
  (o foco de P11) e identica nos dois casos, mas o oraculo fica mais nitido.
* As Edicoes sao solicitadas em ordem *decrescente* e, as vezes, com uma
  duplicata, para exercer a deduplicacao e a emissao em ordem crescente.

O conjunto elegivel esperado e recalculado **independentemente em Python** a
partir das flags geradas (existe **e** tem notas **e**, havendo Recorte, suporta
a dimensao), sem reusar nada do caminho de ``comparar``.

Usa-se ``limiar=0`` de proposito: assim a guarda de privacidade nao suprime as
amostras minusculas das fixtures e os resultados permanecem observaveis
(``tamanho_amostral``/``percentil`` concretos).

Cada TemporaryDirectory e criado *dentro* do corpo do teste (nunca a fixture
``tmp_path`` do pytest junto de ``@given``, que seria compartilhada entre os
exemplos) e removido ao fim do ``with``.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver_fixture
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.erros import ErroComparacaoSemEdicoesElegiveis
from radar_api.modelos import Area, Dimensao, Recorte
from radar_api.nucleo import comparar

# Anos candidatos. Sao apenas rotulos: a Capacidade vem dos dados escritos, nao
# do ano — por isso nao se usam 2023/2024/2025 (evita sugerir as capacidades
# reais dessas Edicoes).
_POOL_EDICOES: tuple[int, ...] = (2021, 2022, 2023, 2024)

# UF unica: esta propriedade nao olha particionamento por UF.
_UF = "SP"

# Dimensoes *nao* de perfil (ver docstring): o unico motivo possivel de omissao
# por recorte aqui e ``RECORTE_INDISPONIVEL``.
_DIMENSOES_NAO_PERFIL: tuple[Dimensao, ...] = (Dimensao.TIPO_ESCOLA, Dimensao.DEP_ADM)

# Dominio pequeno das colunas TINYINT de dimensao; o filtro do Recorte usa o
# mesmo valor como texto (o SQL compara ``CAST(col AS VARCHAR) = ?``).
_VALORES_DIM: tuple[int, ...] = (1, 2)

# Codigos legiveis por maquina admissiveis para uma omissao (Req 3.2).
_CODIGOS_OMISSAO: frozenset[str] = frozenset(
    {
        "EDICAO_AUSENTE",
        "EDICAO_SEM_NOTAS",
        "RECORTE_INDISPONIVEL",
        "PERFIL_NOTA_NAO_COMBINAVEL",
        "CAPACIDADE_INDETERMINADA",
    }
)

# Especificacao bruta de uma Edicao candidata:
# (existe, tem_notas, tem_dimensao, n_linhas).
_EspecEdicao = tuple[bool, bool, bool, int]

_ESTRATEGIA_EDICAO = st.tuples(
    st.booleans(),  # existe na silver
    st.booleans(),  # tem nota na Area pedida
    st.booleans(),  # tem a dimensao do Recorte preenchida
    st.integers(min_value=3, max_value=6),  # linhas (pequeno = rapido)
)


def _linhas_da_edicao(
    especificacao: _EspecEdicao,
    area: Area,
    dimensao: Dimensao,
    valor_dim: int,
) -> list[dict[str, Any]]:
    """Monta as linhas de fixture de uma Edicao a partir da sua especificacao.

    A nota da Area so e escrita quando ``tem_notas`` (senao a coluna e omitida =>
    ``NULL`` => ``possui_notas`` falso); a coluna da ``dimensao`` so e escrita
    quando ``tem_dimensao`` (senao a dimensao nao e suportada). Todas as linhas
    recebem o *mesmo* ``valor_dim``, de modo que o filtro do Recorte case com
    todas elas e o ``tamanho_amostral`` de uma Edicao elegivel seja exatamente o
    seu numero de linhas. Uma linha sem nota e sem dimensao ainda e uma linha
    valida (a fixture preenche ``regiao`` a partir da UF).
    """
    _, tem_notas, tem_dimensao, n_linhas = especificacao
    linhas: list[dict[str, Any]] = []
    for i in range(n_linhas):
        linha: dict[str, Any] = {}
        if tem_notas:
            linha[f"nota_{area.value}"] = float(400 + 10 * i)
        if tem_dimensao:
            linha[dimensao.value] = valor_dim
        linhas.append(linha)
    return linhas


def _eh_elegivel(especificacao: _EspecEdicao, *, com_recorte: bool) -> bool:
    """Oraculo independente de elegibilidade de uma Edicao (Req 3.1/3.2).

    Reimplementa em Python puro a regra que ``comparar`` deve seguir: a Edicao
    entra na comparacao *sse* existe na *silver*, possui notas (na Area pedida) e
    — havendo Recorte — suporta a dimensao filtrada.
    """
    existe, tem_notas, tem_dimensao, _ = especificacao
    return existe and tem_notas and (not com_recorte or tem_dimensao)


# Universos fixos dos ``@example``.
_TODAS_ELEGIVEIS: list[_EspecEdicao] = [(True, True, True, 3), (True, True, True, 4)]
_MISTO: list[_EspecEdicao] = [
    (True, True, True, 3),  # elegivel
    (True, True, False, 3),  # sem a dimensao -> RECORTE_INDISPONIVEL
    (True, False, True, 3),  # sem notas -> EDICAO_SEM_NOTAS
    (False, False, False, 3),  # inexistente -> EDICAO_AUSENTE
]
_NENHUMA_ELEGIVEL: list[_EspecEdicao] = [(False, True, True, 3), (True, False, False, 4)]


@settings(max_examples=100, deadline=None)
@given(
    especificacoes=st.lists(_ESTRATEGIA_EDICAO, min_size=2, max_size=4),
    area=st.sampled_from(list(Area)),
    nota=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    dimensao=st.sampled_from(_DIMENSOES_NAO_PERFIL),
    valor_dim=st.sampled_from(_VALORES_DIM),
    com_recorte=st.booleans(),
    duplicar=st.booleans(),
)
# Todas elegiveis, Recorte vazio: nenhuma omissao.
@example(
    especificacoes=_TODAS_ELEGIVEIS,
    area=Area.CN,
    nota=450.0,
    dimensao=Dimensao.TIPO_ESCOLA,
    valor_dim=1,
    com_recorte=False,
    duplicar=True,
)
# Um representante de cada motivo de omissao, sob Recorte.
@example(
    especificacoes=_MISTO,
    area=Area.MT,
    nota=700.0,
    dimensao=Dimensao.TIPO_ESCOLA,
    valor_dim=2,
    com_recorte=True,
    duplicar=False,
)
# Nenhuma elegivel: comparacao rejeitada (Req 3.3).
@example(
    especificacoes=_NENHUMA_ELEGIVEL,
    area=Area.REDACAO,
    nota=0.0,
    dimensao=Dimensao.DEP_ADM,
    valor_dim=1,
    com_recorte=True,
    duplicar=False,
)
def test_comparacao_inclui_apenas_edicoes_que_suportam_o_recorte(
    especificacoes: list[_EspecEdicao],
    area: Area,
    nota: float,
    dimensao: Dimensao,
    valor_dim: int,
    com_recorte: bool,
    duplicar: bool,
) -> None:
    """Feature: radar-enem-analise-api, Property 11: Comparação inclui apenas edições que suportam o Recorte

    **Validates: Requirements 3.1, 3.2, 3.3**

    Para qualquer conjunto de Edicoes solicitadas, ``comparar`` devolve
    resultados exatamente para as Edicoes que suportam o Recorte e a Area
    (rotulados pela Edicao, em ordem crescente) e registra **todas** as demais em
    ``omissoes`` com um codigo legivel por maquina: solicitadas = resultados ⊎
    omissoes, sem intersecao e sem descarte silencioso. Quando nenhuma Edicao e
    elegivel, a comparacao e rejeitada com
    ``COMPARACAO_SEM_EDICOES_ELEGIVEIS``.
    """
    edicoes = _POOL_EDICOES[: len(especificacoes)]
    por_edicao = dict(zip(edicoes, especificacoes, strict=True))
    recorte = Recorte(filtros={dimensao: str(valor_dim)}) if com_recorte else Recorte()

    # Somente as Edicoes marcadas como existentes sao escritas na *silver*.
    particoes = {
        (edicao, _UF): _linhas_da_edicao(espec, area, dimensao, valor_dim)
        for edicao, espec in por_edicao.items()
        if espec[0]
    }

    # Oraculo: conjunto elegivel calculado independentemente das flags geradas.
    esperadas = {
        edicao
        for edicao, espec in por_edicao.items()
        if _eh_elegivel(espec, com_recorte=com_recorte)
    }

    # Ordem decrescente (+ duplicata opcional) para exercer dedup/ordenacao.
    solicitadas = [*reversed(edicoes), *([edicoes[0]] if duplicar else [])]
    solicitadas_unicas = set(solicitadas)

    with tempfile.TemporaryDirectory() as diretorio:
        raiz = Path(diretorio)
        escrever_silver_fixture(raiz, particoes)
        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=0))

        if not esperadas:
            # Req 3.3: comparacao sem nenhuma Edicao elegivel e rejeitada.
            with pytest.raises(ErroComparacaoSemEdicoesElegiveis) as exc:
                comparar(catalogo, solicitadas, area, nota, recorte, limiar=0)
            assert exc.value.codigo == "COMPARACAO_SEM_EDICOES_ELEGIVEIS"
            return

        resultado = comparar(catalogo, solicitadas, area, nota, recorte, limiar=0)

    edicoes_resultado = [r.edicao for r in resultado.resultados]
    edicoes_omitidas = [o.edicao for o in resultado.omissoes]

    # Particao (nada desaparece em silencio): resultados ⊎ omissoes == solicitadas.
    assert set(edicoes_resultado) | set(edicoes_omitidas) == solicitadas_unicas
    assert not set(edicoes_resultado) & set(edicoes_omitidas)
    # Uma entrada por Edicao (duplicatas do pedido nao se propagam).
    assert len(edicoes_resultado) == len(set(edicoes_resultado))
    assert len(edicoes_omitidas) == len(set(edicoes_omitidas))

    # Req 3.1: resultados exatamente para as Edicoes elegiveis.
    assert set(edicoes_resultado) == esperadas
    # Req 3.4 + determinismo: rotulados por Edicao, em ordem crescente.
    assert edicoes_resultado == sorted(esperadas)

    # Req 3.2: toda omissao carrega um motivo legivel por maquina nao vazio.
    for omissao in resultado.omissoes:
        assert omissao.codigo
        assert omissao.codigo in _CODIGOS_OMISSAO

    # Nao-vacuidade: com limiar=0 os resultados sao observaveis e coerentes com
    # as linhas escritas (todas casam o filtro, quando ha filtro).
    for analise in resultado.resultados:
        assert analise.edicao in solicitadas_unicas
        assert analise.area == area
        assert analise.capacidade.edicao == analise.edicao
        assert analise.tamanho_amostral == por_edicao[analise.edicao][3]
        assert analise.percentil is not None
        assert 0.0 <= analise.percentil <= 100.0
