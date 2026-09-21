/**
 * `GruposExploracao` — o resultado de `POST /v1/exploracao` como grafico e tabela.
 *
 * Decisoes:
 *
 * 1. **Faixa interquartil, nao barra de media.** Cada grupo e uma distribuicao,
 *    nao um numero. Uma barra de medias diria que "Sudeste tem 560" e esconderia
 *    que metade do Sudeste esta entre 470 e 640 — que e o fato interessante.
 *    Desenhar Q1–Q3 com a mediana marcada mostra centro **e** dispersao no mesmo
 *    espaco, e deixa visivel quando dois grupos com medianas diferentes se
 *    sobrepoem quase por inteiro.
 * 2. **Escala comum de 0 a 1000.** Todos os grupos compartilham o eixo da nota
 *    do ENEM. Escalar cada linha pelo proprio maximo produziria comparacao
 *    visual falsa entre grupos.
 * 3. **Grupo suprimido continua na lista.** Quando a guarda de privacidade
 *    anula um grupo, ele aparece com o nome e a explicacao no lugar da faixa —
 *    a lista continua completa, e a ausencia de numeros e a informacao.
 * 4. **HTML, nao SVG.** Larguras percentuais resolvem a geometria inteira, e os
 *    rotulos herdam a tipografia da interface em vez de escalarem com o desenho.
 */

import { Lock } from 'lucide-react';
import type { ReactNode } from 'react';

