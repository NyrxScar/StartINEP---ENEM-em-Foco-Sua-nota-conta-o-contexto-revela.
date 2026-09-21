from __future__ import annotations

import ssl
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import certifi
import httpx

TIMEOUT = httpx.Timeout(30.0, read=300.0)

# O servidor download.inep.gov.br envia apenas o certificado-folha na
# handshake TLS e omite o intermediario da cadeia (RNP ICPEdu GR46 OV TLS CA
# 2025 -> GlobalSign Root R46). Sem esse intermediario, tanto curl quanto
# httpx/certifi falham com CERTIFICATE_VERIFY_FAILED: unable to get local
# issuer certificate, mesmo com a cadeia de confianca publica correta na
# maquina cliente. A causa e uma configuracao incompleta do servidor, nao
# um problema de confianca: por isso a correcao e complementar o bundle de
# CAs do certifi com o intermediario que faltou, e NUNCA usar verify=False,
# que desligaria a verificacao de integridade da fonte inteira — o proposito
# central desta sprint.
# Se a verificacao TLS voltar a falhar (ex.: apos 2030-11-19, quando este
# certificado expira, ou apos uma rotacao de CA da RNP), inspecione o
# certificado-folha atual de download.inep.gov.br e siga a URI "CA Issuers"
# da extensao Authority Information Access para obter o intermediario
# vigente, substituindo o arquivo abaixo.
_CAMINHO_CADEIA_INEP = Path(__file__).parent / "certs" / "inep_chain.pem"


def _contexto_ssl_inep() -> ssl.SSLContext:
    """Monta um SSLContext com as CAs publicas do certifi mais o intermediario da INEP."""
    contexto = ssl.create_default_context(cafile=certifi.where())
    contexto.load_verify_locations(cafile=_CAMINHO_CADEIA_INEP)
    return contexto


@dataclass(frozen=True)
class MetadadosRemotos:
    """O que o INEP publica hoje, sem baixar o corpo do arquivo."""

    bytes_totais: int | None
    last_modified: str | None
    etag: str | None


def _contexto(cliente: httpx.Client | None):
    if cliente is not None:
        return nullcontext(cliente)
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, verify=_contexto_ssl_inep())


def consultar_metadados(url: str, cliente: httpx.Client | None = None) -> MetadadosRemotos:
    # GET de 1 byte em vez de HEAD: o servidor do INEP derruba a conexao em HEAD.
    # O Range faz o corpo nao ser transferido, entao o custo e o mesmo.
    with _contexto(cliente) as c:
        with c.stream("GET", url, headers={"Range": "bytes=0-0"}) as resposta:
            resposta.raise_for_status()
            faixa = resposta.headers.get("content-range")
            tamanho = faixa.rsplit("/", 1)[-1] if faixa else resposta.headers.get("content-length")
            return MetadadosRemotos(
                bytes_totais=int(tamanho) if tamanho and tamanho.isdigit() else None,
                last_modified=resposta.headers.get("last-modified"),
                etag=resposta.headers.get("etag"),
            )


def baixar(url: str, destino: Path, cliente: httpx.Client | None = None) -> Path:
    """Baixa em streaming para nao materializar o ZIP inteiro em memoria."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with _contexto(cliente) as c:
        with c.stream("GET", url) as resposta:
            resposta.raise_for_status()
            with open(destino, "wb") as f:
                for bloco in resposta.iter_bytes(chunk_size=1024 * 1024):
                    f.write(bloco)
    return destino
