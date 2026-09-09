from pathlib import Path

import duckdb
import pytest

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.transform.sql import DerivacaoDesconhecida, montar_select


def _csv_da_edicao(tmp_path: Path, edicao: int, linhas: list[dict[str, str]]) -> tuple:
    """Monta um CSV cujo cabecalho sao as colunas de origem reais do contrato."""
    canonico = carregar_canonico()
    contrato = carregar_contrato(edicao, canonico)
    contrato.fonte.encoding = "utf-8"

    origem = list(contrato.mapeamento.values())
    csv = tmp_path / f"amostra_{edicao}.csv"
    corpo = "\n".join(";".join(linha.get(c, "") for c in origem) for linha in linhas)
    csv.write_text(";".join(origem) + "\n" + corpo + "\n", encoding="utf-8")
    return csv, contrato, canonico


def test_select_2023_produz_todas_as_colunas_canonicas(tmp_path):
    csv, contrato, canonico = _csv_da_edicao(
        tmp_path, 2023, [{"SG_UF_PROVA": "SC"}, {"SG_UF_PROVA": "BA"}]
    )

    tabela = duckdb.connect().execute(montar_select(contrato, canonico, csv)).to_arrow_table()

    assert set(tabela.column_names) == set(canonico.colunas)
    assert tabela.num_rows == 2


def test_valores_convertidos_e_regiao_derivada(tmp_path):
    csv, contrato, canonico = _csv_da_edicao(
        tmp_path,
        2023,
        [
            {"NU_ANO": "2023", "SG_UF_PROVA": "SC", "NU_NOTA_MT": "712.4", "IN_TREINEIRO": "0"},
            {"NU_ANO": "2023", "SG_UF_PROVA": "BA", "NU_NOTA_MT": "", "IN_TREINEIRO": "1"},
        ],
    )
    con = duckdb.connect()
    con.execute(f"CREATE TABLE prata AS {montar_select(contrato, canonico, csv)}")

    sul = con.execute("SELECT regiao, nota_mt, treineiro FROM prata WHERE uf_prova='SC'").fetchone()
    assert sul == ("Sul", pytest.approx(712.4, abs=0.01), False)

    # Ausente na prova: o INEP grava nota vazia. Tem que virar NULL, nunca 0.0 --
    # zero entraria na media e corromperia toda estatistica do recorte.
    nordeste = con.execute(
        "SELECT regiao, nota_mt, treineiro FROM prata WHERE uf_prova='BA'"
    ).fetchone()
    assert nordeste == ("Nordeste", None, True)


def test_colunas_ausentes_viram_null_tipado(tmp_path):
    csv, contrato, canonico = _csv_da_edicao(
        tmp_path, 2024, [{"NU_ANO": "2024", "SG_UF_PROVA": "SC", "NU_NOTA_MT": "500.0"}]
    )
    assert contrato.ausentes, "o contrato de 2024 precisa declarar colunas ausentes"

    tabela = duckdb.connect().execute(montar_select(contrato, canonico, csv)).to_arrow_table()

    for coluna in contrato.ausentes:
        assert coluna in tabela.column_names
        assert tabela.column(coluna).to_pylist() == [None]

    # Ausente nao vira coluna sem tipo: o schema da Prata e igual em toda edicao.
    tipos = {campo.name: str(campo.type) for campo in tabela.schema}
    assert tipos["renda_familiar"] == "string"
    assert tipos["nota_mt"] == "float"
    assert tabela.column("nota_mt").to_pylist() == [pytest.approx(500.0)]


def test_derivacao_nao_reconhecida_falha_cedo(tmp_path):
    csv, contrato, canonico = _csv_da_edicao(tmp_path, 2023, [{"SG_UF_PROVA": "SC"}])
    contrato.derivadas = {"regiao": "funcao_inexistente"}

    with pytest.raises(DerivacaoDesconhecida) as erro:
        montar_select(contrato, canonico, csv)

    assert "funcao_inexistente" in str(erro.value)
