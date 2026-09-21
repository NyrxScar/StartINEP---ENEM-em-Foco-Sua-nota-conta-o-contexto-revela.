import zipfile

import httpx
import pytest

from radar_etl.extract.descompactar import ArquivoInternoAusente, extrair_csv
from radar_etl.extract.fonte import baixar, consultar_metadados


def _cliente_falso(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_consultar_metadados_le_cabecalhos_sem_baixar_corpo():
    def handler(request: httpx.Request) -> httpx.Response:
        # O servidor do INEP derruba HEAD; usamos GET com Range de 1 byte.
        assert request.method == "GET"
        assert request.headers["Range"] == "bytes=0-0"
        return httpx.Response(
            206,
            content=b"x",
            headers={
                "content-range": "bytes 0-0/734003200",
                "last-modified": "Mon, 01 Sep 2026 12:00:00 GMT",
                "etag": '"abc-123"',
            },
        )

    meta = consultar_metadados("https://exemplo.invalido/a.zip", cliente=_cliente_falso(handler))

    assert meta.bytes_totais == 734003200
    assert meta.last_modified == "Mon, 01 Sep 2026 12:00:00 GMT"
    assert meta.etag == '"abc-123"'


def test_baixar_grava_o_corpo_no_destino(tmp_path):
    corpo = b"conteudo-do-zip" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=corpo)

    destino = tmp_path / "microdados.zip"
    resultado = baixar("https://exemplo.invalido/a.zip", destino, cliente=_cliente_falso(handler))

    assert resultado == destino
    assert destino.read_bytes() == corpo


def test_baixar_propaga_erro_http(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        baixar(
            "https://exemplo.invalido/a.zip",
            tmp_path / "x.zip",
            cliente=_cliente_falso(handler),
        )


def test_extrair_csv_recupera_o_arquivo_pedido(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("DADOS/MICRODADOS_ENEM_2025.csv", "NU_ANO;SG_UF_PROVA\n2025;SC\n")
        z.writestr("LEIA-ME.txt", "documentacao")

    destino = extrair_csv(zip_path, "DADOS/MICRODADOS_ENEM_2025.csv", tmp_path / "bronze")

    assert destino.name == "MICRODADOS_ENEM_2025.csv"
    assert destino.read_text(encoding="utf-8").startswith("NU_ANO;SG_UF_PROVA")


def test_extrair_csv_falha_com_mensagem_util_quando_o_nome_nao_existe(tmp_path):
    zip_path = tmp_path / "microdados.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("DADOS/OUTRO_NOME.csv", "a;b\n")

    with pytest.raises(ArquivoInternoAusente) as erro:
        extrair_csv(zip_path, "DADOS/MICRODADOS_ENEM_2025.csv", tmp_path / "bronze")

    # A mensagem precisa listar o que existe: o nome interno muda entre edicoes (risco R3).
    assert "DADOS/OUTRO_NOME.csv" in str(erro.value)
