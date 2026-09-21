import hashlib

from radar_etl.manifesto import Manifesto, agora_iso, sha256_arquivo


def test_sha256_confere_com_hashlib(tmp_path):
    arquivo = tmp_path / "dados.csv"
    conteudo = b"NU_ANO;SG_UF_PROVA\n2025;SC\n" * 5000
    arquivo.write_bytes(conteudo)

    assert sha256_arquivo(arquivo) == hashlib.sha256(conteudo).hexdigest()


def test_sha256_nao_carrega_arquivo_inteiro_em_memoria(tmp_path):
    # 8 MB com blocos de 1 MB: exercita o laco de streaming mais de uma vez.
    arquivo = tmp_path / "grande.bin"
    with open(arquivo, "wb") as f:
        for _ in range(8):
            f.write(b"x" * 1024 * 1024)

    esperado = hashlib.sha256(b"x" * 1024 * 1024 * 8).hexdigest()
    assert sha256_arquivo(arquivo) == esperado


def test_manifesto_sobrevive_a_ida_e_volta_do_disco(tmp_path):
    destino = tmp_path / "_manifests" / "enem_2025.json"
    original = Manifesto(
        edicao=2025,
        fonte_url="https://exemplo.invalido/microdados_enem_2025.zip",
        fonte_sha256="abc123",
        fonte_bytes=1024,
        fonte_last_modified="Mon, 01 Sep 2026 12:00:00 GMT",
        baixado_em=agora_iso(),
    )
    original.salvar(destino)

    recarregado = Manifesto.carregar(destino)
    assert recarregado == original
    assert recarregado.linhas_prata is None


def test_carregar_manifesto_inexistente_devolve_none(tmp_path):
    assert Manifesto.carregar(tmp_path / "nao_existe.json") is None
