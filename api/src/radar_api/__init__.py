"""Pacote ``radar_api`` — camada de analise e servico do Radar ENEM.

Expoe consultas analiticas agregadas sobre a camada *silver* (Parquet
particionado por ``ano``/``uf_prova``) produzida pelo ETL da Sprint 1,
honrando as restricoes de desidentificacao do INEP (apenas agregados).

Os modulos concretos (config, catalogo, nucleo, etc.) sao importados sob
demanda para manter ``import radar_api`` livre de efeitos colaterais.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
