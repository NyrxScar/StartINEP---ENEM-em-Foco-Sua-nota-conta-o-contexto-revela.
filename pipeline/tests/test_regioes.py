import duckdb
import pytest

from radar_etl.transform.regioes import UF_PARA_REGIAO, sql_case_regiao


def test_mapa_cobre_as_27_unidades_federativas():
    assert len(UF_PARA_REGIAO) == 27
    assert set(UF_PARA_REGIAO.values()) == {
        "Norte",
        "Nordeste",
        "Centro-Oeste",
        "Sudeste",
        "Sul",
    }


@pytest.mark.parametrize(
    ("uf", "regiao"),
    [("SC", "Sul"), ("SP", "Sudeste"), ("BA", "Nordeste"), ("AM", "Norte"), ("DF", "Centro-Oeste")],
)
def test_case_sql_traduz_uf_para_regiao(uf, regiao):
    con = duckdb.connect()
    sql = f"SELECT {sql_case_regiao('uf')} AS regiao FROM (SELECT '{uf}' AS uf)"
    assert con.execute(sql).fetchone()[0] == regiao


def test_uf_desconhecida_vira_nulo_em_vez_de_erro():
    con = duckdb.connect()
    sql = f"SELECT {sql_case_regiao('uf')} AS regiao FROM (SELECT 'ZZ' AS uf)"
    assert con.execute(sql).fetchone()[0] is None
