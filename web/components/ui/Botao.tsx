/**
 * `Botao` — acao padrao da interface.
 *
 * O ocre da paleta **nao** aparece aqui de proposito: ele esta reservado para
 * marcar a posicao da pessoa no grafico. Um botao primario ocre gastaria o
 * unico ponto quente da interface em uma afordancia que a forma e o contraste
 * ja resolvem. A hierarquia vem do peso: tinta cheia, contorno, ou nada.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type VarianteBotao = 'primario' | 'secundario' | 'discreto';

export interface BotaoProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: VarianteBotao;
  /** Icone a esquerda do rotulo; decorativo, o texto carrega o significado. */
  icone?: ReactNode;
  /** Ocupa toda a largura disponivel (util em coluna estreita / mobile). */
  largura?: 'auto' | 'cheia';
}

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-[4px] px-4 py-2 text-sm ' +
  'font-medium transition-colors duration-150 disabled:cursor-not-allowed ' +
  'disabled:opacity-45 select-none';

const VARIANTES: Record<VarianteBotao, string> = {
  primario: 'bg-ink text-paper hover:bg-ink-80 active:bg-ink',
  secundario:
    'border border-line-forte bg-surface text-ink hover:bg-paper hover:border-ink-40',
  discreto: 'text-ink-80 hover:bg-paper hover:text-ink',
};

export default function Botao({
  variante = 'primario',
  icone,
  largura = 'auto',
  className = '',
  children,
  type = 'button',
  ...resto
}: BotaoProps) {
  const classes = [
    BASE,
    VARIANTES[variante],
    largura === 'cheia' ? 'w-full' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    // eslint-disable-next-line react/button-has-type -- `type` e sempre definido acima.
    <button type={type} className={classes} {...resto}>
      {icone !== undefined && (
        <span aria-hidden="true" className="shrink-0">
          {icone}
        </span>
      )}
      {children}
    </button>
  );
}
