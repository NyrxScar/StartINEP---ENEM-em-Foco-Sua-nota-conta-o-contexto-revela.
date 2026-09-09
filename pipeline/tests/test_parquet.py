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

    linhas = escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico())

    assert linhas == 3
    assert (destino / "ano=2025" / "uf_prova=SC").is_dir()
    assert (destino / "ano=2025" / "uf_prova=BA").is_dir()


def test_parquet_escrito_e_relido_com_os_mesmos_valores(tmp_path):
    destino = tmp_path / "silver"
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico())

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
        escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico)
        rodadas.append(_bytes_por_arquivo(destino))

    assert rodadas[0] == rodadas[1]


def test_reescrita_no_mesmo_destino_nao_acumula_arquivos(tmp_path):
    destino = tmp_path / "silver"
    canonico = carregar_canonico()
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico)
    primeira = _bytes_por_arquivo(destino)

    escrever_prata(duckdb.connect(), _select_sintetico(), destino, canonico)

    assert _bytes_por_arquivo(destino) == primeira


def test_volumetria_calcula_a_reducao(tmp_path):
    destino = tmp_path / "silver"
    escrever_prata(duckdb.connect(), _select_sintetico(), destino, carregar_canonico())

    volumetria = medir(bytes_origem=1_000_000, destino=destino, linhas=3)

    assert volumetria.bytes_origem == 1_000_000
    assert volumetria.bytes_destino > 0
    assert 0 < volumetria.reducao_percentual < 100
