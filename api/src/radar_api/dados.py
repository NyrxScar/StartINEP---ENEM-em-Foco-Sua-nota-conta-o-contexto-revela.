"""Acesso a camada Prata via DuckDB.

Uma consulta por diagnostico: as contagens do percentil e os momentos da distribuicao
saem juntos, sobre o mesmo recorte, numa varredura so.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

# Whitelists. Nome de coluna NUNCA vem do corpo da requisicao -- so o valor vem, e ele
# vai como parametro. E isso que separa um recorte de uma injecao de SQL.
AREAS: dict[str, str] = {
    "cn": "nota_cn",
    "ch": "nota_ch",
    "lc": "nota_lc",
    "mt": "nota_mt",
    "redacao": "nota_redacao",
}

RECORTES: frozenset[str] = frozenset({
    "regiao",
    "uf_prova",
    "renda_familiar",
    "tipo_escola",
    "dependencia_adm_escola",
    "cor_raca",
    "sexo",
    "faixa_etaria",
    "treineiro",
})


class RecorteInvalido(ValueError):
    """Area ou dimensao de recorte fora da whitelist."""


@dataclass(frozen=True)
class Populacao:
    n_menores: int
    n_iguais: int
    n_total: int
    media: float | None
    desvio: float | None
    mediana: float | None
    q1: float | None
    q3: float | None
    minimo: float | None
    maximo: float | None


class Repositorio:
    def __init__(self, raiz_prata: Path) -> None:
        self._padrao = f"{Path(raiz_prata)}/**/*.parquet"

    def consultar(
        self,
        edicao: int,
        area: str,
        nota: float,
        recorte: dict[str, object],
    ) -> Populacao:
        if area not in AREAS:
            raise RecorteInvalido(f"area '{area}' desconhecida. Conhecidas: {sorted(AREAS)}")

        desconhecidos = sorted(set(recorte) - RECORTES)
        if desconhecidos:
            raise RecorteInvalido(
                f"recorte {desconhecidos} desconhecido. Conhecidos: {sorted(RECORTES)}"
            )

        coluna = AREAS[area]
        condicoes = ["ano = ?", f"{coluna} IS NOT NULL"]
        parametros: list[object] = [nota, nota, edicao]
        for dimensao, valor in recorte.items():
            condicoes.append(f"{dimensao} = ?")
            parametros.append(valor)

        sql = f"""
            SELECT
              count(*) FILTER (WHERE {coluna} < ?)  AS n_menores,
              count(*) FILTER (WHERE {coluna} = ?)  AS n_iguais,
              count(*)                              AS n_total,
              avg({coluna})                         AS media,
              stddev_samp({coluna})                 AS desvio,
              quantile_cont({coluna}, 0.5)          AS mediana,
              quantile_cont({coluna}, 0.25)         AS q1,
              quantile_cont({coluna}, 0.75)         AS q3,
              min({coluna})                         AS minimo,
              max({coluna})                         AS maximo
            FROM read_parquet(?, hive_partitioning = true)
            WHERE {" AND ".join(condicoes)}
        """
        argumentos = [*parametros[:2], self._padrao, *parametros[2:]]
        linha = duckdb.connect().execute(sql, argumentos).fetchone()
        return Populacao(*linha)
