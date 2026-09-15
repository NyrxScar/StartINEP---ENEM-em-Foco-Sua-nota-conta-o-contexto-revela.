"""Smoke test de desempenho do Radar ENEM (Req 6.3 / task 13.4).

Este modulo mede a latencia de uma analise **de recorte unico** contra a
*silver* **real** (``data/silver``, ~13,1 M linhas em 81 Parquet) e verifica que
o *partition pruning* que sustenta essa latencia (Req 6.2) continua valendo.

Natureza do teste — *smoke*, nao *benchmark*:

* Os limites sao **generosos** de proposito. O alvo do Req 6.3 e ``<= 3 s`` para
  uma analise de recorte unico no ambiente de referencia documentado; e esse o
  numero afirmado aqui, e nao um limite apertado em torno da medicao. O objetivo
  e pegar uma regressao **catastrofica** (ex.: alguem remove o pruning e a
  consulta passa a ler a *silver* inteira, ficando ordens de magnitude mais
  lenta), nao falhar porque a maquina ficou ocupada por um instante.
* Cada medicao faz uma chamada de **aquecimento** antes de cronometrar, para nao
  medir custos de primeira-vez (import, abertura dos metadados Parquet, cache de
  pagina do sistema de arquivos). Os tempos frio e quentes sao ambos reportados.
* A guarda **deterministica** (que nao depende de relogio de parede) e a
  contagem de arquivos Parquet lidos: um recorte com ``uf_prova`` deve ler
  estritamente **menos** arquivos que o mesmo recorte sem ``uf_prova``. Se o
  pruning por UF desaparecer, as duas contagens se igualam e o teste falha —
  independentemente de a maquina estar rapida ou lenta.

Marcacao e ambiente:

* Todos os testes levam ``@pytest.mark.desempenho`` (marcador registrado em
  ``api/pyproject.toml``), para permitir ``-m desempenho`` / ``-m 'not
  desempenho'``.
* Todos sao **pulados** quando ``data/silver/ano=2023`` nao existe: medir
  desempenho sobre *fixtures* minusculas nao diria nada, e a suite precisa
  continuar verde num ambiente sem os dados.

Os numeros medidos sao impressos (visiveis com ``-s``) **e** embutidos nas
mensagens de assercao, e a secao 8.3 de ``docs/implantacao.md`` registra a
medicao com o contexto de maquina correspondente.
"""

from __future__ import annotations

import os
import platform
import re
import statistics
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient

from radar_api.app import criar_app
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.consulta import construir_consulta_agregada
from radar_api.modelos import Area, Dimensao, Recorte
from radar_api.nucleo import analisar

# --------------------------------------------------------------------------- #
# Guarda de dados: api/tests/test_desempenho.py -> parents[2] == raiz do repo  #
# --------------------------------------------------------------------------- #
_RAIZ_REPO = Path(__file__).resolve().parents[2]
_SILVER_REAL = _RAIZ_REPO / "data" / "silver"

_requer_silver_real = pytest.mark.skipif(
    not (_SILVER_REAL / "ano=2023").is_dir(),
    reason=(
        f"silver real ausente em {_SILVER_REAL / 'ano=2023'}; "
        "smoke de desempenho pulado (nada a medir sobre fixtures minusculas)"
    ),
)

pytestmark = [pytest.mark.desempenho, _requer_silver_real]

# --------------------------------------------------------------------------- #
# Cenario medido                                                              #
# --------------------------------------------------------------------------- #
# 2023 e a Edicao completa (notas + perfil na mesma linha) e a maior superficie
# de recorte; CN/550 e um pedido tipico do produto.
EDICAO = 2023
AREA = Area.CN
NOTA = 550.0
# Recorte unico: uma dimensao (UF), que e tambem coluna de particao -> pruning.
RECORTE_UF = Recorte(filtros={Dimensao.UF: "SP"})
# Sem recorte: a Edicao inteira (Req 1.3) — o caso mais pesado que a API aceita.
RECORTE_VAZIO = Recorte()

# Alvo literal do Req 6.3 para analise de recorte unico.
ALVO_RECORTE_UNICO_S = 3.0
# A analise sem recorte le todas as particoes de UF da Edicao (27 arquivos em vez
# de 1) e agrega ~6,5x mais linhas. O Req 6.3 fala de recorte unico, entao aqui
# afirmamos um multiplo documentado do alvo: 2x. E deliberadamente folgado — a
# medicao real na maquina de desenvolvimento fica uma ordem de magnitude abaixo
# (ver docs/implantacao.md, secao 8.3), e o que se quer detectar e a perda do
# pruning por ``ano`` (que passaria a ler as tres Edicoes).
FATOR_SEM_RECORTE = 2.0
ALVO_SEM_RECORTE_S = ALVO_RECORTE_UNICO_S * FATOR_SEM_RECORTE

# Numero de medicoes cronometradas apos o aquecimento. Pequeno de proposito: o
# teste roda na suite normal e precisa custar poucos segundos.
REPETICOES = 3


