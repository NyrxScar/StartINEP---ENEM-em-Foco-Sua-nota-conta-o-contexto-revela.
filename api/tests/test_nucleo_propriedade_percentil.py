"""Teste de propriedade dos limites do Percentil (``radar_api.nucleo.analisar``).

Property 3 (task 5.6) — **Limites do Percentil**: para *qualquer* Edicao, Area,
Nota valida e Recorte que produza uma amostra **suficiente** (>= o
``Limite_Minimo_de_Agregacao`` configurado), o Percentil retornado por
``analisar`` deve estar entre 0 e 100, inclusive (Req 1.7).

A propriedade e verificada de ponta a ponta sobre *fixtures* Parquet minusculas
escritas por :mod:`fixtures_silver` no mesmo layout Hive da *silver* real. Para
cada exemplo geramos de 25 a 80 notas nao nulas na Area — garantindo amostra
suficiente sob o limiar (fixado em 25) —, uma Nota de usuario em ``[0, 1000]`` e
um Recorte **vazio** (que preserva a suficiencia por nao filtrar nenhuma linha).
Assim o resultado nunca e marcado como estatisticamente insuficiente e seu
Percentil deve sempre existir e cair no intervalo fechado ``[0, 100]``.

Cada exemplo cria seu proprio ``tempfile.TemporaryDirectory`` (em vez da fixture
``tmp_path`` do pytest) porque, sob ``@given``, o corpo do teste roda muitas
vezes enquanto uma fixture de escopo de funcao seria compartilhada entre os
exemplos — o diretorio proprio mantem cada exemplo isolado e deterministico.

Os ``@example`` fixam os casos de fronteira: ``nota = 0`` e ``nota = 1000`` (os
extremos do intervalo valido) e Notas abaixo/acima de toda a amostra (que levam
o Percentil a exatamente 0 e 100), exercitando ambos os limites.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.modelos import Area, Recorte, ResultadoAnalise
from radar_api.nucleo import analisar

# Limiar de agregacao fixado no teste (independe de variaveis de ambiente
# RADAR_*): com >= 25 notas nao nulas por exemplo, a amostra e sempre suficiente.
LIMIAR = 25

# Notas validas: finitas, no intervalo 0..1000 inclusive (Req 1.8). Reutilizada
# tanto para a amostra quanto para a Nota do usuario cujo Percentil e calculado.
_NOTAS_VALIDAS = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)

# Amostra crescente (30 notas de 300 a 590) usada nos exemplos de "abaixo/acima
# de toda a amostra": Nota do usuario < 300 -> Percentil 0; Nota > 590 -> 100.
_AMOSTRA_CRESCENTE = [float(300 + i * 10) for i in range(30)]


@settings(max_examples=100, deadline=None)
@given(
    edicao=st.integers(min_value=2000, max_value=2100),
    area=st.sampled_from(list(Area)),
    notas=st.lists(_NOTAS_VALIDAS, min_size=LIMIAR, max_size=80),
    nota_usuario=_NOTAS_VALIDAS,
)
@example(edicao=2023, area=Area.CN, notas=[500.0] * 30, nota_usuario=0.0)
@example(edicao=2023, area=Area.MT, notas=[500.0] * 30, nota_usuario=1000.0)
@example(edicao=2024, area=Area.CH, notas=_AMOSTRA_CRESCENTE, nota_usuario=100.0)
@example(edicao=2025, area=Area.LC, notas=_AMOSTRA_CRESCENTE, nota_usuario=900.0)
def test_limites_do_percentil(
    edicao: int,
    area: Area,
    notas: list[float],
    nota_usuario: float,
) -> None:
    """Feature: radar-enem-analise-api, Property 3: Limites do Percentil

    **Validates: Requirements 1.7**

    Para qualquer Edicao, Area, Nota valida e Recorte que produza amostra
    suficiente, o Percentil retornado por ``analisar`` esta em ``[0, 100]``
    inclusive. A suficiencia e garantida por construcao (>= 25 notas nao nulas
    na Area e Recorte vazio), de modo que o resultado nunca e suprimido e o
    Percentil esta sempre presente e dentro dos limites.
    """
    with tempfile.TemporaryDirectory() as dir_tmp:
        raiz = Path(dir_tmp)
        # Uma linha por nota, apenas com a coluna nota_<area> preenchida.
        linhas = [{f"nota_{area.value}": valor} for valor in notas]
        escrever_silver(raiz, edicao, linhas)

        catalogo = Catalogo(Config(silver_root=raiz, limiar_agregacao=LIMIAR))
        resultado = analisar(catalogo, edicao, area, nota_usuario, Recorte())

    assert isinstance(resultado, ResultadoAnalise)
    # Amostra suficiente por construcao: a guarda de privacidade nao suprime.
    assert resultado.estatisticamente_insuficiente is False
    assert resultado.tamanho_amostral == len(notas)
    # Property 3 (Req 1.7): o Percentil existe e cai no intervalo fechado [0, 100].
    assert resultado.percentil is not None
    assert 0.0 <= resultado.percentil <= 100.0
