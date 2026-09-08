# ADR-0004 — Deriva de schema entre edições do ENEM e o contrato com `ausentes`

**Status:** Aceito
**Data:** 2026-09-08
**Decisores:** equipe StartINEP

## Contexto

O plano de trabalho original assumia que cada edição do ENEM chegaria como um
único CSV de microdados contendo, na mesma linha, o perfil socioeconômico do
participante (questionário Q001–Q025, tipo de escola, faixa etária, sexo,
cor/raça) e o resultado da prova (presença por área e as cinco notas). Isso é
verdade para 2023, mas deixou de ser verdade a partir de 2024.

Inspecionando os três ZIPs já baixados em `data/bronze/` (sem re-download —
o servidor do INEP limita a taxa de requisições):

| Edição | Estrutura real dentro do ZIP | Notas | Socioeconômico | Vínculo |
|---|---|---|---|---|
| 2023 | `DADOS/MICRODADOS_ENEM_2023.csv` (arquivo único, 76 colunas) | ✅ | ✅ | ✅ mesma linha |
| 2024 | `DADOS/PARTICIPANTES_2024.csv` (38 colunas) + `DADOS/RESULTADOS_2024.csv` (42 colunas) | ✅ só em RESULTADOS | ✅ só em PARTICIPANTES | ❌ rompido |
| 2025 | `DADOS/PARTICIPANTES_2025.csv` apenas (38 colunas) | ❌ nenhuma | ✅ | — |

**Evidência de que o vínculo de 2024 está de fato rompido, não apenas
reorganizado:**

- Os dois arquivos de 2024 têm exatamente 4.332.944 linhas de dados cada
  (contagem direta dos CSVs dentro do ZIP, sem cabeçalho).
- Usam chaves diferentes: `PARTICIPANTES_2024.csv` é indexado por
  `NU_INSCRICAO`; `RESULTADOS_2024.csv` é indexado por `NU_SEQUENCIAL`. Não há
  coluna em comum entre os dois arquivos.
- As ordens das linhas divergem: a segunda linha (primeiro registro de dados)
  de `RESULTADOS_2024.csv` é de Aratuba/CE; a segunda linha de
  `PARTICIPANTES_2024.csv` é de Porto Alegre/RS. Se as duas populações
  estivessem na mesma ordem — a única forma de juntá-las sem uma chave comum
  seria por posição — a primeira linha de dados seria da mesma pessoa nos dois
  arquivos. Não é. Isso refuta qualquer tentativa de join posicional.

Essa reestruturação não é um defeito de publicação nem uma chave que ficou
faltando por acidente: é a des-identificação deliberada que o próprio
Relatório de Impacto à Proteção de Dados Pessoais (RIPD) dos microdados do
ENEM, publicado pelo INEP e já citado no plano de trabalho original,
descreve como medida de proteção — quebrar propositalmente o vínculo direto
entre quem a pessoa é (perfil) e o que ela tirou (nota) em uma única linha
seguindo a mesma chave, distribuindo os dois em populações com chaves e
ordens diferentes.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| Join posicional (linha N de PARTICIPANTES = linha N de RESULTADOS) | Recuperaria o corte "nota × perfil" completo também em 2024; menor mudança de escopo | Refutado pela evidência (linha 1 de um é CE, do outro é RS); juntar duas pessoas diferentes como se fossem uma fabricaria dados falsos, o oposto do que o projeto promete entregar | **Rejeitada** |
| Escopo 2022+2023 apenas | Evita lidar com a deriva de schema; ambas as edições têm arquivo único | Abandona as duas edições mais recentes (2024 e 2025), que são as que mais importam para um produto de "sua nota, seu contexto" atual | **Rejeitada** |
| Só 2024, com produto reduzido (sem os recortes socioeconômicos) | Mantém uma edição recente; simplifica o contrato para uma capacidade só | Descarta justamente os recortes de renda, escolaridade dos pais e tipo de escola que dão ao projeto seu propósito (mostrar como contexto socioeconômico se relaciona com a nota); um produto sem esses recortes não é o produto proposto | **Rejeitada** |
| Três edições (2023, 2024, 2025), cada uma com sua capacidade declarada via `ausentes` | Preserva o máximo de dado real e verificável em cada edição; nenhuma edição finge ter o que não tem; a lacuna vira documentação obrigatória (justificativa) em vez de ficar implícita | Contratos maiores e mais colunas para acompanhar; consultas cross-edição precisam tratar `NULL`s reais, não apenas dados ausentes por não-resposta do participante | **Escolhida** |

