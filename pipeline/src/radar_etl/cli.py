import zipfile
from pathlib import Path

import typer

app = typer.Typer(help="Pipeline de ingestao dos microdados do ENEM.", no_args_is_help=True)


@app.command()
def ingest(
    edicao: int = typer.Option(..., help="Ano da edicao do ENEM."),
    raiz: Path = typer.Option(Path("../data"), help="Raiz das camadas de dados."),
    forcar: bool = typer.Option(False, "--forcar", help="Reprocessa mesmo sem mudanca na fonte."),
    sem_rede: bool = typer.Option(False, "--sem-rede", help="Pula a verificacao de freshness."),
) -> None:
    """Ingere uma edicao do ENEM: Bronze -> portoes de qualidade -> Prata."""
    from radar_etl.pipeline import Caminhos, EdicaoJaProcessada, executar
    from radar_etl.quality.portoes import QualidadeReprovada

    try:
        manifesto = executar(
            edicao, Caminhos(raiz=raiz), forcar=forcar, verificar_origem=not sem_rede
        )
    except EdicaoJaProcessada as aviso:
        typer.echo(f"[pulado] {aviso}")
        raise typer.Exit(code=0) from aviso
    except QualidadeReprovada as erro:
        typer.echo(f"[REPROVADO] {erro}", err=True)
        raise typer.Exit(code=1) from erro

    reducao = (1 - manifesto.bytes_prata / manifesto.fonte_bytes) * 100
    typer.echo(
        f"[ok] Edicao {manifesto.edicao}: {manifesto.linhas_prata:,} linhas na Prata | "
        f"{manifesto.fonte_bytes / 1_048_576:.1f} MB -> "
        f"{manifesto.bytes_prata / 1_048_576:.1f} MB ({reducao:.1f}% de reducao)"
    )


@app.command()
def inspecionar(
    zip_path: Path = typer.Option(..., "--zip", help="Caminho do ZIP de microdados."),  # noqa: B008
    linhas: int = typer.Option(3, help="Quantas linhas de amostra exibir."),
) -> None:
    """Lista o conteudo do ZIP e o cabecalho do maior CSV, para escrever o contrato da edicao."""
    with zipfile.ZipFile(zip_path) as z:
        infos = sorted(z.infolist(), key=lambda i: i.file_size, reverse=True)

        typer.echo("=== Arquivos no ZIP (maiores primeiro) ===")
        for info in infos:
            typer.echo(f"  {info.file_size / 1_048_576:10.1f} MB  {info.filename}")

        csvs = [i for i in infos if i.filename.lower().endswith(".csv")]
        if not csvs:
            typer.echo("\nNenhum CSV encontrado no ZIP.")
            raise typer.Exit(code=1)

        maior = csvs[0]
        typer.echo(f"\n=== Cabecalho de {maior.filename} ===")
        with z.open(maior.filename) as f:
            bruto = f.read(256 * 1024)

        for codificacao in ("utf-8", "latin-1"):
            try:
                texto = bruto.decode(codificacao)
            except UnicodeDecodeError:
                typer.echo(f"  encoding {codificacao}: FALHOU")
                continue
            typer.echo(f"  encoding {codificacao}: OK")
            for numero, linha in enumerate(texto.splitlines()[: linhas + 1]):
                rotulo = "cabecalho" if numero == 0 else f"linha {numero}"
                typer.echo(f"    [{rotulo}] {linha[:400]}")
            break
