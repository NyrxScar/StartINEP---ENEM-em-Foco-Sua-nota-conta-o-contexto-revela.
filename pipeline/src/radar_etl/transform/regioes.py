from __future__ import annotations

UF_PARA_REGIAO: dict[str, str] = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}


def sql_case_regiao(coluna_uf: str) -> str:
    """Gera o CASE que traduz UF em macrorregiao.

    UF fora do mapa devolve NULL em vez de erro: um codigo inesperado na origem
    e assunto do portao de qualidade, nao motivo para derrubar a transformacao.
    """
    ramos = "\n".join(
        f"    WHEN '{uf}' THEN '{regiao}'" for uf, regiao in sorted(UF_PARA_REGIAO.items())
    )
    return f"CASE {coluna_uf}\n{ramos}\n    ELSE NULL\n  END"