# --------------------------------------------------------------------------- #
# Auxiliares                                                                  #
# --------------------------------------------------------------------------- #
def _medir(chamada: Callable[[], Any], repeticoes: int = REPETICOES) -> tuple[float, list[float]]:
    """Cronometra ``chamada``: uma vez a frio e ``repeticoes`` vezes a quente.

    A primeira invocacao (frio) tambem serve de **aquecimento**: e ela que paga
    o custo de primeira-vez (metadados Parquet, cache de pagina). As medicoes
    seguintes representam o regime de operacao.

    Args:
        chamada: Callable sem argumentos que executa a operacao a medir.
        repeticoes: Quantas medicoes quentes fazer depois do aquecimento.

    Returns:
        ``(tempo_frio, tempos_quentes)``, em segundos (``time.perf_counter``).
    """
    inicio = time.perf_counter()
    chamada()
    frio = time.perf_counter() - inicio

    quentes: list[float] = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        chamada()
        quentes.append(time.perf_counter() - inicio)
    return frio, quentes


def _relatorio(rotulo: str, frio: float, quentes: list[float], alvo: float) -> str:
    """Formata (e imprime) a medicao para o relatorio do teste.

    O texto e impresso (visivel com ``pytest -s``) e devolvido para ser usado
    como mensagem de assercao, de modo que os numeros medidos aparecam tambem
    quando o teste **falha**.
    """
    mediana = statistics.median(quentes)
    texto = (
        f"{rotulo}: frio={frio:.3f}s "
        f"quente_mediana={mediana:.3f}s "
        f"quente_max={max(quentes):.3f}s "
        f"(n={len(quentes)}) alvo={alvo:.1f}s"
    )
    print(texto)
    return texto


