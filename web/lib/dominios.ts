/**
 * Dominios de valores dos filtros de Recorte, para os controles do formulario.
 *
 * A API compara os filtros como texto contra a coluna fisica da *silver*
 * (`CAST(coluna AS VARCHAR) = ?`), e **nao** existe endpoint que enumere os
 * valores possiveis de cada dimensao. Portanto:
 *
 * - dimensoes cujo dominio e estavel e derivado da propria estrutura da silver
 *   ou do dicionario publico dos microdados (`regiao`, `uf_prova`, `tipo_escola`,
 *   `dependencia_adm_escola`, `localizacao_escola`, `cor_raca`) ganham um
 *   `<select>` com rotulos legiveis e o **valor fisico** como `value`;
 * - dimensoes cuja normalizacao a silver nao fixa no contrato
 *   (`renda_familiar`, `escolaridade_pai`, `escolaridade_mae` — derivadas de
 *   Q006/Q001/Q002) ficam sem lista e o formulario oferece um campo de texto;
 * - `municipio_prova` e `codigo_escola` tem dominio grande demais para uma lista
 *   estatica (mais de mil municipios por edicao, dezenas de milhares de escolas)
 *   e mudam a cada edicao. Ficam como entrada livre, e `POST /v1/exploracao`
 *   e o caminho para descobrir quais valores existem de fato.
 *
 * `regiao` segue os rotulos do ETL (`sql_case_regiao`): Norte, Nordeste,
 * Sudeste, Sul, Centro-Oeste.
 */

import type { Dimensao } from './tipos';

/** Uma opcao de filtro: `valor` vai para a API, `rotulo` para a pessoa. */
export interface OpcaoValor {
  valor: string;
  rotulo: string;
}

/** As cinco regioes, como o ETL as materializa a partir da UF. */
const REGIOES: OpcaoValor[] = [
  { valor: 'Norte', rotulo: 'Norte' },
  { valor: 'Nordeste', rotulo: 'Nordeste' },
  { valor: 'Sudeste', rotulo: 'Sudeste' },
  { valor: 'Sul', rotulo: 'Sul' },
  { valor: 'Centro-Oeste', rotulo: 'Centro-Oeste' },
];

/** As 27 unidades federativas; `uf_prova` e tambem chave de particao. */
const UFS: OpcaoValor[] = [
  'AC',
  'AL',
  'AM',
  'AP',
  'BA',
  'CE',
  'DF',
  'ES',
  'GO',
  'MA',
  'MG',
  'MS',
  'MT',
  'PA',
  'PB',
  'PE',
  'PI',
  'PR',
  'RJ',
  'RN',
  'RO',
  'RR',
  'RS',
  'SC',
  'SE',
  'SP',
  'TO',
].map((sigla) => ({ valor: sigla, rotulo: sigla }));

/**
 * Listas de valores por dimensao. Ausencia de entrada = dominio nao fixado pelo
 * contrato; o formulario cai para entrada livre de texto.
 */
export const OPCOES_DIMENSAO: Partial<Record<Dimensao, OpcaoValor[]>> = {
  regiao: REGIOES,
  uf_prova: UFS,
  tipo_escola: [
    { valor: '1', rotulo: 'Nao informado' },
    { valor: '2', rotulo: 'Publica' },
    { valor: '3', rotulo: 'Privada' },
  ],
  dependencia_adm_escola: [
    { valor: '1', rotulo: 'Federal' },
    { valor: '2', rotulo: 'Estadual' },
    { valor: '3', rotulo: 'Municipal' },
    { valor: '4', rotulo: 'Privada' },
  ],
  localizacao_escola: [
    { valor: '1', rotulo: 'Urbana' },
    { valor: '2', rotulo: 'Rural' },
  ],
  cor_raca: [
    { valor: '0', rotulo: 'Nao declarado' },
    { valor: '1', rotulo: 'Branca' },
    { valor: '2', rotulo: 'Preta' },
    { valor: '3', rotulo: 'Parda' },
    { valor: '4', rotulo: 'Amarela' },
    { valor: '5', rotulo: 'Indigena' },
    { valor: '6', rotulo: 'Nao dispoe da informacao' },
  ],
};

/**
 * Dimensoes de **perfil socioeconomico**. Quando a capacidade da edicao tem
 * `perfil_combinavel_com_notas = false` (caso de 2024, cujos arquivos de perfil
 * e de notas nao podem ser unidos), estas dimensoes nao podem entrar em uma
 * analise de nota — Req 2.4/9.2.
 */
export const DIMENSOES_PERFIL: readonly Dimensao[] = [
  'renda_familiar',
  'cor_raca',
  'escolaridade_pai',
  'escolaridade_mae',
];

/**
 * Dimensoes que descrevem a **escola** do participante, e nao ele proprio.
 *
 * Alimentam a secao de perfil de escola. `codigo_escola` identifica a
 * instituicao (so a edicao 2024 o publica); as demais a caracterizam sem
 * identificar. Todas dependem de a pessoa declarar vinculo escolar, o que cobre
 * entre um quinto e um terco dos participantes conforme a edicao — qualquer
 * leitura sobre elas vale para esse subconjunto, nunca para a edicao inteira.
 */
export const DIMENSOES_ESCOLA: readonly Dimensao[] = [
  'tipo_escola',
  'dependencia_adm_escola',
  'localizacao_escola',
  'codigo_escola',
];
