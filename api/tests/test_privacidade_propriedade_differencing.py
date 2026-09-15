"""Teste de propriedade da protecao contra *differencing* (``radar_api.privacidade``).

Property 5 (task 4.4) — **Protecao contra differencing**: para *qualquer* par de
Recortes que difira por um unico filtro, se a *celula-diferenca* (as linhas
presentes em um dos Recortes e ausentes no outro) for menor que o limiar, o
sistema deve suprimir ambos os resultados, impedindo que a **subtracao** das
contagens revele a celula pequena e reidentifique o grupo (Req 9.5).

O ataque de *differencing* funciona assim: um observador que veja os agregados
de dois Recortes vizinhos (``R`` e ``R`` mais/menos um filtro) subtrai as
contagens; o resultado e exatamente o tamanho da celula-diferenca. Se essa
celula for pequena (abaixo do ``Limite_Minimo_de_Agregacao``), a subtracao
contorna o k-anonimato. A guarda expoe duas pecas puras verificadas aqui:

* ``proteger_differencing(a, b, limiar)`` — decisao baseada em **contagens**:
  ``True`` (suprimir ambos) sse ``0 < abs(a - b) < limiar``; simetrica em ``a``/``b``.
* ``differ_por_um_filtro(r1, r2)`` — a **precondicao** do ataque: ``True`` sse
  exatamente uma :class:`~radar_api.modelos.Dimensao` diverge entre os Recortes.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes por propriedade).
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from radar_api.modelos import Dimensao, Recorte
from radar_api.privacidade import differ_por_um_filtro, proteger_differencing

# Estrategias reutilizadas: chaves sao Dimensoes; valores sao textos curtos nao
# vazios (o predicado so olha (des)igualdade de valores, o conteudo e irrelevante).
_DIMENSOES = list(Dimensao)
_VALORES = st.text(min_size=1, max_size=6)


# --------------------------------------------------------------------------- #
# Propriedade principal — decisao de supressao baseada em contagens            #
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(
    limiar=st.integers(min_value=1, max_value=200),
    tamanho_a=st.integers(min_value=0, max_value=1000),
    delta=st.integers(min_value=0, max_value=400),
)
@example(limiar=25, tamanho_a=100, delta=0)  # celula vazia -> nao suprime
@example(limiar=25, tamanho_a=100, delta=24)  # celula < limiar -> suprime
@example(limiar=25, tamanho_a=100, delta=25)  # celula == limiar -> nao suprime
@example(limiar=25, tamanho_a=10, delta=400)  # exercita a fixacao de b >= 0
@example(limiar=1, tamanho_a=0, delta=0)  # limiar minimo degenerado
def test_protecao_contra_differencing(limiar: int, tamanho_a: int, delta: int) -> None:
    """Feature: radar-enem-analise-api, Property 5: Proteção contra differencing

    **Validates: Requirements 9.5**

    Para qualquer par de Recortes vizinhos, a supressao por *differencing* ocorre
    exatamente quando a celula-diferenca (``abs(a - b)``, o que a subtracao das
    contagens revelaria) e nao vazia e menor que o limiar. A decisao e simetrica
    na ordem dos Recortes e trata as fronteiras ``limiar - 1`` (suprime) e
    ``limiar`` (nao suprime).
    """
    # Deriva o segundo tamanho a partir de um delta, mantendo ambos >= 0.
    tamanho_b = tamanho_a - delta if tamanho_a - delta >= 0 else tamanho_a + delta
    assert tamanho_a >= 0 and tamanho_b >= 0

    resultado = proteger_differencing(tamanho_a, tamanho_b, limiar)
    # A celula-diferenca e o que a subtracao revelaria; suprime sse 0 < ela < limiar.
    esperado = 0 < abs(tamanho_a - tamanho_b) < limiar

    assert isinstance(resultado, bool)
    assert resultado == esperado

    # Simetria: a decisao independe de qual Recorte e observado primeiro (usa abs).
    assert proteger_differencing(tamanho_a, tamanho_b, limiar) == proteger_differencing(
        tamanho_b, tamanho_a, limiar
    )

    # Fronteira superior: celula-diferenca == limiar e segura sob k-anonimato.
    assert proteger_differencing(tamanho_a, tamanho_a + limiar, limiar) is False
    # Fronteira interna: celula-diferenca == limiar - 1 (nao vazia) deve suprimir.
    if limiar >= 2:
        assert proteger_differencing(tamanho_a, tamanho_a + (limiar - 1), limiar) is True


# --------------------------------------------------------------------------- #
# Precondicao do ataque — differ_por_um_filtro                                 #
# --------------------------------------------------------------------------- #
@st.composite
def _recortes_vizinhos(draw: st.DrawFn) -> tuple[Recorte, Recorte]:
    """Gera um par de Recortes que diferem por EXATAMENTE um filtro.

    Cobre os dois modos de vizinhanca da precondicao de *differencing*:

    * **adicionar** — ``r2`` e ``r1`` acrescido de uma Dimensao ausente em ``r1``
      (a celula-diferenca corresponde a essa nova dimensao);
    * **mudar** — mesmas Dimensoes, com o valor de UMA delas alterado.
    """
    # Base sobre um subconjunto de Dimensoes; deixa >= 1 dimensao livre p/ adicionar.
    base = draw(
        st.dictionaries(
            keys=st.sampled_from(_DIMENSOES),
            values=_VALORES,
            max_size=len(_DIMENSOES) - 1,
        )
    )
    modo = draw(st.sampled_from(("adicionar", "mudar")))
    if modo == "mudar" and base:
        chave = draw(st.sampled_from(sorted(base)))
        novo = draw(_VALORES)
        if novo == base[chave]:  # garante valor efetivamente distinto
            novo = f"{novo}~"
        alterado = dict(base)
        alterado[chave] = novo
        return Recorte(filtros=dict(base)), Recorte(filtros=alterado)
    # 'adicionar' (ou fallback quando base e vazia): acrescenta uma dimensao ausente.
    ausentes = [d for d in _DIMENSOES if d not in base]
    nova_dim = draw(st.sampled_from(ausentes))
    aumentado = dict(base)
    aumentado[nova_dim] = draw(_VALORES)
    return Recorte(filtros=dict(base)), Recorte(filtros=aumentado)


@settings(max_examples=100, deadline=None)
@given(par=_recortes_vizinhos())
def test_differ_por_um_filtro_vizinhos_verdadeiro(par: tuple[Recorte, Recorte]) -> None:
    """Feature: radar-enem-analise-api, Property 5: Proteção contra differencing

    **Validates: Requirements 9.5**

    Precondicao do ataque: dois Recortes que diferem por um unico filtro (por
    adicao de dimensao ou por troca de um valor) sao reconhecidos como vizinhos,
    de forma simetrica.
    """
    r1, r2 = par
    assert differ_por_um_filtro(r1, r2) is True
    assert differ_por_um_filtro(r2, r1) is True


@settings(max_examples=100, deadline=None)
@given(
    filtros=st.dictionaries(
        keys=st.sampled_from(_DIMENSOES),
        values=_VALORES,
        max_size=len(_DIMENSOES),
    )
)
def test_differ_por_um_filtro_identicos_falso(filtros: dict[Dimensao, str]) -> None:
    """Feature: radar-enem-analise-api, Property 5: Proteção contra differencing

    **Validates: Requirements 9.5**

    Recortes identicos nao diferem por um filtro (zero divergencias), logo nao
    caracterizam a vizinhanca que habilita o ataque de *differencing*.
    """
    r1 = Recorte(filtros=dict(filtros))
    r2 = Recorte(filtros=dict(filtros))
    assert differ_por_um_filtro(r1, r2) is False


@st.composite
def _recortes_distantes(draw: st.DrawFn) -> tuple[Recorte, Recorte]:
    """Gera um par de Recortes que divergem em PELO MENOS duas Dimensoes.

    Mantem um nucleo de filtros comuns (identicos nos dois lados) e faz ``n >= 2``
    Dimensoes livres divergirem — cada uma por adicao (presente so em ``r2``) ou
    por valor distinto nas duas pontas.
    """
    # Reserva >= 2 dimensoes livres para garantir duas divergencias.
    comuns = draw(
        st.dictionaries(
            keys=st.sampled_from(_DIMENSOES),
            values=_VALORES,
            max_size=len(_DIMENSOES) - 2,
        )
    )
    livres = [d for d in _DIMENSOES if d not in comuns]
    n = draw(st.integers(min_value=2, max_value=len(livres)))
    divergentes = draw(st.lists(st.sampled_from(livres), min_size=n, max_size=n, unique=True))

    r1 = dict(comuns)
    r2 = dict(comuns)
    for dim in divergentes:
        if draw(st.booleans()):
            # adicao: presente apenas em r2 -> diverge (r1 nao possui a Dimensao).
            r2[dim] = draw(_VALORES)
        else:
            # valores distintos nas duas pontas -> diverge.
            va = draw(_VALORES)
            vb = draw(_VALORES)
            if vb == va:
                vb = f"{vb}~"
            r1[dim] = va
            r2[dim] = vb
    return Recorte(filtros=r1), Recorte(filtros=r2)


@settings(max_examples=100, deadline=None)
@given(par=_recortes_distantes())
def test_differ_por_um_filtro_distantes_falso(par: tuple[Recorte, Recorte]) -> None:
    """Feature: radar-enem-analise-api, Property 5: Proteção contra differencing

    **Validates: Requirements 9.5**

    Recortes que divergem em duas ou mais Dimensoes nao sao vizinhos por um unico
    filtro; a protecao por *differencing* nao se aplica a esse par.
    """
    r1, r2 = par
    assert differ_por_um_filtro(r1, r2) is False
    assert differ_por_um_filtro(r2, r1) is False
