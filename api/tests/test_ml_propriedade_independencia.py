"""Teste de propriedade da independencia do nucleo analitico em relacao ao ML.

Property 12 (task 11.3) — **Nucleo independente do Modelo_ML**: para *qualquer*
estado de configuracao do Modelo_ML (habilitado, desabilitado ou indisponivel),
as requisicoes de analise estatistica devem ser atendidas sem erro (Req 8.2/8.3).

A verificacao vai um passo alem de "nao levantou excecao". O que o design fixa
(AD-5) e que o Modelo_ML e **secundario**: a saida analitica e funcao dos
**dados** e do **Recorte**, e de nada mais. Logo a propriedade e testada como uma
**equivalencia**: para cada exemplo escrevemos uma *silver* minuscula e rodamos
``analisar`` sob **todos** os estados de ML, exigindo resultados
*exatamente iguais* entre si e iguais ao da configuracao padrao (ML desabilitado)
— tanto na igualdade estrutural do :class:`~radar_api.modelos.ResultadoAnalise`
quanto no payload serializado que cruzaria a fronteira HTTP.

Estados de ML gerados (todos com a mesma *silver* e o mesmo limiar):

* ``DESABILITADO`` — ``ml_habilitado=False``, o padrao da implantacao;
* ``HABILITADO_SEM_ARTEFATO`` — habilitado porem sem ``ml_artefato``
  (``ML_INDISPONIVEL``/``artefato_nao_configurado`` em uma inferencia);
* ``HABILITADO_ARTEFATO_INEXISTENTE`` — habilitado apontando para um caminho que
  nao existe (``ML_INDISPONIVEL``/``artefato_inexistente``);
* ``HABILITADO_ARTEFATO_VALIDO`` — habilitado com um artefato **real** e
  funcional (objeto *picklavel* de escopo de modulo, serializado com o ``pickle``
  da stdlib, carregado pelo carregador padrao de :mod:`radar_api.ml`).

A **ordem** de execucao dos estados tambem e gerada (uma permutacao), de modo que
nenhum resultado possa depender de um estado anterior ter aquecido o cache do ML.

Alem da equivalencia, o teste prova a independencia de tres formas
complementares:

* ``analisar`` nunca levanta :class:`~radar_api.erros.ErroMLDesabilitado` nem
  :class:`~radar_api.erros.ErroMLIndisponivel` em nenhum dos estados;
* rodar o nucleo **nunca carrega o modelo**: ``modelos_em_cache() == 0`` depois de
  analisar sob todos os estados — inclusive com um artefato valido configurado;
* o estado gerado e genuinamente distinto (``ml_disponivel`` bate com o esperado
  e o artefato valido de fato infere), o que impede que a equivalencia seja
  vacua por a configuracao de ML estar sendo ignorada.

A separacao estrutural (``radar_api.nucleo`` **nao importa** ``radar_api.ml``) e
verificada a parte, em um subprocesso limpo — mesma tecnica de
``test_ml.py::test_import_sem_efeito_colateral``.

Cada exemplo cria seu proprio ``tempfile.TemporaryDirectory`` (em vez da fixture
``tmp_path`` do pytest) porque, sob ``@given``, o corpo do teste roda muitas
vezes enquanto uma fixture de escopo de funcao seria compartilhada entre os
exemplos — o diretorio proprio mantem cada exemplo isolado e deterministico.

Biblioteca PBT: **hypothesis** (minimo 100 iteracoes).
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

import radar_api.ml as radar_api_ml
import radar_api.nucleo as radar_api_nucleo
from fixtures_silver import escrever_silver
from radar_api.app import criar_app
from radar_api.catalogo import Catalogo
from radar_api.config import Config
from radar_api.erros import ErroMLDesabilitado, ErroMLIndisponivel
from radar_api.ml import EntradaML, inferir, limpar_cache, ml_disponivel, modelos_em_cache
from radar_api.modelos import Area, Dimensao, Recorte, ResultadoAnalise
from radar_api.nucleo import analisar

# Limiar de agregacao pequeno e fixado no teste (independe de variaveis
# RADAR_*): com amostras de 0 a 8 linhas, os exemplos cobrem tanto o resultado
# divulgado quanto a supressao por amostra insuficiente — a equivalencia entre
# estados de ML precisa valer nos dois regimes.
LIMIAR = 3

# Valor base do artefato valido, para conferir que ele realmente infere.
BASE_PREVISAO = 500.0

# Valores de perfil escritos na *silver* e reusados nos Recortes gerados, para
# que um Recorte possa casar linhas (e nao apenas devolver amostra vazia).
REGIOES = ("Sudeste", "Sul", "Nordeste")
TIPOS_ESCOLA = (1, 2)


class ArtefatoDePropriedade:
    """Artefato de ML minimo, *picklavel*, que satisfaz o protocolo ``prever``.

    Definido no escopo do modulo para poder ser serializado com ``pickle`` — e
    assim exercitar o carregador **padrao** de :mod:`radar_api.ml`, sem nenhuma
    biblioteca de ML instalada no ambiente.
    """

    def __init__(self, base: float = BASE_PREVISAO) -> None:
        self.base = base

    def prever(self, caracteristicas: Mapping[str, str]) -> float:
        """Previsao deterministica: base + 10 por caracteristica informada."""
        return self.base + 10.0 * len(caracteristicas)


class EstadoML(Enum):
    """Estado de configuracao do Modelo_ML sob o qual o nucleo e exercitado.

    Cobre as tres situacoes nomeadas pela Property 12 — desabilitado, habilitado
    e indisponivel — sendo a indisponibilidade quebrada nos dois modos que o
    design distingue: sem artefato configurado e com artefato inexistente.
    """

    DESABILITADO = "desabilitado"
    HABILITADO_SEM_ARTEFATO = "habilitado_sem_artefato"
    HABILITADO_ARTEFATO_INEXISTENTE = "habilitado_artefato_inexistente"
    HABILITADO_ARTEFATO_VALIDO = "habilitado_artefato_valido"


# ``ml_disponivel`` esperado por estado: apenas o artefato real e utilizavel.
# Serve de guarda anti-vacuidade — se a configuracao de ML fosse ignorada, a
# equivalencia entre estados seria trivial e este mapa falharia.
DISPONIBILIDADE_ESPERADA: dict[EstadoML, bool] = {
    EstadoML.DESABILITADO: False,
    EstadoML.HABILITADO_SEM_ARTEFATO: False,
    EstadoML.HABILITADO_ARTEFATO_INEXISTENTE: False,
    EstadoML.HABILITADO_ARTEFATO_VALIDO: True,
}

ESTADOS = list(EstadoML)


@pytest.fixture(autouse=True)
def _cache_limpo() -> Iterator[None]:
    """Isola o cache de modelos do ML entre testes (a memoizacao e global)."""
    limpar_cache()
    yield
    limpar_cache()


def _escrever_artefato(caminho: Path, objeto: object) -> Path:
    """Serializa ``objeto`` em ``caminho`` com ``pickle`` (stdlib)."""
    with caminho.open("wb") as arquivo:
        pickle.dump(objeto, arquivo)
    return caminho


def _config_base(raiz: Path) -> Config:
    """Configuracao padrao (ML desabilitado) — a referencia da equivalencia.

    ``ml_habilitado``/``ml_artefato`` sao passados explicitamente (e nao deixados
    no padrao) para que um ``RADAR_ML_*`` presente no ambiente de teste nao mude
    o significado do baseline.
    """
    return Config(silver_root=raiz, limiar_agregacao=LIMIAR, ml_habilitado=False, ml_artefato=None)


def _config_para_estado(
    estado: EstadoML,
    raiz: Path,
    artefato_valido: Path,
    artefato_inexistente: Path,
) -> Config:
    """Monta a :class:`Config` do ``estado``, variando **apenas** os campos de ML.

    ``silver_root`` e ``limiar_agregacao`` sao identicos em todos os estados: a
    unica diferenca entre as configuracoes e o Modelo_ML, o que torna qualquer
    divergencia de resultado atribuivel a ele.
    """
    if estado is EstadoML.DESABILITADO:
        return _config_base(raiz)
    if estado is EstadoML.HABILITADO_SEM_ARTEFATO:
        return Config(
            silver_root=raiz, limiar_agregacao=LIMIAR, ml_habilitado=True, ml_artefato=None
        )
    artefato = (
        artefato_valido if estado is EstadoML.HABILITADO_ARTEFATO_VALIDO else artefato_inexistente
    )
    return Config(
        silver_root=raiz, limiar_agregacao=LIMIAR, ml_habilitado=True, ml_artefato=artefato
    )


def _serializar(resultado: ResultadoAnalise) -> dict[str, Any]:
    """Serializa o resultado de forma canonica (payload que cruzaria o HTTP).

    ``capacidade.dimensoes_suportadas`` e um ``set``: e ordenado aqui para que a
    comparacao entre estados nao dependa da ordem de iteracao do conjunto.
    """
    payload: dict[str, Any] = resultado.model_dump(mode="json")
    capacidade = payload["capacidade"]
    capacidade["dimensoes_suportadas"] = sorted(capacidade["dimensoes_suportadas"])
    return payload


def _analisar_sem_erro_de_ml(
    estado: EstadoML,
    config: Config,
    edicao: int,
    area: Area,
    nota: float,
    recorte: Recorte,
) -> ResultadoAnalise:
    """Roda ``analisar`` exigindo que nenhum erro do Modelo_ML seja propagado.

    Traduz :class:`ErroMLDesabilitado`/:class:`ErroMLIndisponivel` em falha de
    asserção com o estado responsavel — a violacao direta da Req 8.3.
    """
    try:
        return analisar(Catalogo(config), edicao, area, nota, recorte)
    except (ErroMLDesabilitado, ErroMLIndisponivel) as exc:
        raise AssertionError(
            f"a analise estatistica propagou um erro do Modelo_ML no estado "
            f"{estado.value}: {exc.codigo}"
        ) from exc


# Notas validas: finitas, no intervalo 0..1000 inclusive (Req 1.8).
_NOTAS_VALIDAS = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)

# Uma linha da *silver*: nota + perfil (a coluna de nota depende da Area sorteada,
# por isso a linha e montada no corpo do teste).
_LINHAS = st.lists(
    st.tuples(_NOTAS_VALIDAS, st.sampled_from(REGIOES), st.sampled_from(TIPOS_ESCOLA)),
    max_size=8,
)

# Recorte: vazio (toda a Edicao — Req 1.3) ou com 1-2 filtros conjuntivos sobre
# dimensoes efetivamente escritas na *silver*.
_FILTROS_RECORTE = st.one_of(
    st.just({}),
    st.fixed_dictionaries({Dimensao.REGIAO: st.sampled_from(REGIOES)}),
    st.fixed_dictionaries({Dimensao.TIPO_ESCOLA: st.sampled_from(("1", "2"))}),
    st.fixed_dictionaries(
        {
            Dimensao.REGIAO: st.sampled_from(REGIOES),
            Dimensao.TIPO_ESCOLA: st.sampled_from(("1", "2")),
        }
    ),
)

# Amostra suficiente sob LIMIAR=3, usada nos @example de fronteira.
_AMOSTRA_SUFICIENTE = [(float(300 + i * 50), "Sudeste", 1) for i in range(6)]


@settings(max_examples=100, deadline=None)
@given(
    edicao=st.sampled_from((2023, 2024, 2025)),
    area=st.sampled_from(list(Area)),
    nota=_NOTAS_VALIDAS,
    linhas=_LINHAS,
    filtros=_FILTROS_RECORTE,
    ordem=st.permutations(ESTADOS),
)
@example(  # amostra suficiente, sem recorte: resultado divulgado
    edicao=2023,
    area=Area.CN,
    nota=400.0,
    linhas=_AMOSTRA_SUFICIENTE,
    filtros={},
    ordem=ESTADOS,
)
@example(  # amostra vazia: nada a agregar, e ainda assim sem erro
    edicao=2023,
    area=Area.MT,
    nota=500.0,
    linhas=[],
    filtros={},
    ordem=list(reversed(ESTADOS)),
)
@example(  # abaixo do limiar: supressao por privacidade, identica entre estados
    edicao=2024,
    area=Area.LC,
    nota=1000.0,
    linhas=[(700.0, "Sul", 2)],
    filtros={Dimensao.REGIAO: "Sul"},
    ordem=ESTADOS,
)
@example(  # recorte que nao casa nenhuma linha da amostra
    edicao=2025,
    area=Area.REDACAO,
    nota=0.0,
    linhas=_AMOSTRA_SUFICIENTE,
    filtros={Dimensao.REGIAO: "Nordeste", Dimensao.TIPO_ESCOLA: "2"},
    ordem=list(reversed(ESTADOS)),
)
def test_nucleo_independente_do_modelo_ml(
    edicao: int,
    area: Area,
    nota: float,
    linhas: list[tuple[float, str, int]],
    filtros: dict[Dimensao, str],
    ordem: list[EstadoML],
) -> None:
    """Feature: radar-enem-analise-api, Property 12: Núcleo independente do Modelo_ML

    **Validates: Requirements 8.2, 8.3**

    Para qualquer estado de configuracao do Modelo_ML (habilitado, desabilitado
    ou indisponivel), as requisicoes de analise estatistica sao atendidas sem
    erro — e, mais forte, com **resultado identico**: a saida de ``analisar`` e
    funcao apenas dos dados e do Recorte, nunca da configuracao de ML. A ausencia
    ou a falha do Modelo_ML nao degrada nem altera a analise, e rodar o nucleo
    jamais carrega o modelo.
    """
    limpar_cache()
    recorte = Recorte(filtros=filtros)

    with tempfile.TemporaryDirectory() as dir_tmp:
        base_tmp = Path(dir_tmp)
        raiz = base_tmp / "silver"
        # Uma linha por tupla gerada: nota na Area sorteada + colunas de perfil.
        escrever_silver(
            raiz,
            edicao,
            [
                {f"nota_{area.value}": valor, "regiao": regiao, "tipo_escola": tipo}
                for valor, regiao, tipo in linhas
            ],
        )
        artefato_valido = _escrever_artefato(base_tmp / "modelo.pkl", ArtefatoDePropriedade())
        artefato_inexistente = base_tmp / "nao_existe.pkl"
        assert not artefato_inexistente.exists()

        # Referencia: a configuracao padrao da implantacao (ML desabilitado).
        referencia = _analisar_sem_erro_de_ml(
            EstadoML.DESABILITADO, _config_base(raiz), edicao, area, nota, recorte
        )

        # Mesma analise sob cada estado de ML, na ordem gerada.
        configs = {
            estado: _config_para_estado(estado, raiz, artefato_valido, artefato_inexistente)
            for estado in ordem
        }
        resultados = {
            estado: _analisar_sem_erro_de_ml(estado, configs[estado], edicao, area, nota, recorte)
            for estado in ordem
        }

        # -- Property 12: a saida analitica nao depende do estado do ML -------
        payload_referencia = _serializar(referencia)
        for estado in ordem:
            assert resultados[estado] == referencia, (
                f"o estado de ML {estado.value} alterou o ResultadoAnalise"
            )
            assert _serializar(resultados[estado]) == payload_referencia, (
                f"o estado de ML {estado.value} alterou o payload serializado"
            )

        # O nucleo nunca carregou o modelo — nem com um artefato valido a mao.
        assert modelos_em_cache() == 0

        # -- Guarda anti-vacuidade: os estados sao genuinamente distintos -----
        for estado, config in configs.items():
            assert ml_disponivel(config) is DISPONIBILIDADE_ESPERADA[estado]

        # O estado "habilitado e funcional" realmente infere (logo a
        # equivalencia acima nao vem de um ML inerte em todos os estados).
        saida = inferir(configs[EstadoML.HABILITADO_ARTEFATO_VALIDO], EntradaML(area=area))
        assert saida.origem == "modelo"
        assert saida.edicao == 2023
        assert saida.valor_previsto == pytest.approx(BASE_PREVISAO)
        # ... e so agora, por uma inferencia explicita, o modelo entrou no cache.
        assert modelos_em_cache() == 1

    limpar_cache()


# --------------------------------------------------------------------------- #
# Separacao estrutural: o nucleo nao importa o modulo de ML                    #
# --------------------------------------------------------------------------- #
def test_nucleo_nao_importa_o_modulo_de_ml() -> None:
    """Req 8.2 — importar ``radar_api.nucleo`` nao traz ``radar_api.ml`` consigo.

    Verificacao estrutural em um **subprocesso limpo**: nada alem do nucleo (e
    suas dependencias legitimas) entra em ``sys.modules``. E a forma mais forte
    de afirmar a independencia — nao ha caminho de codigo do nucleo capaz de
    alcancar o Modelo_ML, logo nenhuma falha do ML pode alcançar a analise.
    """
    codigo = (
        "import sys\n"
        "import radar_api.nucleo\n"
        "assert 'radar_api.nucleo' in sys.modules\n"
        "carregados = sorted(n for n in sys.modules if n.startswith('radar_api'))\n"
        "assert 'radar_api.ml' not in carregados, carregados\n"
        "assert 'radar_api.app' not in carregados, carregados\n"
        "print(' '.join(carregados))\n"
    )
    # Garante que o subprocesso encontre ``radar_api`` mesmo sem instalacao
    # editavel (o pacote vive em ``api/src``, injetado no pytest via pythonpath).
    raiz_src = Path(radar_api_ml.__file__).resolve().parents[1]
    ambiente = {**os.environ, "PYTHONPATH": str(raiz_src)}
    processo = subprocess.run(  # noqa: S603 — interpretador do proprio venv
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        check=False,
        env=ambiente,
    )

    assert processo.returncode == 0, processo.stderr
    modulos = processo.stdout.split()
    assert "radar_api.nucleo" in modulos
    assert "radar_api.ml" not in modulos


def test_nucleo_nao_referencia_o_modulo_de_ml() -> None:
    """Nenhum atributo de ``radar_api.nucleo`` aponta para ``radar_api.ml``.

    Complemento em processo do teste de subprocesso: mesmo com ``radar_api.ml``
    ja importado por esta suite, o namespace do nucleo nao o referencia (nem o
    modulo, nem qualquer objeto definido nele).
    """
    # Identidade por ``id`` (e nao por igualdade): os valores do namespace nao
    # sao necessariamente hashaveis nem comparaveis de forma barata.
    ids_do_ml = {
        id(valor)
        for valor in vars(radar_api_ml).values()
        if getattr(valor, "__module__", None) == "radar_api.ml"
    }

    for nome, valor in vars(radar_api_nucleo).items():
        assert valor is not radar_api_ml, f"nucleo.{nome} referencia o modulo de ML"
        assert id(valor) not in ids_do_ml, f"nucleo.{nome} vem de radar_api.ml"


# --------------------------------------------------------------------------- #
# Fronteira HTTP: a rota estatistica nao e afetada pelo estado do ML           #
# --------------------------------------------------------------------------- #
def test_analise_http_identica_em_todos_os_estados_de_ml(tmp_path: Path) -> None:
    """Req 8.2/8.3 — ``POST /v1/analise`` responde 200 e o **mesmo** corpo.

    A mesma equivalencia da Property 12, agora atravessando a borda HTTP: sob os
    quatro estados de ML a analise devolve corpo identico, enquanto
    ``POST /v1/ml/inferencia`` alterna entre 409 categorizado e 200 — prova de
    que a indisponibilidade da rota de ML nao contamina a rota estatistica.
    """
    raiz = tmp_path / "silver"
    escrever_silver(
        raiz,
        2023,
        [{"nota_cn": float(300 + i * 50), "regiao": "Sudeste", "tipo_escola": 1} for i in range(6)],
    )
    artefato_valido = _escrever_artefato(tmp_path / "modelo.pkl", ArtefatoDePropriedade())
    artefato_inexistente = tmp_path / "nao_existe.pkl"
    requisicao = {"edicao": 2023, "area": Area.CN.value, "nota": 400.0, "recorte": {"filtros": {}}}

    corpos: dict[EstadoML, Any] = {}
    for estado in ESTADOS:
        config = _config_para_estado(estado, raiz, artefato_valido, artefato_inexistente)
        with TestClient(criar_app(config)) as cliente:
            resposta_analise = cliente.post("/v1/analise", json=requisicao)
            resposta_ml = cliente.post("/v1/ml/inferencia", json={"area": Area.CN.value})

        # A rota estatistica responde 200 em todos os estados de ML (Req 8.3).
        assert resposta_analise.status_code == 200, estado.value
        corpos[estado] = resposta_analise.json()

        # A rota de ML, por sua vez, muda de comportamento com o estado.
        esperado_ml = 200 if DISPONIBILIDADE_ESPERADA[estado] else 409
        assert resposta_ml.status_code == esperado_ml, estado.value

    referencia = corpos[EstadoML.DESABILITADO]
    for estado, corpo in corpos.items():
        assert corpo == referencia, (
            f"o estado de ML {estado.value} alterou a resposta de /v1/analise"
        )
