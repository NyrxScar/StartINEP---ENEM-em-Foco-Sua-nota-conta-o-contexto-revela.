/**
 * `EstadoVazio` — tela sem conteudo, com saida.
 *
 * Uma tela vazia e um convite a agir, nao um aviso de ausencia. Por isso o
 * componente exige `acao`: sempre existe um proximo passo possivel, mesmo que
 * seja ir para outra secao. Quando a ausencia e estrutural (a API nao publica
 * aquele dado), `fonteAusente` diz exatamente qual dado falta — a pessoa
 * merece saber que o vazio e um limite da base, nao um erro seu nem uma tela
 * que ainda vai carregar.
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export interface EstadoVazioProps {
  icone: LucideIcon;
  titulo: string;
  descricao: ReactNode;
  /** Qual dado a API nao publica; exibido como nota tecnica ao final. */
  fonteAusente?: string;
  acao: ReactNode;
}

export default function EstadoVazio({
  icone: Icone,
  titulo,
  descricao,
  fonteAusente,
  acao,
}: EstadoVazioProps) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-[4px] border border-dashed border-line-forte bg-surface px-6 py-10 sm:px-10">
      <span className="rounded-[4px] bg-paper p-2.5 text-ink-60">
        <Icone size={22} aria-hidden="true" strokeWidth={1.75} />
      </span>

      <div>
        <h2 className="text-[19px] text-ink">{titulo}</h2>
        <div className="prosa mt-2 text-sm leading-relaxed text-ink-80">{descricao}</div>
      </div>

      {fonteAusente !== undefined && (
        <p className="prosa border-l-2 border-line-forte pl-3 text-xs text-ink-60">
          Dado ausente na API: {fonteAusente}
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-1">{acao}</div>
    </div>
  );
}
