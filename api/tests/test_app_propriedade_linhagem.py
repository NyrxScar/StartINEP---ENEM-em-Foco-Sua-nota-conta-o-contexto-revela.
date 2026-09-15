"""Teste de propriedade da presenca da Linhagem na resposta HTTP de analise.

Property 10 (task 7.4) — **Toda resposta carrega Linhagem**: para *qualquer*
resposta de analise bem-sucedida, a Linhagem deve listar cada Edicao utilizada
com o identificador de Manifesto correspondente (Req 5.1).

A propriedade e exercitada na **borda HTTP** (``POST /v1/analise`` via
:class:`~fastapi.testclient.TestClient`), sobre *fixtures* Parquet minusculas
escritas por :mod:`fixtures_silver` no mesmo layout Hive da *silver* real e uma
app montada com ``criar_app(Config(silver_root=..., limiar_agregacao=...))`` —
mesma fiacao do smoke test :mod:`test_app_analise`.

O gerador cruza **deliberadamente o limiar** de agregacao: o tamanho da amostra
vai de 1 a ``2 * LIMIAR``, cobrindo os dois regimes de privacidade —

* amostra suficiente (``>= LIMIAR``): resultado populado (distribuicao,
  percentil, tamanho amostral);
* amostra insuficiente (``< LIMIAR``): resultado suprimido
  (``estatisticamente_insuficiente = True``, campos sensiveis nulos — Req
  1.6/9.3).

A asserçao central e que a ``linhagem`` esta presente e lista a Edicao **nos
dois regimes**: a supressao por privacidade nunca pode remover a auditabilidade
da resposta. Um resultado suprimido continua sendo uma resposta bem-sucedida
(200) e, portanto, precisa dizer de quais Edicoes/Manifestos ele saiu.

Nota sobre os *valores* de ``manifestos``/``datas_carga``: neste ambiente o
pacote ``radar_etl`` nao e importavel e nao existe arquivo de manifesto para as
Edicoes das *fixtures*, de modo que o catalogo degrada para
``manifesto_id = None`` / ``data_carga = None`` (Req 5.4, sem levantar erro). A
Req 5.1 exige **identificar as Edicoes e o Manifesto de cada Edicao usada**;
com o Manifesto ausente, a representacao honesta e degradada e a *chave da
Edicao presente com valor nulo* — nunca a omissao da Edicao. E exatamente isso
que o teste fixa: as chaves existem sempre; os valores podem ser nulos.

No corpo JSON as chaves de ``manifestos``/``datas_carga`` sao **strings** (JSON
nao possui chaves inteiras), por isso a busca usa ``str(edicao)``.

Cada exemplo cria seu proprio ``tempfile.TemporaryDirectory`` (em vez da fixture
``tmp_path`` do pytest) porque, sob ``@given``, o corpo do teste roda muitas
vezes enquanto uma fixture de escopo de funcao seria compartilhada entre os
exemplos — o diretorio proprio mantem cada exemplo isolado e deterministico.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.config import Config
from radar_api.modelos import Area

# Limiar de agregacao fixado no teste (independe de variaveis RADAR_* do
# ambiente); o gerador de ``tamanho`` cruza este valor nos dois sentidos.
LIMIAR = 25

# Notas validas: finitas, no intervalo 0..1000 inclusive (Req 1.8).
_NOTAS_VALIDAS = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)


@settings(max_examples=100, deadline=None)
@given(
    edicao=st.integers(min_value=2000, max_value=2100),
    area=st.sampled_from(list(Area)),
    nota_usuario=_NOTAS_VALIDAS,
    tamanho=st.integers(min_value=1, max_value=2 * LIMIAR),
)
# Fronteiras dos dois regimes de privacidade em torno do limiar.
@example(edicao=2023, area=Area.CN, nota_usuario=500.0, tamanho=LIMIAR)  # suficiente (=)
@example(edicao=2023, area=Area.MT, nota_usuario=500.0, tamanho=LIMIAR - 1)  # suprimido
@example(edicao=2024, area=Area.CH, nota_usuario=0.0, tamanho=1)  # amostra minima
@example(edicao=2099, area=Area.REDACAO, nota_usuario=1000.0, tamanho=2 * LIMIAR)
def test_toda_resposta_carrega_linhagem(
    edicao: int,
    area: Area,
    nota_usuario: float,
    tamanho: int,
) -> None:
    """Feature: radar-enem-analise-api, Property 10: Toda resposta carrega Linhagem

    **Validates: Requirements 5.1**

    Para qualquer resposta de analise bem-sucedida — com amostra suficiente ou
    suprimida pela guarda de privacidade — o corpo traz ``linhagem`` listando a
    Edicao utilizada e uma entrada de Manifesto/data de carga para ela.
    """
    with tempfile.TemporaryDirectory() as dir_tmp:
        raiz = Path(dir_tmp)
        # ``tamanho`` linhas com nota nao nula na Area consultada; o valor cresce
        # de forma deterministica dentro de 0..1000.
        linhas = [
            {f"nota_{area.value}": float(i * 1000 // max(tamanho, 1))} for i in range(tamanho)
        ]
        escrever_silver(raiz, edicao, linhas)

        app = criar_app(Config(silver_root=raiz, limiar_agregacao=LIMIAR))
        with TestClient(app) as cliente:
            resposta = cliente.post(
                "/v1/analise",
                json={"edicao": edicao, "area": area.value, "nota": nota_usuario},
            )

    assert resposta.status_code == 200
    corpo = resposta.json()

    # Os dois regimes de privacidade sao efetivamente exercitados pelo gerador.
    suprimido = tamanho < LIMIAR
    assert corpo["estatisticamente_insuficiente"] is suprimido
    if suprimido:
        # Req 1.6/9.3: campos sensiveis anulados quando a amostra e insuficiente.
        assert corpo["distribuicao"] is None
        assert corpo["percentil"] is None
        assert corpo["tamanho_amostral"] is None
    else:
        assert corpo["tamanho_amostral"] == tamanho
        assert corpo["percentil"] is not None

    # Property 10 (Req 5.1): a Linhagem acompanha a resposta em AMBOS os regimes —
    # a supressao por privacidade nunca remove a auditabilidade.
    linhagem = corpo["linhagem"]
    assert isinstance(linhagem, dict)
    assert {"edicoes", "manifestos", "datas_carga"} <= set(linhagem)

    # A Edicao efetivamente utilizada esta listada.
    assert linhagem["edicoes"] == [edicao]

    # Chave presente para a Edicao usada em manifestos e datas de carga. O valor
    # e ``None`` neste ambiente (``radar_etl`` inimportavel e nenhum arquivo de
    # manifesto nas *fixtures*): Req 5.1 pede identificar as Edicoes/Manifestos,
    # logo a chave presente com valor nulo e a representacao degradada honesta —
    # a Edicao jamais desaparece da Linhagem.
    chave = str(edicao)  # chaves JSON sao strings, mesmo com Edicao inteira
    assert chave in linhagem["manifestos"]
    assert chave in linhagem["datas_carga"]

    # Consistencia interna: a Edicao da Linhagem e a mesma do resultado e da
    # Capacidade embutida (Req 2.5 + 5.1 apontam para a mesma Edicao).
    assert corpo["edicao"] == edicao
    assert corpo["capacidade"]["edicao"] == edicao
