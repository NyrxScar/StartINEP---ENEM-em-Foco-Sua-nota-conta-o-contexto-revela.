/**
 * `IndicadoresChave` — os numeros de cabecalho de um resultado.
 *
 * Decisoes:
 *
 * 1. **Uma superficie dividida por fios, nao quatro cartoes.** Cabecalho de
 *    relatorio estatistico: os quatro numeros pertencem a mesma consulta e sao
 *    lidos em conjunto, entao dar a cada um moldura e sombra proprias sugeriria
 *    quatro fontes independentes. A divisao vira linha horizontal no empilhamento
 *    de telas estreitas (regra `.indicadores` em `styles.css`).
 * 2. **So entra o que a API mediu.** Nao ha "media do ENEM", "escolas
 *    analisadas" nem "taxa de participacao" aqui: a API responde distribuicao,
 *    percentil e tamanho amostral de um recorte, e nada alem disso seria numero
 *    observado. Um indicador inventado em um produto de dados publicos custa
 *    mais caro do que um espaco vazio.
 * 3. **Uma lista de descricoes, nao `<div>`s.** `<dl>`/`<dt>`/`<dd>` e a
 *    semantica exata de "rotulo e valor" e da a leitores de tela o pareamento
 *    sem nenhum ARIA extra.
 */

import { FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import type { ResultadoAnalise } from '@/lib/tipos';

export interface IndicadoresChaveProps {
  resultado: ResultadoAnalise;
}

interface Indicador {
  rotulo: string;
  valor: string;
  /** Unidade exibida em corpo menor ao lado do numero. */
  unidade?: string;
  nota: string;
  /** O indicador que responde a pergunta da pessoa recebe o ocre. */
  destaque?: boolean;
}

export default function IndicadoresChave({ resultado }: IndicadoresChaveProps) {
  const { distribuicao, percentil, tamanho_amostral: amostra } = resultado;

  const indicadores: Indicador[] = [
    {
      rotulo: 'Seu percentil',
      valor: percentil !== null ? FORMATO_UMA_CASA.format(percentil) : 'suprimido',
      unidade: percentil !== null ? '%' : undefined,
      nota:
        percentil !== null
          ? 'da sua nota para baixo no grupo'
          : 'grupo pequeno demais para divulgar',
      destaque: true,
    },
    {
      rotulo: 'Tamanho do grupo',
      valor: amostra !== null ? FORMATO_INTEIRO.format(amostra) : 'suprimido',
      nota: amostra !== null ? 'pessoas com nota valida' : 'abaixo do limiar de divulgacao',
    },
    {
      rotulo: 'Mediana do grupo',
      valor:
        distribuicao !== null
          ? FORMATO_UMA_CASA.format(distribuicao.quantis.mediana)
          : 'suprimida',
      nota: 'metade do grupo ficou abaixo',
    },
    {
      rotulo: 'Intervalo central',
      valor:
        distribuicao !== null
          ? `${FORMATO_UMA_CASA.format(distribuicao.quantis.q1)}–${FORMATO_UMA_CASA.format(
              distribuicao.quantis.q3,
            )}`
          : 'suprimido',
      nota: 'onde estao os 50% do meio',
    },
  ];

  return (
    <dl className="indicadores grid overflow-hidden rounded-[4px] border border-line bg-surface md:grid-cols-4">
      {indicadores.map((indicador) => (
        <div key={indicador.rotulo} className="px-5 py-4">
          <dt className="text-[12px] font-medium text-ink-60">{indicador.rotulo}</dt>
          <dd className="mt-1.5">
            <span
              className={`numerico font-display text-[26px] leading-none ${
                indicador.destaque === true ? 'text-voce' : 'text-ink'
              }`}
            >
              {indicador.valor}
            </span>
            {indicador.unidade !== undefined && (
              <span
                className={`ml-0.5 text-base ${
                  indicador.destaque === true ? 'text-voce' : 'text-ink-60'
                }`}
              >
                {indicador.unidade}
              </span>
            )}
            <span className="mt-1 block text-xs text-ink-40">{indicador.nota}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
