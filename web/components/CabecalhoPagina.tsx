/**
 * `CabecalhoPagina` — titulo e subtitulo de uma secao.
 *
 * Sem sobrancelha em caixa alta e sem rotulo decorativo acima do titulo: o
 * titulo e a barra lateral ja dizem onde a pessoa esta, e uma terceira
 * repeticao do mesmo nome so ocuparia espaco.
 */

import type { ReactNode } from 'react';

export interface CabecalhoPaginaProps {
  titulo: string;
  descricao: string;
  /** Acoes alinhadas a direita em telas largas. */
  acoes?: ReactNode;
}

export default function CabecalhoPagina({
  titulo,
  descricao,
  acoes,
}: CabecalhoPaginaProps) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[clamp(1.5rem,3.5vw,2rem)] text-ink">{titulo}</h1>
        <p className="prosa mt-1.5 text-[15px] leading-relaxed text-ink-60">{descricao}</p>
      </div>
      {acoes !== undefined && <div className="flex gap-2">{acoes}</div>}
    </header>
  );
}
