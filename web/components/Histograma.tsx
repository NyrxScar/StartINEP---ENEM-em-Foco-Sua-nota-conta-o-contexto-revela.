/**
 * `Histograma` — a distribuicao do grupo com a posicao da pessoa marcada.
 *
 * Este e o elemento dominante da interface, e de proposito: a tese do produto e
 * que uma nota isolada nao diz nada e que o contexto e a populacao em volta
 * dela. Por isso o grafico e servido sem moldura, ocupando a largura toda, e
 * tudo em volta permanece discreto.
 *
 * Decisoes:
 *
 * 1. **SVG escrito a mao, sem biblioteca de graficos.** O histograma ja chega
 *    pronto da API (`faixas` de largura uniforme com `contagem`); o que resta e
 *    escalar retangulos. Uma dependencia de charting somaria centenas de KB ao
 *    bundle, produziria uma arvore de `<div>` dificil de descrever para
 *    tecnologia assistiva e ainda exigiria o mesmo trabalho de acessibilidade
 *    feito aqui.
 * 2. **Nenhum texto dentro do SVG.** Texto em unidades de `viewBox` escala junto
 *    com o desenho: o mesmo rotulo sairia com 19px em uma tela larga e 7px no
 *    celular. Todos os rotulos sao HTML posicionado por porcentagem sobre o
 *    grafico, entao a tipografia obedece a escala da interface em qualquer
 *    largura. Como consequencia o SVG e puramente grafico e as margens
 *    horizontais sao zero, o que faz a porcentagem do HTML coincidir exatamente
 *    com a coordenada do desenho.
 * 3. **O grafico nunca e o unico portador de significado.** O `<svg>` e
 *    `role="img"` com um `aria-label` que resume o achado em prosa, e seu
 *    interior e `aria-hidden`. Os mesmos numeros existem nas tabelas que o
 *    acompanham.
 * 4. **Duas cores, um significado cada.** Teal e o grupo; ocre e voce. A barra
 *    que contem a posicao troca de cor e ganha o marcador, entao a identidade
 *    nao depende so do matiz: ha tambem posicao, rotulo e a linha tracejada.
 * 5. **Topos arredondados desenhados com `path`.** `rx` em um `<rect>`
 *    arredondaria tambem a base, descolando a barra da linha de base; o path
 *    arredonda so a ponta de dado, que e a convencao correta.
 */

import { useState } from 'react';

import { FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import type { FaixaHistograma } from '@/lib/tipos';

/** Geometria em unidades de `viewBox`; o tamanho real e fluido via CSS. */
const LARGURA = 640;
const ALTURA = 240;
/** Respiro entre barras vizinhas, em unidades de `viewBox`. */
const VAO = 2.5;
/** Raio da ponta de dado. */
const RAIO = 4;

/** Posicao aproximada da pessoa, em coordenadas de faixa. */
export interface PosicaoUsuario {
  /** Indice da faixa que contem a posicao. */
  indice: number;
  /** Fracao (0..1) percorrida dentro dessa faixa. */
  fracao: number;
  /** Nota estimada correspondente, interpolada dentro da faixa. */
  nota: number;
}

/** Rotulo textual de uma faixa ("500,0 a 550,0"). */
export function rotuloFaixa(faixa: FaixaHistograma): string {
  return `${FORMATO_UMA_CASA.format(faixa.limite_inferior)} a ${FORMATO_UMA_CASA.format(
    faixa.limite_superior,
  )}`;
}

/** Barra com as duas pontas superiores arredondadas e a base reta. */
function caminhoBarra(x: number, y: number, largura: number, altura: number): string {
  const raio = Math.min(RAIO, largura / 2, altura);
  const base = y + altura;
  return (
    `M ${x} ${base}` +
    ` L ${x} ${y + raio}` +
    ` Q ${x} ${y} ${x + raio} ${y}` +
    ` L ${x + largura - raio} ${y}` +
    ` Q ${x + largura} ${y} ${x + largura} ${y + raio}` +
    ` L ${x + largura} ${base} Z`
  );
}

export interface HistogramaProps {
  faixas: FaixaHistograma[];
  posicao: PosicaoUsuario | null;
  /** Resumo em prosa; vira o nome acessivel do grafico. */
  descricao: string;
}

export default function Histograma({ faixas, posicao, descricao }: HistogramaProps) {
  const [sobrevoada, setSobrevoada] = useState<number | null>(null);

  const total = faixas.reduce((soma, faixa) => soma + faixa.contagem, 0);
  const maiorContagem = faixas.reduce((maior, faixa) => Math.max(maior, faixa.contagem), 0);
  const passo = LARGURA / faixas.length;
  const larguraBarra = Math.max(passo - VAO, 1);

  /** Posicao do marcador em porcentagem da largura — serve ao SVG e ao HTML. */
  const percentualMarcador =
    posicao === null ? null : ((posicao.indice + posicao.fracao) / faixas.length) * 100;

  const primeira = faixas[0];
  const ultima = faixas[faixas.length - 1];
  const faixaSobrevoada = sobrevoada !== null ? faixas[sobrevoada] : undefined;

  return (
    <div>
      {/* `pt-5` reserva a faixa onde o rotulo do marcador flutua. */}
      <div className="relative pt-5">
        {percentualMarcador !== null && (
          <span
            aria-hidden="true"
            className="absolute top-0 -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold text-voce"
            style={{
              // Mantem o rotulo dentro do quadro nos extremos da escala.
              left: `clamp(2.5rem, ${percentualMarcador}%, calc(100% - 2.5rem))`,
            }}
          >
            sua posicao
          </span>
        )}

        <svg
          viewBox={`0 0 ${LARGURA} ${ALTURA}`}
          role="img"
          aria-label={descricao}
          preserveAspectRatio="none"
          className="block h-[clamp(160px,26vw,300px)] w-full"
          onMouseLeave={() => setSobrevoada(null)}
        >
          <title>{descricao}</title>
          <g aria-hidden="true">
            {faixas.map((faixa, indice) => {
              const altura =
                maiorContagem > 0 ? (faixa.contagem / maiorContagem) * (ALTURA - 2) : 0;
              const alturaVisivel = Math.max(altura, faixa.contagem > 0 ? 2 : 0);
              const naPosicao = posicao !== null && posicao.indice === indice;
              const x = indice * passo + VAO / 2;

              return (
                <g key={`${faixa.limite_inferior}-${faixa.limite_superior}`}>
                  {/* Alvo de mouse da coluna inteira: bem maior que a barra, para
                      que faixas de contagem baixa continuem sobrevoaveis. */}
                  <rect
                    x={indice * passo}
                    y={0}
                    width={passo}
                    height={ALTURA}
                    fill="transparent"
                    onMouseEnter={() => setSobrevoada(indice)}
                  />
                  {alturaVisivel > 0 && (
                    <path
                      className="barra-histograma"
                      style={{ animationDelay: `${Math.min(indice * 18, 320)}ms` }}
                      d={caminhoBarra(x, ALTURA - alturaVisivel, larguraBarra, alturaVisivel)}
                      fill={naPosicao ? 'var(--color-voce)' : 'var(--color-coorte)'}
                      opacity={sobrevoada === null || sobrevoada === indice ? 1 : 0.45}
                      pointerEvents="none"
                    />
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Linha do marcador em HTML: com `preserveAspectRatio="none"` um traco
            no SVG teria espessura distorcida na horizontal. */}
        {percentualMarcador !== null && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-5 top-4 w-0 border-l-2 border-dashed border-voce"
            style={{ left: `${percentualMarcador}%` }}
          />
        )}

        {faixaSobrevoada !== undefined && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 rounded-[4px]
                       border border-line bg-surface px-3 py-1.5 text-xs shadow-[0_4px_12px_rgb(12_43_51/0.1)]"
          >
            <span className="font-medium text-ink">{rotuloFaixa(faixaSobrevoada)}</span>
            <span className="text-ink-60">
              {' '}
              &middot; {FORMATO_INTEIRO.format(faixaSobrevoada.contagem)} pessoas
              {total > 0 &&
                ` (${FORMATO_UMA_CASA.format((faixaSobrevoada.contagem / total) * 100)}%)`}
            </span>
          </div>
        )}
      </div>

      {/* Eixo e rotulos em HTML: tipografia constante em qualquer largura. */}
      <div
        aria-hidden="true"
        className="numerico mt-0 flex items-center justify-between border-t border-line-forte pt-1.5 text-[11px] text-ink-60"
      >
        <span>{primeira !== undefined ? FORMATO_UMA_CASA.format(primeira.limite_inferior) : ''}</span>
        <span className="text-ink-40">nota</span>
        <span>{ultima !== undefined ? FORMATO_UMA_CASA.format(ultima.limite_superior) : ''}</span>
      </div>
    </div>
  );
}
