import pytest
import yaml

from radar_etl.contracts.modelos import (
    ContratoInvalido,
    carregar_canonico,
    carregar_contrato,
)

CANONICO_MINIMO = {
    "versao": 1,
    "particoes": ["ano", "uf_prova"],
    "colunas": {
        "ano": {"tipo": "SMALLINT", "descricao": "Ano da edicao"},
        "uf_prova": {"tipo": "VARCHAR", "descricao": "UF de aplicacao da prova"},
        "regiao": {"tipo": "VARCHAR", "descricao": "Macrorregiao derivada de uf_prova"},
        "nota_mt": {"tipo": "FLOAT", "descricao": "Nota de Matematica"},
    },
}


def _escrever(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")


def test_carrega_o_schema_canonico(tmp_path):
    caminho = tmp_path / "canonical.yml"
    _escrever(caminho, CANONICO_MINIMO)

    canonico = carregar_canonico(caminho)

    assert canonico.versao == 1
    assert canonico.particoes == ["ano", "uf_prova"]
    assert canonico.colunas["nota_mt"].tipo == "FLOAT"


def test_carrega_contrato_de_edicao_valido(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2025.yml",
        {
            "edicao": 2025,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/microdados_enem_2025.zip",
                "arquivo_csv": "DADOS/MICRODADOS_ENEM_2025.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {"ano": "NU_ANO", "uf_prova": "SG_UF_PROVA", "nota_mt": "NU_NOTA_MT"},
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    contrato = carregar_contrato(2025, canonico, diretorio=tmp_path)

    assert contrato.edicao == 2025
    assert contrato.fonte.encoding == "latin-1"
    assert contrato.mapeamento["nota_mt"] == "NU_NOTA_MT"


def test_contrato_que_deixa_coluna_canonica_sem_origem_e_rejeitado(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2024.yml",
        {
            "edicao": 2024,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/a.zip",
                "arquivo_csv": "D/A.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {"ano": "NU_ANO", "uf_prova": "SG_UF_PROVA"},  # falta nota_mt
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(2024, canonico, diretorio=tmp_path)

    assert "nota_mt" in str(erro.value)


def test_contrato_que_inventa_coluna_fora_do_canonico_e_rejeitado(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")
    _escrever(
        tmp_path / "enem_2023.yml",
        {
            "edicao": 2023,
            "versao_contrato": 1,
            "fonte": {
                "url": "https://exemplo.invalido/a.zip",
                "arquivo_csv": "D/A.csv",
                "separador": ";",
                "encoding": "latin-1",
            },
            "mapeamento": {
                "ano": "NU_ANO",
                "uf_prova": "SG_UF_PROVA",
                "nota_mt": "NU_NOTA_MT",
                "coluna_fantasma": "TP_QUALQUER",
            },
            "derivadas": {"regiao": "regiao_por_uf"},
        },
    )

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(2023, canonico, diretorio=tmp_path)

    assert "coluna_fantasma" in str(erro.value)


def test_contrato_inexistente_falha_apontando_o_caminho(tmp_path):
    _escrever(tmp_path / "canonical.yml", CANONICO_MINIMO)
    canonico = carregar_canonico(tmp_path / "canonical.yml")

    with pytest.raises(ContratoInvalido) as erro:
        carregar_contrato(1998, canonico, diretorio=tmp_path)

    assert "enem_1998.yml" in str(erro.value)