Também foi cogitada — e rejeitada antes de chegar à tabela acima — a ideia de
"grupos de capacidade" (ex.: grupo socioeconômico, grupo escola, grupo notas)
como forma de simplificar a declaração de ausência por categoria em vez de por
coluna individual. A granularidade não fecha: `tipo_escola` existe só em 2023,
enquanto `dependencia_adm_escola` existe em 2023 *e* em 2024 — as duas
cairiam no mesmo grupo "escola" mas têm disponibilidade diferente entre
edições. Só a declaração por coluna individual representa a realidade sem
perder informação.

## Decisão

O escopo do Sprint 1 passa a três edições — 2023, 2024 (apenas
`RESULTADOS_2024.csv`) e 2025 (`PARTICIPANTES_2025.csv`) — cada uma com um
contrato próprio (`enem_2023.yml`, `enem_2024.yml`, `enem_2025.yml`) que
declara exatamente o que aquela edição pode fornecer.

`PARTICIPANTES_2024.csv` não é ingerido. Ingerir os dois arquivos de 2024
criaria duas populações disjuntas do mesmo ano no mesmo pipeline, sem forma
válida de relacionar uma pessoa presente em um arquivo com a mesma pessoa no
outro — o que tornaria qualquer recorte cruzado (por exemplo, nota por faixa
de renda) construído com dados de 2024 estatisticamente inválido por
construção, mesmo que o pipeline rodasse sem erro.

O schema canônico (`canonical.yml`) não muda: continua sendo o vocabulário
único e completo, a União de tudo que qualquer edição já ofereceu. O que
muda é o modelo de contrato (`ContratoEdicao`), que ganha o campo
`ausentes: dict[str, str]` — mapeando coluna canônica a uma justificativa
textual de por que aquela edição não pode fornecê-la. A validação cruzada em
`carregar_contrato` passa a exigir que toda coluna canônica apareça em
exatamente um dos três conjuntos — `mapeamento`, `derivadas` ou `ausentes` —
nunca em nenhum, nunca em mais de um, e nunca com uma justificativa vazia.
Ausência tem que ser declarada e justificada; nunca silenciosa. Na camada
Prata, toda coluna listada em `ausentes` é materializada como `NULL` do tipo
declarado no schema canônico, em vez de a coluna simplesmente não existir na
tabela daquela edição — o que manteria o schema físico estável entre edições
e tornaria explícito, linha a linha, o que é "não sei" (ausência estrutural
de 2024/2025) versus "não respondeu" (não-resposta do participante em 2023).

## Consequências

**Fica mais fácil:**
- Auditar exatamente o que cada edição pode e não pode sustentar, lendo um
  único arquivo YAML por edição — a justificativa de cada `ausentes` é, por
  construção, a evidência da deriva de schema que o critério de aceite do
  projeto (AV3) exige, e a matéria-prima direta deste ADR.
- Adicionar uma quarta edição no futuro sem reabrir esta decisão: o mecanismo
  de `ausentes` já existe e generaliza para qualquer nova lacuna de
  capacidade, sem exigir uma nova categoria de "grupo" ad-hoc.
- Detectar contradição do próprio autor do contrato cedo: declarar uma coluna
  ao mesmo tempo como mapeada e como ausente, ou deixar uma justificativa em
  branco, falha a validação em vez de silenciosamente escolher um dos dois.

**Fica mais difícil:**
- Qualquer consulta ou visualização que cruze recortes socioeconômicos com
  notas precisa primeiro filtrar por edição (ou verificar `ausentes`) antes de
  assumir que a coluna existe com dado real — uma consulta ingênua sobre
  `renda_familiar` e `nota_mt` juntas em 2024 retornaria só `NULL`s em vez de
  um erro, porque a Prata materializa a ausência como `NULL` estrutural.
- O portão de volume (Task 10) não pode mais comparar cada edição com a
  imediatamente anterior por padrão: 2024-RESULTADOS só é comparável a 2023
  nas colunas que ambos têm; comparar 2025-PARTICIPANTES com 2024-RESULTADOS
  mediria populações e capacidades diferentes.

**Risco aceito:**
- O produto de 2024 e 2025 é estruturalmente mais pobre que o de 2023 nos
  recortes que dependem de cruzar perfil com nota, e isso é permanente — não
  um problema temporário de ingestão a ser corrigido depois. Qualquer
  interface ou relatório que use dados de 2024/2025 precisa comunicar essa
  limitação ao usuário final, em vez de apresentar as três edições como
  equivalentes em profundidade analítica.
