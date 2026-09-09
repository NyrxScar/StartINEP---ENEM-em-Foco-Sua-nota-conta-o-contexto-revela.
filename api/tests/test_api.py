import duckdb
import pytest
from fastapi.testclient import TestClient

from radar_api.main import criar_app


@pytest.fixture
def cliente(tmp_path):
    destino = tmp_path / "silver"
    destino.mkdir()
    linhas = ",\n".join(
        f"(2023, 'SC', 'Sul', 'E', {100.0 + i}, {200.0 + i})" for i in range(60)
    )
    duckdb.connect().execute(f"""
        COPY (SELECT * FROM (VALUES {linhas})
              AS t(ano, uf_prova, regiao, renda_familiar, nota_mt, nota_redacao))
        TO '{destino}' (FORMAT PARQUET, PARTITION_BY (ano), OVERWRITE_OR_IGNORE)
    """)
    return TestClient(criar_app(destino))


def test_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_diagnostico_devolve_percentil_e_contexto(cliente):
    resposta = cliente.post(
        "/diagnostico",
        json={"edicao": 2023, "notas": {"mt": 130.0}, "recorte": {"regiao": "Sul"}},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    mt = corpo["resultados"]["mt"]
    assert mt["n"] == 60
    assert mt["percentil"] == pytest.approx(50.83, abs=0.01)
    assert mt["media"] == pytest.approx(129.5)
    assert corpo["recorte_descricao"] == "regiao: Sul"
    # Nenhum numero sai sem dizer como foi calculado.
    assert "posto medio" in corpo["metodologia"]["definicao_percentil"]


def test_varias_areas_de_uma_vez(cliente):
    corpo = cliente.post(
        "/diagnostico", json={"edicao": 2023, "notas": {"mt": 130.0, "redacao": 230.0}}
    ).json()
    assert set(corpo["resultados"]) == {"mt", "redacao"}


def test_nota_fora_da_escala_e_rejeitada(cliente):
    for nota in (1200.0, -5.0):
        resposta = cliente.post("/diagnostico", json={"edicao": 2023, "notas": {"mt": nota}})
        assert resposta.status_code == 422


def test_area_desconhecida_e_rejeitada(cliente):
    resposta = cliente.post("/diagnostico", json={"edicao": 2023, "notas": {"filosofia": 500.0}})
    assert resposta.status_code == 400
    assert "filosofia" in resposta.json()["detail"]


def test_recorte_desconhecido_vira_400_e_nao_500(cliente):
    resposta = cliente.post(
        "/diagnostico", json={"edicao": 2023, "notas": {"mt": 130.0}, "recorte": {"signo": "leao"}}
    )
    assert resposta.status_code == 400
    assert "signo" in resposta.json()["detail"]


def test_recorte_sem_populacao_avisa_em_vez_de_quebrar(cliente):
    corpo = cliente.post(
        "/diagnostico",
        json={"edicao": 2023, "notas": {"mt": 130.0}, "recorte": {"regiao": "Norte"}},
    ).json()

    mt = corpo["resultados"]["mt"]
    assert mt["n"] == 0
    assert mt["percentil"] is None
    assert "sem dados" in mt["aviso"].lower()


def test_recorte_pequeno_recebe_aviso_de_confiabilidade(cliente):
    """Percentil sobre 40 pessoas nao pode parecer igual a percentil sobre 4 milhoes."""
    corpo = cliente.post(
        "/diagnostico",
        json={"edicao": 2023, "notas": {"mt": 130.0}, "recorte": {"renda_familiar": "E"}},
    ).json()
    mt = corpo["resultados"]["mt"]
    assert mt["n"] == 60
    assert mt["percentil"] is not None, "o percentil e exato mesmo em recorte pequeno"
    assert "cautela" in mt["aviso"]


def test_edicoes_disponiveis(cliente):
    assert cliente.get("/edicoes").json() == {"edicoes": [2023]}
