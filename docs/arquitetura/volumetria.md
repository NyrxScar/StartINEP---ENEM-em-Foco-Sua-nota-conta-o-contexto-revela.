# Volumetria — Camada Bronze → Prata

Medição em 08/09/2026, com `radar-etl` v0.1.0, contrato v1.
Fonte dos números: manifestos em `data/_manifests/`, gerados pela própria execução.

## Resultado

| Edição | ZIP origem (MB) | CSV expandido / Bronze (MB) | Parquet+Snappy / Prata (MB) | Linhas | Redução vs. CSV |
|---|---:|---:|---:|---:|---:|
| 2023 | 524,1 | 1.694,8 | 29,8 | 3.933.955 | 98,2% |
| 2024 | 501,7 | 1.605,5 | 21,7 | 4.332.944 | 98,6% |
| 2025 | 518,4 | 489,3 | 0,8 | 4.810.772 | 99,8% |
| **Total** | **1.544,2** | **3.789,6** | **52,3** | **13.077.671** | **98,6%** |

**3,7 GB de CSV viram 52 MB de Parquet.** A base inteira cabe com folga em qualquer
free tier, e é isso que torna a hospedagem de custo zero viável.

## Justificativa técnica da redução

Três mecanismos, e vale separá-los porque têm pesos bem diferentes:

**1. Projeção de colunas — o maior ganho isolado.** O schema canônico retém 21 colunas.
A edição de 2023 traz 76 na origem, a de 2024 traz 42 e a de 2025 traz 38. Nenhuma
estatística do produto depende das demais: respostas item a item (`TX_RESPOSTAS_*`),
gabaritos (`TX_GABARITO_*`), códigos de prova e identificadores de município não são
consultados por nada na aplicação. Descartá-los na projeção elimina a maior parte do
volume antes de qualquer compressão.

**2. Tipagem.** No CSV tudo é texto: `712.4` ocupa 5 bytes. Em Parquet é um `FLOAT` de
4 bytes, e um código de faixa etária cabe em 1 byte como `TINYINT`.

**3. Compressão colunar Snappy.** Valores do mesmo tipo ficam adjacentes no arquivo, o
que eleva muito a taxa em colunas categóricas de baixa cardinalidade — UF, sexo,
cor/raça, faixa de renda.

Snappy foi escolhido em vez de Gzip por priorizar **velocidade de descompressão** sobre
taxa máxima: o artefato é escrito 3 vezes por semestre e lido a cada requisição de
usuário.

### Por que 2025 comprime tanto mais (99,8%)

Não é mérito do Parquet. A edição de 2025 publica apenas `PARTICIPANTES_2025.csv`, sem
nenhuma nota — 11 das 21 colunas canônicas são declaradas ausentes no contrato e saem
como NULL tipado. Uma coluna inteiramente nula custa quase nada em Parquet. O número é
verdadeiro, mas mede a incompletude da fonte, não a eficiência da compressão. Ver
[ADR-0004](../adr/0004-deriva-de-schema-entre-edicoes-do-enem.md).

Comparação honesta é entre 2023 (98,2%) e 2024 (98,6%), ambas com notas.

## Tempo e memória

| Edição | Tempo (wall clock) | Pico de RAM |
|---|---:|---:|
| 2023 | 0:38 | 771,5 MB |
| 2024 | 0:56 | 728,5 MB |
| 2025 | 0:43 | 730,0 MB |

Medido com `/usr/bin/time -v`.

**O pico de RAM é a evidência que sustenta a decisão arquitetural.** O CSV de 2024 tem
1.605 MB e o processo nunca passou de 728 MB — menos da metade do arquivo que estava
convertendo. A conversão acontece por streaming: o DuckDB lê o CSV em blocos e grava
Parquet em blocos, sem materializar a base.

Para contraste, `pandas.read_csv` sobre o mesmo arquivo exigiria tipicamente 2 a 4× o
tamanho em disco por causa do overhead de objetos Python em colunas textuais — algo
entre 3 e 6 GB só para manter a base viva, antes de qualquer cálculo. É a diferença
entre um pipeline que roda no notebook de qualquer integrante e um que não roda em
nenhum.

## Reprodução

```bash
cd pipeline
for ANO in 2023 2024 2025; do
  uv run radar-etl ingest --edicao $ANO --raiz ../data
done
```

Idempotência verificada: reexecutar sem `--forcar` é pulado por comparação de SHA-256 da
fonte; reexecutar com `--forcar` produz Parquet byte a byte idêntico
(`find ../data/silver -name '*.parquet' | sort | xargs sha256sum` antes e depois).
