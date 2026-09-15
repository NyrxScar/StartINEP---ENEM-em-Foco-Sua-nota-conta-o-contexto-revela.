/**
 * Cliente HTTP tipado da API `radar_api` (Radar ENEM).
 *
 * Regras de projeto:
 *
 * 1. **URL base por ambiente** — lida de `NEXT_PUBLIC_API_URL`, com default de
 *    desenvolvimento `http://localhost:8000`. Nenhuma URL de producao e
 *    embutida no codigo (design, secao Implantacao: configuracao por variaveis
 *    de ambiente).
 * 2. **O envelope de erro e preservado** — em qualquer resposta nao-OK, o corpo
 *    `{codigo, mensagem, detalhes}` e parseado e re-lancado como
 *    {@link ErroApi}, que carrega `codigo`/`mensagem`/`detalhes` e o status HTTP.
 *    A UI (tasks 12.2–12.4) ramifica por `codigo` — ex.: `RECORTE_INDISPONIVEL`
 *    para listar `detalhes.edicoes_que_suportam` (Req 2.6/4.3) — e nunca precisa
 *    interpretar texto livre.
 * 3. **Falhas sem envelope tambem sao tipadas** — erro de rede, timeout e
 *    respostas nao-JSON viram `ErroApi` com os codigos sinteticos
 *    {@link CODIGO_ERRO_REDE}, {@link CODIGO_TIMEOUT} e
 *    {@link CODIGO_RESPOSTA_INVALIDA}, para que o consumidor tenha um unico tipo
 *    de erro a tratar.
 *
 * Este modulo e isomorfico (usa apenas `fetch`/`AbortSignal`): serve tanto a
 * Server Components quanto a Client Components.
 */

import type {
  Capacidade,
  EnvelopeErro,
  InfoEdicao,
  Recorte,
  RequisicaoAnalise,
  RequisicaoComparacao,
  ResultadoAnalise,
  ResultadoComparacao,
  Saude,
} from './tipos';

/** URL base default para desenvolvimento local (uvicorn). */
export const URL_API_DEFAULT = 'http://localhost:8000';

/** Timeout por requisicao, alinhado ao `RADAR_TIMEOUT_CONSULTA_S` da API (30s). */
export const TIMEOUT_MS = 30_000;

/** Codigo sintetico: a API nao pode ser alcancada (DNS, conexao recusada, CORS). */
export const CODIGO_ERRO_REDE = 'ERRO_REDE';

/** Codigo sintetico: a requisicao excedeu {@link TIMEOUT_MS}. */
export const CODIGO_TIMEOUT = 'TIMEOUT';

/** Codigo sintetico: a resposta nao trouxe um envelope/JSON interpretavel. */
export const CODIGO_RESPOSTA_INVALIDA = 'RESPOSTA_INVALIDA';

/**
 * URL base da API, sem barra final.
 *
 * `process.env.NEXT_PUBLIC_API_URL` e substituido no build pelo Next para o
 * bundle do cliente; no servidor e lido do ambiente do processo.
 */
export function urlBase(): string {
  const configurada = process.env.NEXT_PUBLIC_API_URL;
  const bruta = configurada && configurada.length > 0 ? configurada : URL_API_DEFAULT;
  return bruta.replace(/\/+$/, '');
}

/**
 * Erro tipado que **preserva** o envelope legivel por maquina da API.
 *
 * Sempre lancado pelas funcoes deste modulo (nunca uma string), para que a UI
 * possa decidir por `codigo` e ler `detalhes` sem *parsing* de mensagem.
 */
export class ErroApi extends Error {
  /** Codigo da taxonomia da API, ou um dos codigos sinteticos deste modulo. */
  readonly codigo: EnvelopeErro['codigo'];

  /** Detalhes estruturados (ex.: `edicoes_que_suportam`). Nunca `undefined`. */
  readonly detalhes: Record<string, unknown>;

  /** Status HTTP da resposta; `0` quando a requisicao nao chegou a completar. */
  readonly status: number;

  /** `true` quando o corpo veio no formato `{codigo, mensagem, detalhes}`. */
  readonly temEnvelope: boolean;

  constructor(params: {
    codigo: EnvelopeErro['codigo'];
    mensagem: string;
    detalhes?: Record<string, unknown>;
    status?: number;
    temEnvelope?: boolean;
    causa?: unknown;
  }) {
    super(params.mensagem, { cause: params.causa });
    this.name = 'ErroApi';
    this.codigo = params.codigo;
    this.detalhes = params.detalhes ?? {};
    this.status = params.status ?? 0;
    this.temEnvelope = params.temEnvelope ?? false;
  }

