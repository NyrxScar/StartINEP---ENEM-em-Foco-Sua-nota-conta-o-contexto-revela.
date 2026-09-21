from __future__ import annotations

from dataclasses import dataclass

from radar_etl.contracts.modelos import ContratoEdicao


@dataclass(frozen=True)
class Veredito:
    portao: str
    aprovado: bool
    mensagem: str


class QualidadeReprovada(Exception):
    """Ao menos um portao reprovou. A promocao para a camada Prata nao acontece."""

    def __init__(self, vereditos: list[Veredito]) -> None:
        self.vereditos = vereditos
        detalhes = "\n".join(f"  - [{v.portao}] {v.mensagem}" for v in vereditos)
        super().__init__(f"Portoes de qualidade reprovaram:\n{detalhes}")


def portao_schema(colunas_no_csv: list[str], contrato: ContratoEdicao) -> Veredito:
    """A estrutura da fonte mudou? Coluna a mais e tolerada; coluna a menos, nao."""
    ausentes = sorted(set(contrato.mapeamento.values()) - set(colunas_no_csv))
    if ausentes:
        return Veredito(
            "schema",
            False,
            f"Colunas exigidas pelo contrato da edicao {contrato.edicao} nao existem no "
            f"CSV: {ausentes}. Revise o contrato antes de reprocessar.",
        )
    return Veredito("schema", True, f"{len(contrato.mapeamento)} colunas de origem localizadas.")


def portao_volume(
    linhas_atual: int,
    linhas_referencia: int | None,
    tolerancia: float = 0.20,
) -> Veredito:
    """Houve queda brusca na ingestao?"""
    if linhas_referencia is None:
        return Veredito(
            "volume",
            True,
            f"{linhas_atual:,} linhas. Sem referencia comparavel para esta edicao.",
        )

    variacao = (linhas_atual - linhas_referencia) / linhas_referencia
    if abs(variacao) > tolerancia:
        return Veredito(
            "volume",
            False,
            f"Variacao de {variacao:.0%} ({linhas_referencia:,} -> {linhas_atual:,}) excede a "
            f"tolerancia de {tolerancia:.0%}. Exige conferencia manual.",
        )
    return Veredito("volume", True, f"{linhas_atual:,} linhas, variacao de {variacao:+.1%}.")


def portao_freshness(
    sha256_local: str,
    sha256_remoto: str | None,
    last_modified_local: str | None,
    last_modified_remoto: str | None,
) -> Veredito:
    """O arquivo que temos ainda e o que o INEP publica?

    O INEP retifica microdados recem-publicados: a edicao de 2025 foi ajustada em
    01/09/2026. Reprocessar depois de uma retificacao sem perceber mudaria as
    estatisticas em silencio, que e pior do que um erro visivel.
    """
    if sha256_remoto is not None and sha256_remoto != sha256_local:
        return Veredito(
            "freshness",
            False,
            "O arquivo na origem mudou desde o download (hash divergente): o INEP "
            "provavelmente retificou a edicao. Rebaixe o Bronze e reprocesse "
            "conscientemente.",
        )

    if (
        last_modified_remoto is not None
        and last_modified_local is not None
        and last_modified_remoto != last_modified_local
    ):
        return Veredito(
            "freshness",
            False,
            f"Last-Modified mudou na origem: '{last_modified_local}' -> "
            f"'{last_modified_remoto}'. Confirme se a edicao foi retificada.",
        )

    return Veredito("freshness", True, "Bronze corresponde ao que a origem publica.")


def avaliar(vereditos: list[Veredito]) -> None:
    reprovados = [v for v in vereditos if not v.aprovado]
    if reprovados:
        raise QualidadeReprovada(reprovados)
