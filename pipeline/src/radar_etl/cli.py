import typer

app = typer.Typer(help="Pipeline de ingestao dos microdados do ENEM.", no_args_is_help=True)


@app.command()
def ingest(edicao: int = typer.Option(..., help="Ano da edicao do ENEM.")) -> None:
    """Executa a ingestao de uma edicao (implementado na Task 10)."""
    raise NotImplementedError