  /** A mensagem da API (alias de `message`, no vocabulario do envelope). */
  get mensagem(): string {
    return this.message;
  }

  /** O envelope original, reconstruido. */
  envelope(): EnvelopeErro {
    return { codigo: this.codigo, mensagem: this.message, detalhes: this.detalhes };
  }
}

/** Type guard: o valor e um {@link ErroApi}? */
export function ehErroApi(valor: unknown): valor is ErroApi {
  return valor instanceof ErroApi;
}

/** Verifica se um corpo desconhecido tem a forma do envelope de erro. */
function ehEnvelope(corpo: unknown): corpo is EnvelopeErro {
  if (typeof corpo !== 'object' || corpo === null) return false;
  const candidato = corpo as Record<string, unknown>;
  return typeof candidato.codigo === 'string' && typeof candidato.mensagem === 'string';
}

/** Extrai `detalhes` do envelope de forma defensiva (a API sempre envia objeto). */
function detalhesDe(envelope: EnvelopeErro): Record<string, unknown> {
  const detalhes = envelope.detalhes as unknown;
  return typeof detalhes === 'object' && detalhes !== null
    ? (detalhes as Record<string, unknown>)
    : {};
}

/** Opcoes de uma chamada: permite abortar/propagar cache do Next. */
export interface OpcoesRequisicao {
  signal?: AbortSignal;
  /** Repassado ao `fetch` do Next (default `no-store`: dados sempre frescos). */
  cache?: RequestCache;
}

/**
 * Executa uma requisicao e devolve o corpo JSON tipado.
 *
 * @throws {ErroApi} Em qualquer resposta nao-OK (com o envelope preservado), em
 *   falha de rede, timeout ou corpo nao interpretavel.
 */
async function requisitar<T>(
  caminho: string,
  init: RequestInit,
  opcoes: OpcoesRequisicao = {},
): Promise<T> {
  const resposta = await enviar(caminho, init, opcoes);
  const corpo = await lerJson(resposta);

  if (!resposta.ok) {
    throw erroDaResposta(resposta, corpo);
  }
  return corpo as T;
}

/** Dispara o `fetch` com timeout, traduzindo falhas de transporte em `ErroApi`. */
async function enviar(
  caminho: string,
  init: RequestInit,
  opcoes: OpcoesRequisicao,
): Promise<Response> {
  const controlador = new AbortController();
  const temporizador = setTimeout(() => controlador.abort(), TIMEOUT_MS);
  const abortoExterno = () => controlador.abort();
  opcoes.signal?.addEventListener('abort', abortoExterno);

  try {
    return await fetch(`${urlBase()}${caminho}`, {
      ...init,
      cache: opcoes.cache ?? 'no-store',
      signal: controlador.signal,
    });
  } catch (causa) {
    if (opcoes.signal?.aborted) {
      throw new ErroApi({
        codigo: CODIGO_ERRO_REDE,
        mensagem: 'A requisicao foi cancelada.',
        causa,
      });
    }
    if (controlador.signal.aborted) {
      throw new ErroApi({
        codigo: CODIGO_TIMEOUT,
        mensagem: `A API nao respondeu em ${TIMEOUT_MS / 1000} segundos.`,
        detalhes: { timeout_ms: TIMEOUT_MS },
        causa,
      });
    }
    throw new ErroApi({
      codigo: CODIGO_ERRO_REDE,
      mensagem: 'Nao foi possivel contatar a API do Radar ENEM.',
      detalhes: { url_base: urlBase() },
      causa,
    });
  } finally {
    clearTimeout(temporizador);
    opcoes.signal?.removeEventListener('abort', abortoExterno);
  }
}

/** Le o corpo como JSON; `undefined` quando vazio ou nao-JSON. */
async function lerJson(resposta: Response): Promise<unknown> {
  const texto = await resposta.text();
  if (texto.length === 0) return undefined;
  try {
    return JSON.parse(texto) as unknown;
  } catch {
    return undefined;
  }
}

