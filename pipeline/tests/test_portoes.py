import pytest

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.quality.portoes import (
    QualidadeReprovada,
    avaliar,
    portao_freshness,
    portao_schema,
    portao_volume,
)


@pytest.fixture
def contrato():
    return carregar_contrato(2023, carregar_canonico())


def test_schema_aprova_quando_todas_as_colunas_de_origem_existem(contrato):
    colunas = [*contrato.mapeamento.values(), "COLUNA_EXTRA_IGNORADA"]
    assert portao_schema(colunas, contrato).aprovado


def test_schema_reprova_e_nomeia_a_coluna_que_sumiu(contrato):
    colunas = [c for c in contrato.mapeamento.values() if c != "NU_NOTA_MT"]
    veredito = portao_schema(colunas, contrato)
    assert not veredito.aprovado
    assert "NU_NOTA_MT" in veredito.mensagem


def test_volume_aprova_variacao_pequena():
    assert portao_volume(4_300_000, 4_200_000).aprovado


def test_volume_reprova_queda_brusca():
    veredito = portao_volume(2_000_000, 4_200_000)
    assert not veredito.aprovado
    assert "52" in veredito.mensagem


def test_volume_aprova_sem_referencia():
    veredito = portao_volume(4_300_000, None)
    assert veredito.aprovado
    assert "referencia" in veredito.mensagem.lower()


def test_freshness_aprova_quando_a_fonte_nao_mudou():
    assert portao_freshness("abc", "abc", "Mon, 01 Sep 2026", "Mon, 01 Sep 2026").aprovado


def test_freshness_reprova_quando_o_inep_republicou_o_arquivo():
    veredito = portao_freshness("abc", "def", "Mon, 01 Sep 2026", "Tue, 10 Oct 2026")
    assert not veredito.aprovado
    assert "retific" in veredito.mensagem.lower()


def test_freshness_reprova_quando_so_o_last_modified_mudou():
    # Sem hash remoto nao da para comparar bytes; o Last-Modified e o unico sinal.
    veredito = portao_freshness("abc", None, "Mon, 01 Sep 2026", "Tue, 10 Oct 2026")
    assert not veredito.aprovado
    assert "Last-Modified" in veredito.mensagem


def test_freshness_aprova_quando_nao_ha_sinal_remoto():
    assert portao_freshness("abc", None, "Mon, 01 Sep 2026", None).aprovado


def test_avaliar_levanta_com_todos_os_vereditos_reprovados(contrato):
    vereditos = [
        portao_schema([c for c in contrato.mapeamento.values() if c != "NU_NOTA_MT"], contrato),
        portao_volume(1_000, 4_200_000),
        portao_freshness("abc", "abc", None, None),
    ]

    with pytest.raises(QualidadeReprovada) as erro:
        avaliar(vereditos)

    assert {v.portao for v in erro.value.vereditos} == {"schema", "volume"}


def test_avaliar_nao_levanta_quando_tudo_aprova():
    avaliar([portao_volume(100, 100)])
