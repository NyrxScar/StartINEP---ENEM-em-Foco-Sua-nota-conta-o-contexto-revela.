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