def _arquivos_lidos(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> int:
    """Conta os arquivos Parquet que o plano executado realmente leu.

    Usa ``EXPLAIN ANALYZE`` e soma as ocorrencias de ``Total Files Read`` do
    perfil — a contagem que o proprio motor reporta para o ``READ_PARQUET``,
    depois de aplicar o *file filter* de particao.

    Args:
        con: Conexao DuckDB aberta.
        sql: SQL a analisar (tipicamente vindo de ``construir_consulta_*``).
        params: Parametros posicionais do SQL.

    Returns:
        Total de arquivos lidos pelo plano.
    """
    plano = con.execute(f"EXPLAIN ANALYZE {sql}", params).fetchall()[0][1]
    ocorrencias = re.findall(r"Total Files Read:\s*([0-9]+)", plano)
    assert ocorrencias, (
        "o perfil de EXPLAIN ANALYZE nao reportou 'Total Files Read'; "
        f"nao foi possivel verificar o pruning. Plano:\n{plano}"
    )
    return sum(int(valor) for valor in ocorrencias)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def config() -> Config:
    """Config apontando para a *silver* real, com limiar explicito.

    O ``limiar_agregacao`` e fixado para nao depender de variaveis ``RADAR_*``
    do ambiente; o recorte medido tem centenas de milhares de linhas, muito
    acima dele.
    """
    return Config(silver_root=_SILVER_REAL, limiar_agregacao=25)


@pytest.fixture(scope="module")
def catalogo(config: Config) -> Catalogo:
    """Catalogo unico para o modulo (a descoberta de Edicoes nao e o que se mede)."""
    return Catalogo(config)


@pytest.fixture(scope="module", autouse=True)
def contexto_ambiente(config: Config) -> None:
    """Imprime o contexto da maquina, para que as medicoes sejam atribuiveis.

    Sem esse contexto, um numero de latencia nao significa nada: e ele que
    permite dizer *em qual ambiente* a medicao foi feita (Req 6.3 fala de
    "ambiente de referencia documentado", rotulado por
    ``RADAR_AMBIENTE_REFERENCIA``).
    """
    print(
        "\ncontexto: "
        f"ambiente_referencia={config.ambiente_referencia} "
        f"cpu_count={os.cpu_count()} "
        f"python={platform.python_version()} "
        f"duckdb={duckdb.__version__} "
        f"silver={_SILVER_REAL}"
    )


@pytest.fixture(scope="module")
def cliente(config: Config) -> Iterator[TestClient]:
    """Cliente HTTP sobre a app real apontando para a *silver* real."""
    with TestClient(criar_app(config)) as cliente_http:
        yield cliente_http


@pytest.fixture(scope="module")
def conexao() -> Iterator[duckdb.DuckDBPyConnection]:
    """Conexao DuckDB reutilizada pelas verificacoes de plano (pruning)."""
    con = duckdb.connect()
    try:
        yield con
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# 1. Latencia da analise de recorte unico (Req 6.3)                           #
# --------------------------------------------------------------------------- #
def test_analise_recorte_unico_dentro_do_alvo(catalogo: Catalogo) -> None:
    """Analise de recorte unico (2023/CN/{UF:SP}) responde dentro de 3 s.

    Este e o cenario literal do Req 6.3. Mede o nucleo (``analisar``), que e
    onde esta o custo: leitura do Parquet + agregacao no DuckDB.
    """
    resultado_ref = analisar(catalogo, EDICAO, AREA, NOTA, RECORTE_UF)
    assert resultado_ref.tamanho_amostral, "recorte medido veio vazio; medicao sem sentido"

    frio, quentes = _medir(lambda: analisar(catalogo, EDICAO, AREA, NOTA, RECORTE_UF))
    relato = _relatorio(
        "analise recorte unico (2023/CN/UF=SP)", frio, quentes, ALVO_RECORTE_UNICO_S
    )

    assert frio <= ALVO_RECORTE_UNICO_S, relato
    assert max(quentes) <= ALVO_RECORTE_UNICO_S, relato


# --------------------------------------------------------------------------- #
# 2. Latencia da analise sem recorte (caso mais pesado)                       #
# --------------------------------------------------------------------------- #
def test_analise_edicao_inteira_dentro_do_alvo_ampliado(catalogo: Catalogo) -> None:
    """Analise sem recorte (Edicao 2023 inteira) responde dentro de 2x o alvo.

    Nao e o cenario do Req 6.3 (que fala de recorte unico), mas e o pedido mais
    caro que a API aceita (Req 1.3) e o que melhor expoe a perda do pruning por
    ``ano``. O limite e um multiplo **documentado** do alvo, nao uma medicao
    apertada.
    """
    resultado_ref = analisar(catalogo, EDICAO, AREA, NOTA, RECORTE_VAZIO)
    assert resultado_ref.tamanho_amostral, "Edicao medida veio vazia; medicao sem sentido"

    frio, quentes = _medir(lambda: analisar(catalogo, EDICAO, AREA, NOTA, RECORTE_VAZIO))
    relato = _relatorio("analise sem recorte (2023/CN)", frio, quentes, ALVO_SEM_RECORTE_S)

    assert frio <= ALVO_SEM_RECORTE_S, relato
    assert max(quentes) <= ALVO_SEM_RECORTE_S, relato


# --------------------------------------------------------------------------- #
# 3. Latencia ponta-a-ponta pela borda HTTP (Req 6.3: "a API SHALL retornar")  #
# --------------------------------------------------------------------------- #
def test_http_analise_recorte_unico_dentro_do_alvo(cliente: TestClient) -> None:
    """``POST /v1/analise`` de recorte unico responde dentro de 3 s.

    O Req 6.3 fala da resposta *da API*, entao a medicao inclui a serializacao
    e a validacao da borda, e nao apenas o nucleo.
    """
    corpo = {
        "edicao": EDICAO,
        "area": AREA.value,
        "nota": NOTA,
        "recorte": {"filtros": {Dimensao.UF.value: "SP"}},
    }

    def chamar() -> None:
        resposta = cliente.post("/v1/analise", json=corpo)
        assert resposta.status_code == 200, resposta.text

    frio, quentes = _medir(chamar)
    relato = _relatorio("POST /v1/analise (2023/CN/UF=SP)", frio, quentes, ALVO_RECORTE_UNICO_S)

    assert frio <= ALVO_RECORTE_UNICO_S, relato
    assert max(quentes) <= ALVO_RECORTE_UNICO_S, relato


# --------------------------------------------------------------------------- #
# 4. Guarda deterministica: partition pruning por uf_prova (Req 6.2)          #
# --------------------------------------------------------------------------- #
def test_pruning_por_uf_reduz_arquivos_lidos(conexao: duckdb.DuckDBPyConnection) -> None:
    """Recorte com ``uf_prova`` le estritamente menos arquivos que sem ele.

    Verificacao **estrutural** (e por isso estavel, ao contrario do relogio de
    parede) do Req 6.2, sobre o SQL que a producao realmente emite
    (``construir_consulta_agregada``). Se o predicado de ``uf_prova`` deixar de
    ser gerado — ou deixar de ser empurrado para o *file filter* de particao —
    as duas contagens se igualam e esta assercao falha.
    """
    com_uf = construir_consulta_agregada(_SILVER_REAL, EDICAO, AREA, RECORTE_UF, NOTA)
    sem_uf = construir_consulta_agregada(_SILVER_REAL, EDICAO, AREA, RECORTE_VAZIO, NOTA)

    arquivos_com_uf = _arquivos_lidos(conexao, com_uf.sql, com_uf.params)
    arquivos_sem_uf = _arquivos_lidos(conexao, sem_uf.sql, sem_uf.params)

    print(
        f"pruning por uf_prova: arquivos lidos com UF={arquivos_com_uf} vs sem UF={arquivos_sem_uf}"
    )

    assert arquivos_com_uf >= 1, "plano com recorte de UF nao leu nenhum arquivo"
    assert arquivos_com_uf < arquivos_sem_uf, (
        "partition pruning por uf_prova nao esta valendo: o recorte com UF leu "
        f"{arquivos_com_uf} arquivo(s) e o sem UF leu {arquivos_sem_uf} — "
        "esperado estritamente menos com UF (Req 6.2)"
    )