import TabelaDados from '@/components/ui/TabelaDados';
import { FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import type { GrupoExploracao } from '@/lib/tipos';

/** Limites do eixo: o intervalo possivel de uma nota do ENEM. */
const NOTA_MAXIMA = 1000;
const MARCAS = [0, 250, 500, 750, 1000];

export interface GruposExploracaoProps {
  grupos: GrupoExploracao[];
  /** Traduz o valor cru da dimensao para algo legivel (ex.: "1" -> "Urbana"). */
  rotularValor?: (valor: string) => string;
  /** Resumo em prosa; vira o nome acessivel do grafico. */
  descricao: string;
  /** Legenda da tabela equivalente. */
  legendaTabela: string;
  /** Exibido quando nao ha nenhum grupo. */
  vazio?: ReactNode;
}

function FaixaGrupo({ quantis }: { quantis: NonNullable<GrupoExploracao['quantis']> }) {
  const inicio = (quantis.q1 / NOTA_MAXIMA) * 100;
  const largura = Math.max(((quantis.q3 - quantis.q1) / NOTA_MAXIMA) * 100, 0.4);
  const mediana = (quantis.mediana / NOTA_MAXIMA) * 100;

  return (
    <div className="relative h-5">
      {MARCAS.slice(1, -1).map((marca) => (
        <span
          key={marca}
          aria-hidden="true"
          className="absolute inset-y-0 w-px bg-line"
          style={{ left: `${(marca / NOTA_MAXIMA) * 100}%` }}
        />
      ))}
      <span
        className="absolute inset-y-1 rounded-[3px] bg-coorte/75"
        style={{ left: `${inicio}%`, width: `${largura}%` }}
      />
      <span
        className="absolute inset-y-0 w-0.5 rounded-full bg-ink"
        style={{ left: `${mediana}%` }}
      />
    </div>
  );
}

export default function GruposExploracao({
  grupos,
  rotularValor = (valor) => valor,
  descricao,
  legendaTabela,
  vazio = 'Nenhum grupo para exibir neste recorte.',
}: GruposExploracaoProps) {
  if (grupos.length === 0) {
    return (
      <p className="rounded-[4px] border border-dashed border-line-forte bg-surface px-6 py-8 text-center text-sm text-ink-60">
        {vazio}
      </p>
    );
  }

  const visiveis = grupos.filter((g) => g.quantis !== null);
  const suprimidos = grupos.length - visiveis.length;

  return (
    <div className="space-y-5">
      <div role="img" aria-label={descricao}>
        <div aria-hidden="true" className="space-y-1.5">
          {grupos.map((grupo) => (
            <div key={grupo.valor} className="flex items-center gap-3">
              <span className="w-36 shrink-0 truncate text-right text-[13px] text-ink-80" title={rotularValor(grupo.valor)}>
                {rotularValor(grupo.valor)}
              </span>

              <div className="min-w-0 flex-1 border-l border-line-forte pl-px">
                {grupo.quantis !== null ? (
                  <FaixaGrupo quantis={grupo.quantis} />
                ) : (
                  <p className="flex h-5 items-center gap-1.5 text-xs text-ink-40">
                    <Lock size={11} strokeWidth={2} />
                    grupo pequeno demais para divulgar
                  </p>
                )}
              </div>

              <span className="numerico w-24 shrink-0 text-right text-[13px] text-ink">
                {grupo.quantis !== null ? FORMATO_UMA_CASA.format(grupo.quantis.mediana) : '—'}
              </span>
            </div>
          ))}
        </div>

        {/* Eixo e legenda do desenho: sem eles a faixa nao diz o que representa. */}
        <div aria-hidden="true" className="mt-2 flex items-start gap-3">
          <span className="w-36 shrink-0" />
          <div className="numerico relative min-w-0 flex-1 text-[11px] text-ink-40">
            {MARCAS.map((marca) => (
              <span
                key={marca}
                className={`absolute top-0 ${marca === 0 ? '' : marca === NOTA_MAXIMA ? '-translate-x-full' : '-translate-x-1/2'}`}
                style={{ left: `${(marca / NOTA_MAXIMA) * 100}%` }}
              >
                {marca}
              </span>
            ))}
            <span className="invisible">0</span>
          </div>
          <span className="w-24 shrink-0 text-right text-[11px] text-ink-40">mediana</span>
        </div>

        <p aria-hidden="true" className="prosa mt-3 text-xs text-ink-60">
          A barra cobre a metade central do grupo (do primeiro ao terceiro quartil) e o
          traco escuro marca a mediana. Barras que se sobrepoem indicam grupos cujas
          notas se confundem, mesmo quando as medianas diferem.
          {suprimidos > 0 &&
            ` ${FORMATO_INTEIRO.format(suprimidos)} ${
              suprimidos === 1 ? 'grupo ficou' : 'grupos ficaram'
            } sem numeros por serem pequenos demais para divulgacao.`}
        </p>
      </div>

      <div className="overflow-hidden rounded-[4px] border border-line bg-surface pt-4">
        <TabelaDados
          legenda={legendaTabela}
          paginaTamanho={15}
          linhas={grupos}
          chaveLinha={(grupo) => grupo.valor}
          colunas={[
            {
              chave: 'valor',
              cabecalho: 'Grupo',
              celula: (grupo) => rotularValor(grupo.valor),
            },
            {
              chave: 'pessoas',
              cabecalho: 'Pessoas',
              alinhamento: 'fim',
              celula: (grupo) =>
                grupo.tamanho_amostral !== null
                  ? FORMATO_INTEIRO.format(grupo.tamanho_amostral)
                  : 'suprimido',
            },
            {
              chave: 'q1',
              cabecalho: 'Q1',
              alinhamento: 'fim',
              celula: (grupo) =>
                grupo.quantis !== null ? FORMATO_UMA_CASA.format(grupo.quantis.q1) : '—',
            },
            {
              chave: 'mediana',
              cabecalho: 'Mediana',
              alinhamento: 'fim',
              celula: (grupo) =>
                grupo.quantis !== null ? FORMATO_UMA_CASA.format(grupo.quantis.mediana) : '—',
            },
            {
              chave: 'q3',
              cabecalho: 'Q3',
              alinhamento: 'fim',
              celula: (grupo) =>
                grupo.quantis !== null ? FORMATO_UMA_CASA.format(grupo.quantis.q3) : '—',
            },
          ]}
        />
      </div>
    </div>
  );
}