/** Constroi o `ErroApi` de uma resposta nao-OK, preservando o envelope. */
function erroDaResposta(resposta: Response, corpo: unknown): ErroApi {
  if (ehEnvelope(corpo)) {
    return new ErroApi({
      codigo: corpo.codigo,
      mensagem: corpo.mensagem,
      detalhes: detalhesDe(corpo),
      status: resposta.status,
      temEnvelope: true,
    });
  }
  return new ErroApi({
    codigo: CODIGO_RESPOSTA_INVALIDA,
    mensagem: `A API respondeu ${resposta.status} sem envelope de erro.`,
    detalhes: { status: resposta.status, corpo },
    status: resposta.status,
  });
}

/** Monta o `init` de um POST JSON. */
function postJson(corpo: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(corpo),
  };
}

/** Recorte vazio: analise sobre toda a edicao (Req 1.3). */
export function recorteVazio(): Recorte {
  return { filtros: {} };
}

/**
 * `POST /v1/analise` — distribuicao e percentil da nota dentro do recorte
 * (Req 1.1). O resultado sempre carrega `capacidade` (Req 2.5) e `linhagem`
 * (Req 5.1); quando o recorte e pequeno, vem com
 * `estatisticamente_insuficiente = true` e detalhes nulos (Req 1.6).
 *
 * @throws {ErroApi} `NOTA_FORA_INTERVALO`, `AREA_INVALIDA`, `EDICAO_AUSENTE`,
 *   `EDICAO_SEM_NOTAS`, `PERFIL_NOTA_NAO_COMBINAVEL`, `RECORTE_INDISPONIVEL`.
 */
export function analisar(
  requisicao: RequisicaoAnalise,
  opcoes?: OpcoesRequisicao,
): Promise<ResultadoAnalise> {
  return requisitar<ResultadoAnalise>('/v1/analise', postJson(requisicao), opcoes);
}

/**
 * `POST /v1/comparacao` — um resultado por edicao elegivel, mais as `omissoes`
 * com motivo (Req 3). Endpoint em implementacao no backend (task 8.2); o cliente
 * ja segue o contrato do design.
 *
 * @throws {ErroApi} `COMPARACAO_SEM_EDICOES_ELEGIVEIS` quando nenhuma edicao
 *   solicitada e elegivel (Req 3.3).
 */
export function comparar(
  requisicao: RequisicaoComparacao,
  opcoes?: OpcoesRequisicao,
): Promise<ResultadoComparacao> {
  return requisitar<ResultadoComparacao>('/v1/comparacao', postJson(requisicao), opcoes);
}

/** `GET /v1/edicoes` — edicoes disponiveis com manifesto e data de carga (Req 5.2). */
export function listarEdicoes(opcoes?: OpcoesRequisicao): Promise<InfoEdicao[]> {
  return requisitar<InfoEdicao[]>('/v1/edicoes', { method: 'GET' }, opcoes);
}

/**
 * `GET /v1/edicoes/{edicao}/capacidade` — capacidade derivada do contrato,
 * usada pelo formulario para filtrar dimensoes e desabilitar areas sem notas
 * (Req 4.1/4.6).
 *
 * @throws {ErroApi} `EDICAO_AUSENTE` quando a edicao nao existe na silver.
 */
export function obterCapacidade(
  edicao: number,
  opcoes?: OpcoesRequisicao,
): Promise<Capacidade> {
  return requisitar<Capacidade>(
    `/v1/edicoes/${encodeURIComponent(String(edicao))}/capacidade`,
    { method: 'GET' },
    opcoes,
  );
}

/**
 * `GET /health` — readiness da API.
 *
 * Diferente dos demais: o status `503` (silver inacessivel) **nao** e um
 * envelope de erro, e sim o proprio corpo de saude com `status: "degradado"`.
 * Por isso o corpo e aceito em 200 e 503; apenas falhas de transporte ou
 * respostas sem corpo valido produzem {@link ErroApi}.
 */
export async function verificarSaude(opcoes?: OpcoesRequisicao): Promise<Saude> {
  const resposta = await enviar('/health', { method: 'GET' }, opcoes ?? {});
  const corpo = await lerJson(resposta);

  if (typeof corpo === 'object' && corpo !== null && 'status' in corpo) {
    return corpo as Saude;
  }
  throw new ErroApi({
    codigo: CODIGO_RESPOSTA_INVALIDA,
    mensagem: `O health-check respondeu ${resposta.status} com corpo inesperado.`,
    detalhes: { status: resposta.status, corpo },
    status: resposta.status,
  });
}
