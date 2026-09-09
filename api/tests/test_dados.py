import duckdb
import pytest

from radar_api.dados import AREAS, RECORTES, RecorteInvalido, Repositorio


@pytest.fixture
def prata(tmp_path):
    """Prata sintetica: 2023 com notas, 2025 sem nota (como a fonte real)."""
    destino = tmp_path / "silver"
    destino.mkdir()
    con = duckdb.connect()
    con.execute(f"""
        COPY (
          SELECT * FROM (VALUES
            (2023, 'SC', 'Sul', 'E', 2, 100.0),
            (2023, 'SC', 'Sul', 'E', 2, 200.0),
            (2023, 'SC', 'Sul', 'B', 1, 200.0),
            (2023, 'BA', 'Nordeste', 'B', 1, 300.0),
            (2023, 'BA', 'Nordeste', 'B', 1, NULL),
            (2025, 'SC', 'Sul', 'E', 2, NULL)
          ) AS t(ano, uf_prova, regiao, renda_familiar, tipo_escola, nota_mt)
        ) TO '{destino}' (FORMAT PARQUET, PARTITION_BY (ano), OVERWRITE_OR_IGNORE)
    """)
    return destino


def test_conta_menores_iguais_e_total_ignorando_nulos(prata):
    r = Repositorio(prata).consultar(edicao=2023, area="mt", nota=200.0, recorte={})

    assert (r.n_menores, r.n_iguais, r.n_total) == (1, 2, 4)  # a linha NULL fica de fora


def test_recorte_filtra_a_populacao(prata):
    r = Repositorio(prata).consultar(edicao=2023, area="mt", nota=200.0, recorte={"regiao": "Sul"})

    assert r.n_total == 3
    assert r.media == pytest.approx((100 + 200 + 200) / 3)


def test_recortes_combinam(prata):
    r = Repositorio(prata).consultar(
        edicao=2023, area="mt", nota=200.0, recorte={"regiao": "Sul", "renda_familiar": "E"}
    )
    assert r.n_total == 2


def test_medidas_de_dispersao(prata):
    r = Repositorio(prata).consultar(edicao=2023, area="mt", nota=200.0, recorte={})

    assert r.mediana == pytest.approx(200.0)
    assert r.minimo == pytest.approx(100.0)
    assert r.maximo == pytest.approx(300.0)
    # quantile_cont e interpolacao linear (Hyndman-Fan Type 7), igual ao numpy.
    assert r.q1 == pytest.approx(175.0)
    assert r.q3 == pytest.approx(225.0)


def test_edicao_sem_nota_devolve_populacao_vazia(prata):
    r = Repositorio(prata).consultar(edicao=2025, area="mt", nota=500.0, recorte={})
    assert r.n_total == 0


def test_area_desconhecida_e_rejeitada(prata):
    with pytest.raises(RecorteInvalido, match="area"):
        Repositorio(prata).consultar(edicao=2023, area="filosofia", nota=500.0, recorte={})


def test_recorte_desconhecido_e_rejeitado(prata):
    # Barreira contra injecao: a coluna vem de whitelist, nunca do corpo da requisicao.
    with pytest.raises(RecorteInvalido, match="signo"):
        Repositorio(prata).consultar(edicao=2023, area="mt", nota=500.0, recorte={"signo": "leao"})


def test_valor_de_recorte_e_parametrizado_nao_interpolado(prata):
    r = Repositorio(prata).consultar(
        edicao=2023, area="mt", nota=200.0, recorte={"regiao": "Sul' OR '1'='1"}
    )
    assert r.n_total == 0


def test_whitelists_expostas_para_a_api():
    assert "mt" in AREAS and "redacao" in AREAS
    assert "regiao" in RECORTES and "renda_familiar" in RECORTES
