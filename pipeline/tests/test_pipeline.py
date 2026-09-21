import zipfile

import pytest

from radar_etl.contracts.modelos import carregar_canonico, carregar_contrato
from radar_etl.manifesto import Manifesto, sha256_arquivo
from radar_etl.pipeline import Caminhos, EdicaoJaProcessada, executar
from radar_etl.quality.portoes import QualidadeReprovada

EDICAO = 2024


def _contrato():
    return carregar_contrato(EDICAO, carregar_canonico())


def _montar_zip(caminhos: Caminhos, linhas: int = 50, remover: str | None = None) -> None:
    """Monta um ZIP com o mesmo formato do INEP, usando as colunas do contrato real."""
    contrato = _contrato()
    origem = [c for c in contrato.mapeamento.values() if c != remover]
    if remover:
        origem.append("COLUNA_RENOMEADA")

    valores = {"NU_ANO": str(EDICAO), "SG_UF_PROVA": "SC", "NU_NOTA_MT": "500.0"}
    corpo = []
    for i in range(linhas):
        valores["SG_UF_PROVA"] = "SC" if i % 2 else "BA"
        corpo.append(";".join(valores.get(c, "1") for c in origem))

    caminhos.bronze.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminhos.bronze / f"microdados_enem_{EDICAO}.zip", "w") as z:
        z.writestr(contrato.fonte.arquivo_csv, ";".join(origem) + "\n" + "\n".join(corpo) + "\n")


@pytest.fixture
def caminhos(tmp_path):
    return Caminhos(raiz=tmp_path)


def _prata(caminhos):
    arquivos = sorted(caminhos.silver.rglob("*.parquet"))
    return {p.relative_to(caminhos.silver).as_posix(): p.read_bytes() for p in arquivos}


def test_ingestao_completa_produz_prata_e_manifesto(caminhos):
    _montar_zip(caminhos)

    manifesto = executar(EDICAO, caminhos, verificar_origem=False)

    assert manifesto.linhas_prata == 50
    assert manifesto.bytes_prata > 0
    assert (caminhos.silver / f"ano={EDICAO}" / "uf_prova=SC").is_dir()
    assert manifesto.fonte_sha256 == sha256_arquivo(
        caminhos.bronze / f"microdados_enem_{EDICAO}.zip"
    )
    assert Manifesto.carregar(caminhos.manifests / f"enem_{EDICAO}.json") == manifesto


def test_reexecucao_com_fonte_inalterada_e_pulada(caminhos):
    _montar_zip(caminhos)
    executar(EDICAO, caminhos, verificar_origem=False)

    with pytest.raises(EdicaoJaProcessada):
        executar(EDICAO, caminhos, verificar_origem=False)


def test_forcar_reprocessa_e_produz_bytes_identicos(caminhos):
    _montar_zip(caminhos)
    executar(EDICAO, caminhos, verificar_origem=False)
    primeira = _prata(caminhos)

    executar(EDICAO, caminhos, forcar=True, verificar_origem=False)

    assert _prata(caminhos) == primeira


def test_coluna_ausente_reprova_o_schema_e_preserva_a_prata(caminhos):
    _montar_zip(caminhos)
    executar(EDICAO, caminhos, verificar_origem=False)
    prata_boa = _prata(caminhos)

    _montar_zip(caminhos, remover="NU_NOTA_MT")
    with pytest.raises(QualidadeReprovada) as erro:
        executar(EDICAO, caminhos, forcar=True, verificar_origem=False)

    assert "NU_NOTA_MT" in str(erro.value)
    assert _prata(caminhos) == prata_boa, "a Prata anterior tem que sobreviver a uma reprovacao"


def test_queda_brusca_de_volume_reprova(caminhos):
    _montar_zip(caminhos, linhas=100)
    executar(EDICAO, caminhos, verificar_origem=False)

    _montar_zip(caminhos, linhas=10)
    with pytest.raises(QualidadeReprovada) as erro:
        executar(EDICAO, caminhos, forcar=True, verificar_origem=False)

    assert "volume" in str(erro.value)


def test_contrato_novo_reprocessa_mesmo_com_fonte_inalterada(caminhos, monkeypatch):
    """Mudar o contrato tem que reprocessar, ainda que o ZIP seja identico.

    A idempotencia por hash da fonte sozinha esconderia o caso mais comum de
    evolucao do pipeline: mapear uma coluna que faltava. Sem esta regra, a Prata
    ficaria em silencio com o resultado do contrato antigo — o pior jeito de
    errar, porque nada avisa.
    """
    _montar_zip(caminhos)
    primeiro = executar(EDICAO, caminhos, verificar_origem=False)

    # Mesma fonte + mesmo contrato: continua sendo pulada.
    with pytest.raises(EdicaoJaProcessada):
        executar(EDICAO, caminhos, verificar_origem=False)

    # Mesma fonte, contrato em versao nova: tem que reprocessar.
    contrato_novo = _contrato()
    object.__setattr__(contrato_novo, "versao_contrato", primeiro.versao_contrato + 1)
    monkeypatch.setattr(
        "radar_etl.pipeline.carregar_contrato", lambda *_a, **_k: contrato_novo
    )

    segundo = executar(EDICAO, caminhos, verificar_origem=False)
    assert segundo.versao_contrato == primeiro.versao_contrato + 1
    assert segundo.fonte_sha256 == primeiro.fonte_sha256, "a fonte nao mudou"
