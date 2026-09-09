# Dicionário de Dados — Schema Canônico

Schema canônico v1, 21 colunas. Gerado a partir de
`pipeline/src/radar_etl/contracts/` em 08/09/2026.

Cada edição do ENEM é traduzida para este vocabulário por um contrato YAML próprio.
`—` significa que a coluna foi declarada **ausente** naquela edição: ela existe no
schema, sai como NULL tipado na camada Prata, e a justificativa está registrada abaixo.

## Cobertura por edição

| Campo canônico | Tipo | 2023 | 2024 | 2025 | Descrição |
|---|---|---|---|---|---|
| `ano` | SMALLINT | `NU_ANO` | `NU_ANO` | `NU_ANO` | Ano da edicao do ENEM. Coluna de particao. |
| `uf_prova` | VARCHAR | `SG_UF_PROVA` | `SG_UF_PROVA` | `SG_UF_PROVA` | Sigla da UF onde o participante realizou a prova. Coluna de particao. |
| `regiao` | VARCHAR | _derivada_ | _derivada_ | _derivada_ | Macrorregiao (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) derivada de uf_prova. |
| `faixa_etaria` | TINYINT | `TP_FAIXA_ETARIA` | — | `TP_FAIXA_ETARIA` | Codigo da faixa etaria do participante, conforme dicionario do INEP. |
| `sexo` | VARCHAR | `TP_SEXO` | — | `TP_SEXO` | Sexo declarado (M/F). |
| `cor_raca` | TINYINT | `TP_COR_RACA` | — | `TP_COR_RACA` | Codigo de cor/raca autodeclarada, conforme dicionario do INEP. |
| `tipo_escola` | TINYINT | `TP_ESCOLA` | — | — | Tipo de escola do ensino medio (publica, privada, exterior, nao respondeu). |
| `dependencia_adm_escola` | TINYINT | `TP_DEPENDENCIA_ADM_ESC` | `TP_DEPENDENCIA_ADM_ESC` | — | Dependencia administrativa da escola (federal, estadual, municipal, privada). |
| `treineiro` | BOOLEAN | `IN_TREINEIRO` | — | `IN_TREINEIRO` | Participante fez a prova como treineiro. |
| `renda_familiar` | VARCHAR | `Q006` | — | `Q006` | Faixa de renda familiar mensal declarada no questionario socioeconomico (Q006). |
| `escolaridade_pai` | VARCHAR | `Q001` | — | `Q001` | Escolaridade do pai declarada no questionario socioeconomico. |
| `escolaridade_mae` | VARCHAR | `Q002` | — | `Q002` | Escolaridade da mae declarada no questionario socioeconomico. |
| `presenca_cn` | TINYINT | `TP_PRESENCA_CN` | `TP_PRESENCA_CN` | — | Situacao de presenca em Ciencias da Natureza (0 faltou, 1 presente, 2 eliminado). |
| `presenca_ch` | TINYINT | `TP_PRESENCA_CH` | `TP_PRESENCA_CH` | — | Situacao de presenca em Ciencias Humanas. |
| `presenca_lc` | TINYINT | `TP_PRESENCA_LC` | `TP_PRESENCA_LC` | — | Situacao de presenca em Linguagens e Codigos. |
| `presenca_mt` | TINYINT | `TP_PRESENCA_MT` | `TP_PRESENCA_MT` | — | Situacao de presenca em Matematica. |
| `nota_cn` | FLOAT | `NU_NOTA_CN` | `NU_NOTA_CN` | — | Nota de Ciencias da Natureza (0-1000). Nula para ausentes e eliminados. |
| `nota_ch` | FLOAT | `NU_NOTA_CH` | `NU_NOTA_CH` | — | Nota de Ciencias Humanas (0-1000). Nula para ausentes e eliminados. |
| `nota_lc` | FLOAT | `NU_NOTA_LC` | `NU_NOTA_LC` | — | Nota de Linguagens e Codigos (0-1000). Nula para ausentes e eliminados. |
| `nota_mt` | FLOAT | `NU_NOTA_MT` | `NU_NOTA_MT` | — | Nota de Matematica (0-1000). Nula para ausentes e eliminados. |
| `nota_redacao` | FLOAT | `NU_NOTA_REDACAO` | `NU_NOTA_REDACAO` | — | Nota da redacao (0-1000). Nula para ausentes e eliminados. |


### Ausentes em 2024

