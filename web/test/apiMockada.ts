/**
 * Controle do cliente de API mockado nos testes de componente (task 12.5).
 *
 * Decisoes:
 *
 * 1. **A rede nunca e tocada, mas o modulo nao e substituido por inteiro.** Cada
 *    arquivo de teste que monta um componente com efeitos declara, no topo:
 *
 *    ```ts
 *    vi.mock('@/lib/api', async (importOriginal) => {
 *      const real = await importOriginal<typeof import('@/lib/api')>();
 *      return { ...real, analisar: vi.fn(), listarEdicoes: vi.fn(), obterCapacidade: vi.fn() };
 *    });
 *    ```
 *
 *    Somente as tres funcoes que fazem `fetch` viram `vi.fn()`. Tudo o mais —
 *    a **classe `ErroApi` real** e os codigos sinteticos `ERRO_REDE`,
 *    `TIMEOUT`, `RESPOSTA_INVALIDA` — continua sendo o codigo de producao. Isso
 *    importa: `EstadoErro` ramifica por `erro.codigo` e le `erro.detalhes`, e
 *    `FormularioAnalise` usa `ehErroApi` (um `instanceof`). Um duble de `ErroApi`
 *    faria os testes passarem com um erro que nao e o erro do sistema.
 * 2. **A capacidade vem do proprio catalogo de edicoes.** `prepararApi` deriva a
 *    resposta de `obterCapacidade` da `InfoEdicao` correspondente, para que a
 *    fixture do teste tenha uma unica fonte de verdade sobre o que a edicao
 *    suporta — em vez de dois objetos que podem discordar.
 * 3. **`analisar` sem configuracao falha alto.** O default e uma rejeicao com
 *    mensagem explicita, para que um teste que dependa da analise sem prepara-la
 *    aponte o proprio esquecimento em vez de morrer com `undefined`.
 *
 * Este modulo so pode ser importado por arquivos que declararam o `vi.mock`
 * acima; sem ele, `vi.mocked(...)` devolveria as funcoes reais.
 */

import { vi } from 'vitest';

import { analisar, CODIGO_RESPOSTA_INVALIDA, ErroApi, listarEdicoes, obterCapacidade } from '@/lib/api';
import type { Capacidade, InfoEdicao } from '@/lib/tipos';

import { criarCapacidade, criarInfoEdicao } from './fixtures';

/** `POST /v1/analise` mockado. */
export const analisarMock = vi.mocked(analisar);

/** `GET /v1/edicoes` mockado. */
export const listarEdicoesMock = vi.mocked(listarEdicoes);

/** `GET /v1/edicoes/{edicao}/capacidade` mockado. */
export const obterCapacidadeMock = vi.mocked(obterCapacidade);

/** Cenario de API de um teste: o que a API responde antes da submissao. */
export interface CenarioApi {
  /** Catalogo devolvido por `listarEdicoes`. Default: uma edicao 2023 plena. */
  edicoes?: InfoEdicao[];
  /**
   * Capacidade devolvida por `obterCapacidade`, sobrepondo a do catalogo. O
   * campo `edicao` e reescrito com a edicao consultada, porque o formulario so
   * aceita a capacidade cuja edicao coincide com a selecionada.
   */
  capacidade?: Capacidade;
  /** Faz `listarEdicoes` rejeitar (degradacao sem API). */
  falhaEdicoes?: ErroApi;
  /** Faz `obterCapacidade` rejeitar (aviso de capacidade indeterminada). */
  falhaCapacidade?: ErroApi;
}

/**
 * Configura as respostas do catalogo e da capacidade. Deve ser chamada **dentro**
 * de cada teste: `restoreMocks: true` (vitest.config.ts) limpa as
 * implementacoes entre os testes, o que mantem cada cenario local e explicito.
 */
export function prepararApi(cenario: CenarioApi = {}): void {
  const edicoes = cenario.edicoes ?? [criarInfoEdicao()];
  const { falhaEdicoes, falhaCapacidade, capacidade } = cenario;

  listarEdicoesMock.mockImplementation(() =>
    falhaEdicoes !== undefined ? Promise.reject(falhaEdicoes) : Promise.resolve(edicoes),
  );

  obterCapacidadeMock.mockImplementation((edicao: number) => {
    if (falhaCapacidade !== undefined) return Promise.reject(falhaCapacidade);
    if (capacidade !== undefined) return Promise.resolve({ ...capacidade, edicao });
    const info = edicoes.find((candidata) => candidata.edicao === edicao);
    return Promise.resolve(info?.capacidade ?? criarCapacidade({ edicao }));
  });

  analisarMock.mockRejectedValue(
    new ErroApi({
      codigo: CODIGO_RESPOSTA_INVALIDA,
      mensagem: 'analisar() nao foi configurado neste teste.',
    }),
  );
}

/** Uma promessa cujo desfecho o teste decide, para observar estados em voo. */
export interface Diferido<T> {
  promessa: Promise<T>;
  resolver: (valor: T) => void;
  rejeitar: (causa: unknown) => void;
}

/**
 * Cria uma promessa pendente controlada pelo teste. Serve ao indicador de
 * carregamento (Req 4.5): o estado "em andamento" so e observavel enquanto a
 * requisicao nao terminou, e prender isso a um `setTimeout` seria um teste
 * lento e instavel.
 */
export function deferir<T>(): Diferido<T> {
  const controles: {
    resolver?: (valor: T) => void;
    rejeitar?: (causa: unknown) => void;
  } = {};
  const promessa = new Promise<T>((resolver, rejeitar) => {
    controles.resolver = resolver;
    controles.rejeitar = rejeitar;
  });
  return {
    promessa,
    resolver: (valor) => controles.resolver?.(valor),
    rejeitar: (causa) => controles.rejeitar?.(causa),
  };
}
