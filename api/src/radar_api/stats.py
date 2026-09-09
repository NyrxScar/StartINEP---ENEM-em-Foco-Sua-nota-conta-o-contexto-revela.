"""Nucleo estatistico do Radar ENEM.

Funcoes puras: recebem contagens ja apuradas e devolvem numero. Nenhum acesso a dados
aqui -- e o que permite validar a matematica contra scipy sem tocar em 13 milhoes de
linhas.
"""

from __future__ import annotations


def percentil(n_menores: int, n_iguais: int, n_total: int) -> float:
    """Percentil de posto medio (mid-rank), em porcentagem.

        percentil(x) = (N_menores + 0,5 * N_iguais) / N * 100

    O termo 0,5 * N_iguais nao e detalhe: as notas do ENEM sao discretas e produzem
    muitos empates. Sem a correcao, um bloco inteiro de empatados iria para um dos
    lados e o percentil ficaria sistematicamente enviesado.

    E a mesma definicao de `scipy.stats.percentileofscore(kind='mean')`, contra a qual
    os testes comparam. NAO e a mesma coisa que `PERCENT_RANK()` do SQL, que calcula
    (rank - 1) / (N - 1), sem correcao de empates e forcando minimo 0 e maximo 1.
    """
    if n_total <= 0:
        raise ValueError("Recorte vazio: nao ha populacao para calcular percentil.")
    return (n_menores + 0.5 * n_iguais) / n_total * 100


def zscore(x: float, media: float, desvio: float) -> float | None:
    """Distancia ate a media do recorte, em desvios-padrao.

    Devolve None quando o desvio e zero -- recorte em que todo mundo tirou a mesma
    nota nao tem escala para medir distancia.

    Metrica SECUNDARIA por decisao de projeto. As notas do ENEM vem de TRI e nao sao
    normais, entao este valor nao deve ser convertido em percentil pela tabela da
    normal padrao. Para posicionamento relativo use `percentil`, que e calculado sobre
    a distribuicao empirica real.
    """
    if desvio == 0:
        return None
    return (x - media) / desvio
