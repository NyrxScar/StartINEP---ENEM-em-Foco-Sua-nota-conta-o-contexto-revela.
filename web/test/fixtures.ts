/**
 * Construtores de *fixtures* do contrato da API, para os testes de componente
 * (task 12.5).
 *
 * Por que construtores e nao objetos literais espalhados pelos testes: os tipos
 * de `lib/tipos.ts` sao o contrato serializado da API (muitos campos
 * obrigatorios, varios anulaveis). Um teste que precisa apenas de
 * `possui_notas: false` nao deveria repetir os outros dez campos — repeticao que
 * envelhece mal e esconde qual campo o teste realmente exercita.
 *
 * Cada construtor devolve um valor **valido e completo** e aceita
 * `sobrescritas` parciais: o que aparece na chamada e exatamente a condicao sob
 * teste. Os valores default sao deliberadamente "bem-comportados" (edicao 2023,
 * todas as dimensoes, amostra suficiente) para que o caso de borda esteja sempre
 * visivel no proprio teste.
 */

import type {
  Capacidade,
  Distribuicao,
  FaixaHistograma,
  InfoEdicao,
  Linhagem,
  ResultadoAnalise,
} from '@/lib/tipos';

/** Timestamp ISO 8601 de carga usado como default (sem fuso, como o Manifesto). */
export const DATA_CARGA_PADRAO = '2025-03-12T14:32:00';

/** Identificador de Manifesto usado como default. */
export const MANIFESTO_PADRAO = 'sha256:abc123';

/** Capacidade plena: todas as dimensoes, com notas e perfil combinavel. */
export function criarCapacidade(sobrescritas: Partial<Capacidade> = {}): Capacidade {
  return {
    edicao: 2023,
    dimensoes_suportadas: [
      'regiao',
      'uf_prova',
      'tipo_escola',
      'dependencia_adm_escola',
      'renda_familiar',
      'cor_raca',
      'escolaridade_pai',
      'escolaridade_mae',
    ],
    possui_notas: true,
    perfil_combinavel_com_notas: true,
    ...sobrescritas,
  };
}

/**
 * Uma edicao do catalogo `GET /v1/edicoes`. A capacidade default acompanha a
 * edicao informada, para que `capacidade.edicao` nunca contradiga `edicao`.
 */
export function criarInfoEdicao(sobrescritas: Partial<InfoEdicao> = {}): InfoEdicao {
  const edicao = sobrescritas.edicao ?? 2023;
  return {
    edicao,
    manifesto_id: MANIFESTO_PADRAO,
    data_carga: DATA_CARGA_PADRAO,
    capacidade: criarCapacidade({ edicao }),
    ...sobrescritas,
  };
}

/** Faixas default do histograma: 100 pessoas distribuidas em quatro faixas. */
export function criarFaixas(): FaixaHistograma[] {
  return [
    { limite_inferior: 300, limite_superior: 400, contagem: 10 },
    { limite_inferior: 400, limite_superior: 500, contagem: 30 },
    { limite_inferior: 500, limite_superior: 600, contagem: 40 },
    { limite_inferior: 600, limite_superior: 700, contagem: 20 },
  ];
}

/** Distribuicao coerente com {@link criarFaixas}. */
export function criarDistribuicao(sobrescritas: Partial<Distribuicao> = {}): Distribuicao {
  return {
    faixas: criarFaixas(),
    quantis: { minimo: 300, q1: 450, mediana: 520, q3: 610, maximo: 700 },
    ...sobrescritas,
  };
}

/** Linhagem de uma unica edicao, com Manifesto e data de carga presentes. */
export function criarLinhagem(sobrescritas: Partial<Linhagem> = {}): Linhagem {
  return {
    edicoes: [2023],
    manifestos: { '2023': MANIFESTO_PADRAO },
    datas_carga: { '2023': DATA_CARGA_PADRAO },
    ...sobrescritas,
  };
}

/** Resultado bem-sucedido: percentil 72,5 sobre uma amostra de 1.234 pessoas. */
export function criarResultado(sobrescritas: Partial<ResultadoAnalise> = {}): ResultadoAnalise {
  const edicao = sobrescritas.edicao ?? 2023;
  const chave = String(edicao);
  return {
    edicao,
    area: 'cn',
    distribuicao: criarDistribuicao(),
    percentil: 72.5,
    tamanho_amostral: 1234,
    estatisticamente_insuficiente: false,
    capacidade: criarCapacidade({ edicao }),
    linhagem: criarLinhagem({
      edicoes: [edicao],
      manifestos: { [chave]: MANIFESTO_PADRAO },
      datas_carga: { [chave]: DATA_CARGA_PADRAO },
    }),
    ...sobrescritas,
  };
}

/**
 * Resultado suprimido pela guarda de privacidade (Req 1.6/4.4/9.3): a marca de
 * insuficiencia **e** os detalhes anulados, exatamente como a API responde.
 */
export function criarResultadoSuprimido(
  sobrescritas: Partial<ResultadoAnalise> = {},
): ResultadoAnalise {
  return criarResultado({
    distribuicao: null,
    percentil: null,
    tamanho_amostral: null,
    estatisticamente_insuficiente: true,
    ...sobrescritas,
  });
}
