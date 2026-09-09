from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb

from radar_etl.contracts.modelos import SchemaCanonico


@dataclass(frozen=True)
class Volumetria:
    bytes_origem: int
    bytes_destino: int
    linhas: int

    @property
    def reducao_percentual(self) -> float:
        if self.bytes_origem == 0:
            return 0.0
        return (1 - self.bytes_destino / self.bytes_origem) * 100


def escrever_prata(
    con: duckdb.DuckDBPyConnection,
    select_sql: str,
    destino: Path,
    canonico: SchemaCanonico,
) -> int:
    """Escreve a camada Prata em Parquet+Snappy, particionada e reproduzivel.

    Determinismo e requisito, nao detalhe: threads=1, ordem de insercao preservada e
    ORDER BY ALL fazem duas execucoes sobre a mesma fonte produzirem bytes identicos.
    E assim que a idempotencia do pipeline vira algo verificavel em vez de alegado.
    """
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True, exist_ok=True)

    con.execute("SET threads TO 1")
    con.execute("SET preserve_insertion_order TO true")

    particoes = ", ".join(canonico.particoes)
    caminho = str(destino).replace("'", "''")
    con.execute(f"""
        COPY (SELECT * FROM ({select_sql}) ORDER BY ALL)
        TO '{caminho}'
        (FORMAT PARQUET, COMPRESSION SNAPPY, PARTITION_BY ({particoes}),
         OVERWRITE_OR_IGNORE, FILENAME_PATTERN 'dados_{{i}}')
    """)

    return con.execute(
        f"SELECT count(*) FROM read_parquet('{caminho}/**/*.parquet', hive_partitioning=true)"
    ).fetchone()[0]


def medir(bytes_origem: int, destino: Path, linhas: int) -> Volumetria:
    bytes_destino = sum(p.stat().st_size for p in destino.rglob("*.parquet"))
    return Volumetria(bytes_origem=bytes_origem, bytes_destino=bytes_destino, linhas=linhas)
