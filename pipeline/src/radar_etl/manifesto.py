from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

BLOCO = 1024 * 1024


def sha256_arquivo(caminho: Path) -> str:
    """Calcula o SHA-256 lendo em blocos de 1 MB, sem carregar o arquivo em RAM."""
    digest = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            digest.update(bloco)
    return digest.hexdigest()


def agora_iso() -> str:
    return datetime.now(UTC).isoformat()


class Manifesto(BaseModel):
    """Linhagem de uma edicao: o que foi baixado, o que foi processado, e com que resultado."""

    edicao: int
    fonte_url: str
    fonte_sha256: str
    fonte_bytes: int
    fonte_last_modified: str | None = None
    baixado_em: str

    csv_bytes: int | None = None
    linhas_bronze: int | None = None
    linhas_prata: int | None = None
    bytes_prata: int | None = None
    versao_contrato: int | None = None
    processado_em: str | None = None

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def carregar(cls, caminho: Path) -> Manifesto | None:
        if not caminho.exists():
            return None
        return cls.model_validate_json(caminho.read_text(encoding="utf-8"))
