"""Configuracao por ambiente do servico Radar ENEM.

Le variaveis de ambiente com prefixo ``RADAR_`` para parametrizar a API:
a raiz da camada *silver*, a raiz dos manifestos, o limiar de k-anonimato
(``Limite_Minimo_de_Agregacao``), o Modelo_ML opcional, o timeout de consulta
e o rotulo do ambiente de referencia.

Requisitos atendidos:

* **1.6 / 9.3** — ``limiar_agregacao`` (padrao 25), limiar de agregacao usado
  para suprimir agregados pequenos (k-anonimato).
* **6.3** — ``timeout_consulta_s`` (padrao 30) e ``ambiente_referencia``
  (rotulo do ambiente documentado para os limites de latencia).
* **8.1** — ``ml_habilitado`` (padrao False) e ``ml_artefato`` (opcional) para
  o Modelo_ML secundario.

A raiz da *silver* e um contrato de entrada externo: o ``silver_root`` padrao
serve apenas para desenvolvimento local; em producao ``RADAR_SILVER_ROOT``
aponta para o ponto de montagem dos Parquet (ver secao de implantacao do
design).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do repositorio inferida a partir da localizacao do pacote:
# api/src/radar_api/config.py -> parents[3] == raiz do repositorio.
# Usada apenas como *default* de desenvolvimento (env override e o que importa).
_RAIZ_REPO = Path(__file__).resolve().parents[3]
_SILVER_ROOT_PADRAO = _RAIZ_REPO / "data" / "silver"


class Config(BaseSettings):
    """Configuracao da API, lida do ambiente com prefixo ``RADAR_``.

    Cada campo mapeia para ``RADAR_<NOME_DO_CAMPO_EM_MAIUSCULAS>`` (ex.:
    ``silver_root`` <- ``RADAR_SILVER_ROOT``). Valores ausentes usam os padroes
    abaixo; ``.env`` e suportado para desenvolvimento local.
    """

    model_config = SettingsConfigDict(
        env_prefix="RADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # RADAR_SILVER_ROOT — raiz da camada silver (Parquet particionado).
    silver_root: Path = _SILVER_ROOT_PADRAO
    # RADAR_MANIFESTOS_ROOT — raiz dos manifestos (padrao = silver_root).
    manifestos_root: Path | None = None
    # RADAR_LIMIAR_AGREGACAO — limiar de k-anonimato (Req 1.6, 9.3).
    limiar_agregacao: int = 25
    # RADAR_ML_HABILITADO — habilita o Modelo_ML opcional (Req 8.1).
    ml_habilitado: bool = False
    # RADAR_ML_ARTEFATO — caminho do artefato do Modelo_ML (opcional, Req 8.1).
    ml_artefato: Path | None = None
    # RADAR_TIMEOUT_CONSULTA_S — timeout de consulta, em segundos (Req 6.3).
    timeout_consulta_s: int = 30
    # RADAR_AMBIENTE_REFERENCIA — rotulo do ambiente de referencia (Req 6.3).
    ambiente_referencia: str = "local"
    # RADAR_CORS_ORIGENS — origens permitidas para requisicoes cross-origin
    # do navegador (lista separada por virgula). O padrao cobre o frontend
    # Next.js em desenvolvimento (portas 3000/3001, localhost e 127.0.0.1).
    # Em producao, com frontend e API na mesma origem (roteamento por caminho
    # no ingress), o CORS e desnecessario e esta lista pode ficar vazia.
    cors_origens: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    @model_validator(mode="after")
    def _aplicar_default_manifestos(self) -> Config:
        """Faz ``manifestos_root`` cair para ``silver_root`` quando ausente."""
        if self.manifestos_root is None:
            self.manifestos_root = self.silver_root
        return self

    @property
    def cors_origens_lista(self) -> list[str]:
        """Origens de CORS como lista, ignorando entradas vazias."""
        return [
            origem.strip() for origem in self.cors_origens.split(",") if origem.strip()
        ]


def carregar_config() -> Config:
    """Carrega a configuracao da API a partir do ambiente.

    Returns:
        Instancia de :class:`Config` com os valores resolvidos das variaveis
        de ambiente ``RADAR_*`` (ou os padroes documentados).
    """
    return Config()
