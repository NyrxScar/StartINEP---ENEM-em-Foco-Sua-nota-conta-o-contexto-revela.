"""Guarda de privacidade do servico Radar ENEM (k-anonimato / agregacao).

Centraliza a aplicacao do ``Limite_Minimo_de_Agregacao`` (k-anonimato) a todo
``ResultadoAnalise`` antes que ele cruze a fronteira do nucleo analitico (AD-4).
Isso honra a desidentificacao do INEP e o RIPD (Req 9): agregados com contagem
inferior ao limiar sao suprimidos para impedir a reidentificacao por recorte
pequeno.

Este modulo hospeda ``aplicar_limiar`` (limiar minimo de agregacao — Req 1.6 /
9.3, Property 4) e ``proteger_differencing`` (protecao contra *differencing* —
Req 9.5, Property 5), acompanhado do predicado auxiliar ``differ_por_um_filtro``;
o modulo e o ponto unico e auditavel dessas politicas.
"""

from __future__ import annotations

from radar_api.modelos import Recorte, ResultadoAnalise


def aplicar_limiar(res: ResultadoAnalise, limiar: int) -> ResultadoAnalise:
    """Aplica o limiar minimo de agregacao (k-anonimato) a um resultado.

    Se o ``tamanho_amostral`` do resultado for menor que ``limiar`` — ou ja
    estiver ausente (``None``), sinal de que a entrada ja foi suprimida —, o
    resultado retornado e marcado como ``estatisticamente_insuficiente`` e todos
    os campos sensiveis (``distribuicao``, ``percentil`` e o proprio
    ``tamanho_amostral`` exposto) sao anulados, sem expor qualquer detalhe da
    Distribuicao (Req 1.6 / 9.3). Caso contrario (amostra ``>= limiar``), o
    resultado e retornado com ``estatisticamente_insuficiente=False`` e a
    Distribuicao / percentil / tamanho amostral intactos.

    A entrada nunca e mutada in loco: retorna-se sempre uma nova instancia (via
    ``model_copy``), preservando ``edicao``, ``area``, ``capacidade`` e
    ``linhagem``.

    :param res: resultado analitico a filtrar pela guarda de privacidade.
    :param limiar: ``Limite_Minimo_de_Agregacao`` configurado, fornecido pelo
        chamador (este modulo nao le configuracao).
    :returns: um novo ``ResultadoAnalise`` — suprimido ou intacto conforme o
        tamanho amostral.
    """
    suprimir = res.tamanho_amostral is None or res.tamanho_amostral < limiar
    if suprimir:
        return res.model_copy(
            update={
                "estatisticamente_insuficiente": True,
                "distribuicao": None,
                "percentil": None,
                "tamanho_amostral": None,
            }
        )
    return res.model_copy(update={"estatisticamente_insuficiente": False})


def proteger_differencing(tamanho_a: int, tamanho_b: int, limiar: int) -> bool:
    """Decide se dois Recortes vizinhos devem ser suprimidos por *differencing*.

    Protecao contra o ataque classico de *differencing* (Req 9.5 / Property 5):
    quando dois Recortes diferem por um unico filtro (ver
    :func:`differ_por_um_filtro`), a *celula-diferenca* — o conjunto de linhas
    presentes em apenas um dos Recortes — tem tamanho ``abs(tamanho_a -
    tamanho_b)``. Se um atacante observar ambos os agregados, subtrair as
    contagens revela exatamente essa celula; caso ela seja pequena (abaixo do
    limiar), a subtracao permitiria reidentificar o pequeno grupo. Para impedir,
    ``True`` significa "suprimir AMBOS os resultados".

    Semantica (funcao pura, baseada em contagens e simetrica na ordem dos
    argumentos, pois usa ``abs``):

    * ``abs(tamanho_a - tamanho_b) == 0`` -> ``False``: populacoes de mesmo
      tamanho; a subtracao nao revela nenhuma celula, nada a suprimir.
    * ``0 < abs(tamanho_a - tamanho_b) < limiar`` -> ``True``: a celula-diferenca
      e nao vazia e menor que o limiar; ambos os resultados devem ser suprimidos.
    * ``abs(tamanho_a - tamanho_b) >= limiar`` -> ``False``: a celula-diferenca e
      grande o suficiente (``>= limiar``), portanto segura sob k-anonimato.

    A decisao e deliberadamente baseada apenas em contagens (sem ``Recorte`` nem
    I/O): o chamador valida a precondicao de "diferem por um unico filtro" (por
    exemplo via :func:`differ_por_um_filtro`) e fornece ``limiar`` — este modulo
    nao le configuracao.

    :param tamanho_a: tamanho amostral do primeiro Recorte (contagem de linhas).
    :param tamanho_b: tamanho amostral do segundo Recorte (contagem de linhas).
    :param limiar: ``Limite_Minimo_de_Agregacao`` configurado, fornecido pelo
        chamador.
    :returns: ``True`` se ambos os resultados devem ser suprimidos (celula-diferenca
        nao vazia e abaixo do limiar); ``False`` caso contrario.
    """
    celula_diferenca = abs(tamanho_a - tamanho_b)
    return 0 < celula_diferenca < limiar


def differ_por_um_filtro(r1: Recorte, r2: Recorte) -> bool:
    """Indica se dois Recortes diferem por exatamente um filtro (precondicao P5).

    Predicado auxiliar que valida a precondicao do ataque de *differencing*
    (Req 9.5): os dois Recortes sao "vizinhos" quando existe **exatamente uma**
    :class:`~radar_api.modelos.Dimensao` em que os filtros divergem. Isso cobre
    tanto o caso "adicionar um filtro" (``r2`` e ``r1`` mais uma dimensao) quanto
    o caso "irmaos" (mesmas dimensoes, um unico valor diferente). A ausencia de
    filtro para uma dimensao e tratada como ``None`` e comparada como tal.

    :param r1: primeiro Recorte.
    :param r2: segundo Recorte.
    :returns: ``True`` se exatamente uma dimensao diverge entre os dois Recortes;
        ``False`` se forem identicos ou diferirem em duas ou mais dimensoes.
    """
    dimensoes = set(r1.filtros) | set(r2.filtros)
    divergencias = sum(
        1 for dim in dimensoes if r1.filtros.get(dim) != r2.filtros.get(dim)
    )
    return divergencias == 1
