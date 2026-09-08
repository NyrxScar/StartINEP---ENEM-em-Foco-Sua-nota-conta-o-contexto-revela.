import zipfile

from typer.testing import CliRunner

from radar_etl import __version__
from radar_etl.cli import app

runner = CliRunner()


def test_versao_e_exposta_pelo_pacote():
    assert __version__ == "0.1.0"


def test_cli_responde_ao_help():
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    assert "ingest" in resultado.stdout


def test_inspecionar_lista_arquivos_e_cabecalho(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(
            "DADOS/MICRODADOS_ENEM_2025.csv",
            "NU_ANO;SG_UF_PROVA;NU_NOTA_MT\n2025;SC;712.4\n",
        )
        z.writestr("LEIA-ME.txt", "doc")

    resultado = runner.invoke(app, ["inspecionar", "--zip", str(zip_path)])

    assert resultado.exit_code == 0
    assert "DADOS/MICRODADOS_ENEM_2025.csv" in resultado.stdout
    assert "NU_NOTA_MT" in resultado.stdout
