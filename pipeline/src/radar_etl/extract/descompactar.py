from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


class ArquivoInternoAusente(Exception):
    """O nome esperado dentro do ZIP nao existe nesta edicao."""


def extrair_csv(zip_path: Path, nome_interno: str, destino_dir: Path) -> Path:
    """Extrai um unico arquivo do ZIP para `destino_dir`, preservando apenas o nome base."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        disponiveis = z.namelist()
        if nome_interno not in disponiveis:
            raise ArquivoInternoAusente(
                f"'{nome_interno}' nao existe em {zip_path.name}. "
                f"Arquivos disponiveis: {disponiveis}"
            )
        destino = destino_dir / Path(nome_interno).name
        with z.open(nome_interno) as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida, length=1024 * 1024)
    return destino
