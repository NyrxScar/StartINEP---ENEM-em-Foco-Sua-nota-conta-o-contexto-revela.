/**
 * `Distintivo` — rotulo curto de estado.
 *
 * Cor nunca e o unico sinal: cada tom vem acompanhado do proprio texto, e os
 * estados de disponibilidade tambem trazem um ponto que muda de forma. O tom
 * `recusa` usa vinho, nao vermelho de semaforo, porque neste produto a maioria
 * das negativas e uma decisao correta do servico (supressao por privacidade,
 * dados que nao podem ser cruzados) e nao uma falha.
 */

import type { ReactNode } from 'react';

export type TomDistintivo = 'neutro' | 'ativo' | 'atencao' | 'recusa';

const TONS: Record<TomDistintivo, string> = {
  neutro: 'bg-paper text-ink-80 border-line-forte',
  ativo: 'bg-coorte-fraco text-[#005c69] border-[#9ed3db]',
  atencao: 'bg-voce-fraco text-[#8a4100] border-[#e3b98c]',
  recusa: 'bg-vinho-fraco text-vinho border-[#e0b9c6]',
};

export interface DistintivoProps {
  tom?: TomDistintivo;
  /** Ponto colorido a esquerda; util para estados de disponibilidade. */
  ponto?: boolean;
  children: ReactNode;
}

export default function Distintivo({
  tom = 'neutro',
  ponto = false,
  children,
}: DistintivoProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONS[tom]}`}
    >
      {ponto && (
        <span aria-hidden="true" className="size-1.5 rounded-full bg-current opacity-70" />
      )}
      {children}
    </span>
  );
}
