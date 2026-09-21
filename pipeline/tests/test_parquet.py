import duckdb

from radar_etl.contracts.modelos import carregar_canonico
from radar_etl.load.parquet import escrever_prata, medir


def _select_sintetico() -> str:
    canonico = carregar_canonico()
    fixas = {"ano", "uf_prova", "regiao", "nota_mt"}
    outras = [f"NULL::{d.tipo} AS {n}" for n, d in canonico.colunas.items() if n not in fixas]
    return f"""
        SELECT 2025::SMALLINT AS ano, uf AS uf_prova, reg AS regiao,
               nota::FLOAT AS nota_mt, {", ".join(outras)}
        FROM (VALUES ('SC', 'Sul', 700.0), ('SC', 'Sul', 500.0), ('BA', 'Nordeste', 600.0))
             AS t(uf, reg, nota)
    """


def _bytes_por_arquivo(destino):
    arquivos = sorted(destino.rglob("*.parquet"))
    return {p.relative_to(destino).as_posix(): p.read_bytes() for p in arquivos}


def test_escreve_parquet_particionado_por_ano_e_uf(tmp_path):
    destino = tmp_path / "silver"

    linhas = escrever_prata(
        duckdb.connect(), _select_sintetico(), destino, carregar_canonico(), 2025
    )

    assert linhas == 3
    assert (destino / "ano=2025" / "uf_prova=SC").is_dir()
    assert (destino / "ano=2025" / "uf_prova=BA").is_dir()


def test_parquet_escrito_e_relido_com_os_mesmos_valores(tmp_path):
    destino = tmp_path / "silver"
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico(), 2025)

    total = (
        duckdb.connect()
        .execute(
            f"SELECT count(*), sum(nota_mt) FROM "
            f"read_parquet('{destino}/**/*.parquet', hive_partitioning=true)"
        )
        .fetchone()
    )
    assert total == (3, 1800.0)


def test_duas_escritas_produzem_bytes_identicos(tmp_path):
    """Idempotencia: e o criterio de pronto da Sprint 1, nao um detalhe."""
    canonico = carregar_canonico()
    rodadas = []
    for nome in ("a", "b"):
        destino = tmp_path / nome
        escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico, 2025)
        rodadas.append(_bytes_por_arquivo(destino))

    assert rodadas[0] == rodadas[1]


def test_reescrita_no_mesmo_destino_nao_acumula_arquivos(tmp_path):
    destino = tmp_path / "silver"
    canonico = carregar_canonico()
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico, 2025)
    primeira = _bytes_por_arquivo(destino)

    escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico, 2025)

    assert _bytes_por_arquivo(destino) == primeira


def test_volumetria_calcula_a_reducao(tmp_path):
    destino = tmp_path / "silver"
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico(), 2025)

    volumetria = medir(bytes_origem=1_000_000, destino=destino, linhas=3)

    assert volumetria.bytes_origem == 1_000_000
    assert volumetria.bytes_destino > 0
    assert 0 < volumetria.reducao_percentual < 100


def _select_ano(ano: int) -> str:
    return _select_sintetico().replace("2025::SMALLINT", f"{ano}::SMALLINT")


def test_escrever_uma_edicao_nao_apaga_as_outras(tmp_path):
    destino = tmp_path / "silver"
    canonico = carregar_canonico()

    escrever_prata(duckdb.connect(), _select_ano(2023), destino, canonico, edicao=2023)
    escrever_prata(duckdb.connect(), _select_ano(2024), destino, canonico, edicao=2024)

    anos = (
        duckdb.connect()
        .execute(
            f"SELECT ano, count(*) FROM read_parquet('{destino}/**/*.parquet', "
            f"hive_partitioning=true) GROUP BY ano ORDER BY ano"
        )
        .fetchall()
    )
    assert anos == [(2023, 3), (2024, 3)]


def test_reescrever_uma_edicao_nao_duplica_nem_vaza_particao_antiga(tmp_path):
    destino = tmp_path / "silver"
    canonico = carregar_canonico()
    escrever_prata(duckdb.connect(), _select_ano(2023), destino, canonico, edicao=2023)

    # A segunda passada de 2023 so tem SC: a particao BA da passada anterior tem que sumir.
    so_sc = _select_ano(2023).replace("('BA', 'Nordeste', 600.0)", "('SC', 'Sul', 600.0)")
    linhas = escrever_prata(duckdb.connect(), so_sc, destino, canonico, edicao=2023)

    assert linhas == 3
    assert not (destino / "ano=2023" / "uf_prova=BA").exists()
