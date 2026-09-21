from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.extract.descompactar import extrair_csv
from radar_etl.extract.fonte import baixar, consultar_metadados
from radar_etl.load.parquet import escrever_prata, medir
from radar_etl.manifesto import Manifesto, agora_iso, sha256_arquivo
from radar_etl.quality.portoes import avaliar, portao_freshness, portao_schema, portao_volume
from radar_etl.transform.sql import montar_select


class EdicaoJaProcessada(Exception):
    """Fonte inalterada e Prata ja existente: nao ha o que reprocessar."""


@dataclass(frozen=True)
class Caminhos:
    raiz: Path

    @property
    def bronze(self) -> Path:
        return self.raiz / "bronze"

    @property
    def silver(self) -> Path:
        return self.raiz / "silver"

    @property
    def manifests(self) -> Path:
        return self.raiz / "_manifests"


def executar(
    edicao: int,
    caminhos: Caminhos,
    forcar: bool = False,
    verificar_origem: bool = True,
) -> Manifesto:
    """Ingere uma edicao: Bronze -> portoes -> Prata.

    A ordem importa: os portoes rodam ANTES de escrever. Como `avaliar` levanta, a
    Prata anterior sobrevive a uma reprovacao sem nenhum mecanismo de rollback.
    """
    canonico = carregar_canonico()
    contrato = carregar_contrato(edicao, canonico)

    zip_path = caminhos.bronze / f"microdados_enem_{edicao}.zip"
    manifesto_path = caminhos.manifests / f"enem_{edicao}.json"
    anterior = Manifesto.carregar(manifesto_path)

    if not zip_path.exists():
        baixar(contrato.fonte.url, zip_path)

    sha_local = sha256_arquivo(zip_path)

    # A fonte sozinha nao decide: o contrato tambem e entrada do processamento.
    # Sem comparar `versao_contrato`, editar um contrato (mapear uma coluna nova,
    # corrigir uma origem) e re-rodar devolveria "ja processada" e deixaria na
    # Prata um resultado que nao corresponde ao contrato vigente — em silencio,
    # que e o pior jeito de errar.
    mesma_fonte = anterior and anterior.fonte_sha256 == sha_local and anterior.linhas_prata
    mesmo_contrato = anterior and anterior.versao_contrato == contrato.versao_contrato
    if mesma_fonte and mesmo_contrato and not forcar:
        raise EdicaoJaProcessada(
            f"Edicao {edicao} ja processada a partir da mesma fonte "
            f"(sha256 {sha_local[:12]}...) e do contrato v{contrato.versao_contrato}. "
            f"Use --forcar para reprocessar."
        )

    last_modified_remoto = None
    if verificar_origem:
        last_modified_remoto = consultar_metadados(contrato.fonte.url).last_modified
        avaliar([
            portao_freshness(
                sha256_local=sha_local,
                sha256_remoto=None,
                last_modified_local=anterior.fonte_last_modified if anterior else None,
                last_modified_remoto=last_modified_remoto,
            )
        ])

    csv_path = extrair_csv(zip_path, contrato.fonte.arquivo_csv, caminhos.bronze / str(edicao))

    con = duckdb.connect()
    leitura = (
        f"read_csv('{str(csv_path).replace(chr(39), chr(39) * 2)}', "
        f"delim = '{contrato.fonte.separador}', header = true, "
        f"encoding = '{contrato.fonte.encoding}', all_varchar = true)"
    )

    # `description` devolve o cabecalho real sem ler nenhuma linha de dados.
    colunas_no_csv = [d[0] for d in con.execute(f"SELECT * FROM {leitura} LIMIT 0").description]

    # Passada extra sobre o CSV, deliberada: o portao de volume precisa do total ANTES
    # da promocao. Promover para so entao descobrir a queda seria tarde demais.
    linhas_bronze = con.execute(f"SELECT count(*) FROM {leitura}").fetchone()[0]

    avaliar([
        portao_schema(colunas_no_csv, contrato),
        portao_volume(linhas_bronze, anterior.linhas_prata if anterior else None),
    ])

    linhas_prata = escrever_prata(
        con, montar_select(contrato, canonico, csv_path), caminhos.silver, canonico, edicao
    )
    # Mede so a particao desta edicao: somar a Prata inteira reportaria a volumetria
    # acumulada de todas as edicoes ja ingeridas.
    particao = caminhos.silver / f"{canonico.particoes[0]}={edicao}"
    volumetria = medir(zip_path.stat().st_size, particao, linhas_prata)

    manifesto = Manifesto(
        edicao=edicao,
        fonte_url=contrato.fonte.url,
        fonte_sha256=sha_local,
        fonte_bytes=zip_path.stat().st_size,
        fonte_last_modified=last_modified_remoto
        or (anterior.fonte_last_modified if anterior else None),
        baixado_em=anterior.baixado_em if anterior else agora_iso(),
        csv_bytes=csv_path.stat().st_size,
        linhas_bronze=linhas_bronze,
        linhas_prata=linhas_prata,
        bytes_prata=volumetria.bytes_destino,
        versao_contrato=contrato.versao_contrato,
        processado_em=agora_iso(),
    )
    manifesto.salvar(manifesto_path)
    return manifesto
