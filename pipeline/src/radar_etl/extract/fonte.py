from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import httpx

TIMEOUT = httpx.Timeout(30.0, read=300.0)


@dataclass(frozen=True)
class MetadadosRemotos:
    """O que o INEP publica hoje, sem baixar o corpo do arquivo."""

    bytes_totais: int | None
    last_modified: str | None
    etag: str | None


def _contexto(cliente: httpx.Client | None):
    if cliente is not None:
        return nullcontext(cliente)
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)


def consultar_metadados(url: str, cliente: httpx.Client | None = None) -> MetadadosRemotos:
    with _contexto(cliente) as c:
        resposta = c.head(url)
        resposta.raise_for_status()
        tamanho = resposta.headers.get("content-length")
        return MetadadosRemotos(
            bytes_totais=int(tamanho) if tamanho is not None else None,
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
