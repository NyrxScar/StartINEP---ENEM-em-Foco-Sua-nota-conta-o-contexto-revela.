"""API do Radar ENEM.

Nada do que o usuario informa e persistido: notas e perfil sao processados na
requisicao e descartados. E requisito de projeto, nao otimizacao -- elimina a maior
parte da superficie de exposicao LGPD.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from radar_api.dados import AREAS, RECORTES, Populacao, RecorteInvalido, Repositorio
from radar_api.stats import percentil, zscore

# Abaixo disso o percentil existe mas nao merece a mesma confianca visual que um
# calculado sobre milhoes de pessoas. Ver PLANO_IMPLEMENTACAO.md, guarda de N minimo.
N_MINIMO = 100

METODOLOGIA = {
    "definicao_percentil": "posto medio (mid-rank): (N_menores + 0,5 x N_iguais) / N",
    "quantis": "interpolacao linear (Hyndman-Fan Type 7)",
    "desvio_padrao": "amostral, denominador n-1",
    "ressalva_zscore": (
        "As notas do ENEM vem de TRI e nao seguem distribuicao normal. O Z-score aqui e "
        "estatistica descritiva -- distancia ate a media em desvios-padrao -- e NAO deve "
        "ser convertido em percentil pela tabela da normal padrao. Para posicionamento "
        "relativo use o percentil, calculado sobre a distribuicao empirica real."
    ),
    "fonte": "Microdados do ENEM - INEP",
}

Nota = Annotated[float, Field(ge=0, le=1000)]


class Requisicao(BaseModel):
    edicao: int
    notas: dict[str, Nota] = Field(min_length=1)
    recorte: dict[str, str | int | bool] = {}


class ResultadoArea(BaseModel):
    nota: float
    n: int
    percentil: float | None = None
    zscore: float | None = None
    media: float | None = None
    mediana: float | None = None
    desvio_padrao: float | None = None
    q1: float | None = None
    q3: float | None = None
    minimo: float | None = None
    maximo: float | None = None
    histograma: list[tuple[float, int]] = []
    aviso: str | None = None


class Resposta(BaseModel):
    edicao: int
    recorte_descricao: str
    resultados: dict[str, ResultadoArea]
    metodologia: dict[str, str]


def _descrever(recorte: dict) -> str:
    if not recorte:
        return "Brasil (todos os participantes)"
    return " · ".join(f"{k}: {v}" for k, v in recorte.items())


def _avaliar(nota: float, p: Populacao) -> ResultadoArea:
    if p.n_total == 0:
        return ResultadoArea(
            nota=nota, n=0, aviso="Sem dados para este recorte nesta edicao."
        )

    aviso = None
    if p.n_total < N_MINIMO:
        aviso = (
            f"Recorte com apenas {p.n_total} participantes: o percentil e exato para este "
            f"grupo, mas pouco representativo. Interprete com cautela."
        )

    return ResultadoArea(
        nota=nota,
        n=p.n_total,
        percentil=round(percentil(p.n_menores, p.n_iguais, p.n_total), 2),
        zscore=round(z, 2) if (z := zscore(nota, p.media, p.desvio)) is not None else None,
        media=p.media,
        mediana=p.mediana,
        desvio_padrao=p.desvio,
        q1=p.q1,
        q3=p.q3,
        minimo=p.minimo,
        maximo=p.maximo,
        histograma=p.histograma,
        aviso=aviso,
    )


def criar_app(raiz_prata: Path) -> FastAPI:
    repo = Repositorio(raiz_prata)
    app = FastAPI(title="Radar ENEM", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("RADAR_CORS_ORIGINS", "*").split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/edicoes")
    def edicoes() -> dict[str, list[int]]:
        anos = sorted(int(p.name.removeprefix("ano=")) for p in raiz_prata.glob("ano=*"))
        return {"edicoes": anos}

    @app.get("/recortes")
    def recortes() -> dict[str, list[str]]:
        return {"areas": sorted(AREAS), "recortes": sorted(RECORTES)}

    @app.post("/diagnostico", response_model=Resposta)
    def diagnostico(req: Requisicao) -> Resposta:
        try:
            resultados = {
                area: _avaliar(nota, repo.consultar(req.edicao, area, nota, req.recorte))
                for area, nota in req.notas.items()
            }
        except RecorteInvalido as erro:
            raise HTTPException(status_code=400, detail=str(erro)) from erro

        return Resposta(
            edicao=req.edicao,
            recorte_descricao=_descrever(req.recorte),
            resultados=resultados,
            metodologia=METODOLOGIA,
        )

    return app


app = criar_app(Path(os.getenv("RADAR_PRATA", "../data/silver")))
