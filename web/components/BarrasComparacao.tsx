/**
 * `BarrasComparacao` — o mesmo percentil lado a lado, uma barra por edicao.
 *
 * Decisoes:
 *
 * 1. **Barras horizontais em HTML, nao em SVG.** Comparar um valor entre poucas
 *    categorias nomeadas se resolve com larguras percentuais; nao ha nenhuma
 *    geometria aqui que justifique um sistema de coordenadas. Em HTML os
 *    rotulos herdam a tipografia da interface em vez de escalarem junto com o
 *    desenho, e o alinhamento com as tabelas ao lado sai de graca.
 * 2. **Escala fixa de 0 a 100.** Percentil tem limites naturais; escalar pelo
 *    maior valor presente exageraria diferencas pequenas — dois anos com 71% e
 *    74% pareceriam mundos distantes.
 * 3. **Uma serie, nenhuma legenda.** O titulo do cartao ja diz o que a barra
 *    mede e cada valor esta rotulado diretamente na ponta; uma legenda aqui
 *    seria uma caixa para explicar uma cor so.
 * 4. **O conjunto e uma figura unica para tecnologia assistiva**: `role="img"`
 *    com o resumo em prosa, interior `aria-hidden`, e os mesmos numeros na
 *    tabela que acompanha o grafico.
 */

import { FORMATO_EDICAO, FORMATO_UMA_CASA } from '@/lib/formato';

export interface ItemComparacao {
  edicao: number;
  percentil: number;
  /** Rotulo de apoio, como o tamanho do grupo. */
  detalhe: string;
}

export interface BarrasComparacaoProps {
  itens: ItemComparacao[];
  descricao: string;
}

const MARCAS = [0, 25, 50, 75, 100];

export default function BarrasComparacao({ itens, descricao }: BarrasComparacaoProps) {
  return (
    <div role="img" aria-label={descricao}>
      <div aria-hidden="true" className="space-y-3">
        {itens.map((item) => (
          <div key={item.edicao} className="flex items-center gap-3">
            <span className="numerico w-12 shrink-0 text-right text-[13px] font-medium text-ink-80">
              {FORMATO_EDICAO.format(item.edicao)}
            </span>

            <div className="relative min-w-0 flex-1 border-l border-line-forte py-1">
              {/* Grade a cada 25 pontos percentuais, atras das barras. */}
              {MARCAS.slice(1).map((marca) => (
                <span
                  key={marca}
                  className="absolute inset-y-0 w-px bg-line"
                  style={{ left: `${marca}%` }}
                />
              ))}
              <div
                className="relative h-6 rounded-r-[4px] bg-coorte"
                style={{ width: `${Math.max(item.percentil, 0.5)}%` }}
              />
            </div>

            <span className="numerico w-32 shrink-0 text-[13px] text-ink">
              <span className="font-semibold">
                {FORMATO_UMA_CASA.format(item.percentil)}%
              </span>
              <span className="ml-1.5 text-xs text-ink-40">{item.detalhe}</span>
            </span>
          </div>
        ))}
      </div>

      <div aria-hidden="true" className="mt-2 flex gap-3">
        <span className="w-12 shrink-0" />
        <div className="numerico relative min-w-0 flex-1 text-[11px] text-ink-40">
          {MARCAS.map((marca) => (
            <span
              key={marca}
              className={`absolute top-0 ${marca === 0 ? '' : '-translate-x-1/2'}`}
              style={{ left: `${marca}%` }}
            >
              {marca}%
            </span>
          ))}
          <span className="invisible">0%</span>
        </div>
        <span className="w-32 shrink-0" />
      </div>
    </div>
  );
}
