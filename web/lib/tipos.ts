/**
 * Tipos do contrato HTTP da API `radar_api` (Radar ENEM).
 *
 * Espelham 1:1 os modelos pydantic de `api/src/radar_api/modelos.py` e o
 * envelope de erro de `api/src/radar_api/erros.py`, na forma **serializada em
 * JSON**:
 *
 * - `Capacidade.dimensoes_suportadas` e um `set[Dimensao]` em Python, portanto
 *   chega como array de strings;
 * - `Linhagem.manifestos`/`datas_carga` sao `dict[int, ...]` em Python; chaves
 *   de objeto JSON sao sempre strings, logo `Record<string, ...>`;
 * - `datas_carga` carrega `datetime` serializado como string ISO 8601.
 *
 * Campos anulaveis (`distribuicao`, `percentil`, `tamanho_amostral`) refletem a
 * guarda de privacidade: quando o recorte cai abaixo do limiar de agregacao a
 * API anula os detalhes e marca `estatisticamente_insuficiente` (Req 1.6/9.3).
 */

/** Area de avaliacao do ENEM (sufixo da coluna `nota_<area>` na silver). */
export type Area = 'cn' | 'ch' | 'lc' | 'mt' | 'redacao';

/**
 * Dimensao de Recorte. Os valores sao os nomes **fisicos** das colunas
 * canonicas da silver, exatamente como o enum `Dimensao` do backend.
 */
export type Dimensao =
  | 'regiao'
  | 'uf_prova'
  | 'tipo_escola'
  | 'dependencia_adm_escola'
  | 'renda_familiar'
  | 'cor_raca'
  | 'escolaridade_pai'
  | 'escolaridade_mae';

/** Rotulos legiveis por humano para cada dimensao (uso do formulario, 12.2). */
export const ROTULOS_DIMENSAO: Record<Dimensao, string> = {
  regiao: 'Regiao',
  uf_prova: 'UF da prova',
  tipo_escola: 'Tipo de escola',
  dependencia_adm_escola: 'Dependencia administrativa',
  renda_familiar: 'Renda familiar',
  cor_raca: 'Cor/raca',
  escolaridade_pai: 'Escolaridade do pai',
  escolaridade_mae: 'Escolaridade da mae',
};

/** Rotulos legiveis por humano para cada area. */
export const ROTULOS_AREA: Record<Area, string> = {
  cn: 'Ciencias da Natureza',
  ch: 'Ciencias Humanas',
  lc: 'Linguagens e Codigos',
  mt: 'Matematica',
  redacao: 'Redacao',
};

/**
 * Conjunto de filtros aplicados de forma conjuntiva (AND).
 * `filtros` vazio significa "sem recorte" (toda a edicao) — Req 1.3/1.4.
 */
export interface Recorte {
  filtros: Partial<Record<Dimensao, string>>;
}

/** Corpo de `POST /v1/analise`. */
export interface RequisicaoAnalise {
  edicao: number;
  area: Area;
  /** Nota informada; a API exige 0..1000 inclusive (Req 1.8). */
  nota: number;
  recorte: Recorte;
}

/** Corpo de `POST /v1/comparacao` (2+ edicoes; Req 3). */
export interface RequisicaoComparacao {
  edicoes: number[];
  area: Area;
  nota: number;
  recorte: Recorte;
}

/** Resumo por quantis da distribuicao de notas de um recorte. */
export interface Quantis {
  minimo: number;
  q1: number;
  mediana: number;
  q3: number;
  maximo: number;
}

/** Uma faixa (bucket) do histograma da distribuicao. */
export interface FaixaHistograma {
  limite_inferior: number;
  limite_superior: number;
  contagem: number;
}

/** Distribuicao agregada: histograma + quantis. */
export interface Distribuicao {
  faixas: FaixaHistograma[];
  quantis: Quantis;
}

/** Capacidade analitica de uma edicao (Req 2.1/2.5). */
export interface Capacidade {
  edicao: number;
  dimensoes_suportadas: Dimensao[];
  possui_notas: boolean;
  perfil_combinavel_com_notas: boolean;
}

/**
 * Linhagem de uma resposta (Req 5.1). As chaves de `manifestos` e `datas_carga`
 * sao a edicao serializada como string (ex.: `"2023"`); os valores sao anulaveis
 * porque a silver e seus manifestos sao contrato de entrada externo.
 */
export interface Linhagem {
  edicoes: number[];
  manifestos: Record<string, string | null>;
  /** Timestamps ISO 8601 de carga, por edicao. */
  datas_carga: Record<string, string | null>;
}

/** Resultado de uma analise de recorte unico. */
export interface ResultadoAnalise {
  edicao: number;
  area: Area;
  distribuicao: Distribuicao | null;
  percentil: number | null;
  tamanho_amostral: number | null;
  estatisticamente_insuficiente: boolean;
  capacidade: Capacidade;
  linhagem: Linhagem;
}

/** Edicao omitida de uma comparacao, com o motivo legivel por maquina (Req 3.2). */
export interface OmissaoEdicao {
  edicao: number;
  codigo: string;
}

/** Resultado de uma comparacao entre edicoes. */
export interface ResultadoComparacao {
  resultados: ResultadoAnalise[];
  omissoes: OmissaoEdicao[];
}

/** Metadados de uma edicao disponivel na silver (`GET /v1/edicoes` — Req 5.2). */
export interface InfoEdicao {
  edicao: number;
  manifesto_id: string | null;
  /** Timestamp ISO 8601 da carga, ou `null` quando o manifesto esta ausente. */
  data_carga: string | null;
  capacidade: Capacidade;
}

/** Resposta de `GET /health` (readiness — Req 7.1). */
export interface Saude {
  status: 'ok' | 'degradado';
  silver_acessivel: boolean;
  edicoes: number[];
  ambiente_referencia: string;
}

/**
 * Codigos da taxonomia de erros da API. A uniao com `string` mantem o tipo
 * aberto: um codigo novo no backend nao quebra a compilacao do frontend, mas os
 * conhecidos ainda sao autocompletados e checados em `switch`.
 */
export type CodigoErro =
  | 'NOTA_FORA_INTERVALO'
  | 'AREA_INVALIDA'
  | 'RECORTE_INDISPONIVEL'
  | 'EDICAO_SEM_NOTAS'
  | 'PERFIL_NOTA_NAO_COMBINAVEL'
  | 'COMPARACAO_SEM_EDICOES_ELEGIVEIS'
  | 'EDICAO_AUSENTE'
  | 'MANIFESTO_AUSENTE'
  | 'MANIFESTO_INVALIDO'
  | 'CAPACIDADE_INDETERMINADA'
  | 'REQUISICAO_INVALIDA'
  | (string & {});

/**
 * Envelope de erro da API — **sempre** este formato em respostas 4xx
 * (422/404/409). `detalhes` e legivel por maquina; para
 * `RECORTE_INDISPONIVEL` traz `edicoes_que_suportam` (Req 2.6).
 */
export interface EnvelopeErro {
  codigo: CodigoErro;
  mensagem: string;
  detalhes: Record<string, unknown>;
}

/** Detalhes de `RECORTE_INDISPONIVEL` (Req 2.2/2.6, consumido pela UI 12.4). */
export interface DetalhesRecorteIndisponivel {
  dimensao?: string;
  edicao?: number;
  edicoes_que_suportam?: number[];
}