- **`faixa_etaria`** — TP_FAIXA_ETARIA nao esta em RESULTADOS_2024.csv; vive em PARTICIPANTES_2024.csv, que usa NU_INSCRICAO como chave (RESULTADOS usa NU_SEQUENCIAL) e por isso nao e juntavel a esta edicao. Ver ADR-0004.
- **`sexo`** — TP_SEXO nao esta em RESULTADOS_2024.csv; vive em PARTICIPANTES_2024.csv, que o INEP publica com chave propria (NU_INSCRICAO) desassociada da chave de RESULTADOS (NU_SEQUENCIAL), sem coluna em comum para o join. Ver ADR-0004.
- **`cor_raca`** — TP_COR_RACA nao esta em RESULTADOS_2024.csv; vive em PARTICIPANTES_2024.csv, cuja chave (NU_INSCRICAO, ordenada) nao corresponde a chave de RESULTADOS (NU_SEQUENCIAL, embaralhada) — nao ha como relacionar as duas linhas. Ver ADR-0004.
- **`tipo_escola`** — TP_ESCOLA nao existe em nenhuma das 42 colunas de RESULTADOS_2024.csv (so TP_DEPENDENCIA_ADM_ESC sobrevive nesse arquivo); o tipo de escola do ensino medio propriamente dito ficou em PARTICIPANTES_2024.csv, inacessivel a partir das notas nesta edicao. Ver ADR-0004.
- **`treineiro`** — IN_TREINEIRO nao esta em RESULTADOS_2024.csv; vive em PARTICIPANTES_2024.csv, que nao e ingerido porque sua chave (NU_INSCRICAO) nao se junta a chave de RESULTADOS (NU_SEQUENCIAL). Ver ADR-0004.
- **`renda_familiar`** — Q006 (renda familiar) faz parte do questionario socioeconomico, que o INEP moveu inteiro para PARTICIPANTES_2024.csv a partir de 2024. Esse arquivo nao e ingerido porque nao ha chave em comum com RESULTADOS_2024.csv para juntar renda a nota. Ver ADR-0004.
- **`escolaridade_pai`** — Q001 (escolaridade do pai) faz parte do questionario socioeconomico, publicado so em PARTICIPANTES_2024.csv a partir de 2024. Sem chave em comum com RESULTADOS_2024.csv, essa resposta nao pode ser associada a nota do participante nesta edicao. Ver ADR-0004.
- **`escolaridade_mae`** — Q002 (escolaridade da mae) faz parte do questionario socioeconomico, publicado so em PARTICIPANTES_2024.csv a partir de 2024. Sem chave em comum com RESULTADOS_2024.csv, essa resposta nao pode ser associada a nota do participante nesta edicao. Ver ADR-0004.

### Ausentes em 2025

- **`tipo_escola`** — TP_ESCOLA nao existe entre as 38 colunas de PARTICIPANTES_2025.csv. O INEP nao publicou, para 2025, um arquivo com os dados de escola do ensino medio equivalentes ao que MICRODADOS_ENEM_2023 trazia. Ver ADR-0004.
- **`dependencia_adm_escola`** — TP_DEPENDENCIA_ADM_ESC nao existe entre as 38 colunas de PARTICIPANTES_2025.csv. Assim como TP_ESCOLA, os dados de escola nao foram publicados para esta edicao. Ver ADR-0004.
- **`presenca_cn`** — TP_PRESENCA_CN nao esta em PARTICIPANTES_2025.csv. Ate a data deste contrato o INEP nao publicou um RESULTADOS_2025.csv (nao existe no ZIP); presenca e nota so existem uma vez que essa segunda parte da edicao seja disponibilizada. Ver ADR-0004.
- **`presenca_ch`** — TP_PRESENCA_CH nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de TP_PRESENCA_CN: nao ha RESULTADOS_2025.csv publicado nesta edicao. Ver ADR-0004.
- **`presenca_lc`** — TP_PRESENCA_LC nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de TP_PRESENCA_CN: nao ha RESULTADOS_2025.csv publicado nesta edicao. Ver ADR-0004.
- **`presenca_mt`** — TP_PRESENCA_MT nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de TP_PRESENCA_CN: nao ha RESULTADOS_2025.csv publicado nesta edicao. Ver ADR-0004.
- **`nota_cn`** — NU_NOTA_CN nao esta em PARTICIPANTES_2025.csv. As notas ficariam num RESULTADOS_2025.csv que o INEP ainda nao publicou para esta edicao (nao consta no ZIP). Ver ADR-0004.
- **`nota_ch`** — NU_NOTA_CH nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de NU_NOTA_CN: o arquivo de resultados desta edicao nao foi publicado. Ver ADR-0004.
- **`nota_lc`** — NU_NOTA_LC nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de NU_NOTA_CN: o arquivo de resultados desta edicao nao foi publicado. Ver ADR-0004.
- **`nota_mt`** — NU_NOTA_MT nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de NU_NOTA_CN: o arquivo de resultados desta edicao nao foi publicado. Ver ADR-0004.
- **`nota_redacao`** — NU_NOTA_REDACAO nao esta em PARTICIPANTES_2025.csv pelo mesmo motivo de NU_NOTA_CN: o arquivo de resultados desta edicao nao foi publicado. Ver ADR-0004.

## Deriva de schema entre edições

A tabela acima é a evidência empírica da deriva. Três padrões distintos:

1. **2023 é a única edição completa.** Cobre as 21 colunas canônicas — é a base do
   produto, a única que permite cruzar nota com perfil socioeconômico.
2. **2024 perdeu o eixo socioeconômico.** 8 colunas ausentes, todas do questionário e da
   demografia. A causa é estrutural, não uma coluna renomeada.
3. **2025 perdeu o eixo de desempenho.** 11 colunas ausentes: as 5 notas, as 4 presenças
   e as 2 de escola. A edição foi publicada só com participantes.

`tipo_escola` (`TP_ESCOLA`) merece nota à parte: existe apenas em 2023. Nas edições
seguintes o INEP não republicou essa variável em nenhum dos arquivos — não é o mesmo
caso das outras, que existem mas em arquivo não-juntável.

## Nota de privacidade

`NU_INSCRICAO`, `NU_SEQUENCIAL` e demais identificadores **não entram** na camada Prata:
são descartados na projeção. A Prata não contém identificador de participante, e o
produto nunca persiste dados informados pelo usuário.

Isso é decisão de projeto, não consequência: reduz o volume e elimina a maior parte da
superfície de exposição LGPD de uma vez.

## Domínios dos códigos categóricos

Os códigos de `faixa_etaria`, `cor_raca`, `tipo_escola`, `dependencia_adm_escola`,
`renda_familiar` (Q006), `escolaridade_pai` (Q001) e `escolaridade_mae` (Q002) seguem o
dicionário oficial do INEP, distribuído dentro de cada ZIP em
`DICIONÁRIO/Dicionário_Microdados_Enem_<ANO>.xlsx`.

`presenca_*`: `0` faltou, `1` presente, `2` eliminado.
