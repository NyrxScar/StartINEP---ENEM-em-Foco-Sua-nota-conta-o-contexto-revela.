/**
 * `Modal` — dialogo sobre `<dialog>` nativo.
 *
 * O elemento nativo ja entrega, sem biblioteca e sem codigo nosso, o que
 * costuma ser reimplementado errado: captura de foco dentro do dialogo,
 * fechamento com Esc, camada de topo acima de qualquer `z-index` e a semantica
 * de dialogo modal para tecnologia assistiva. O que resta aqui e ligar o
 * elemento ao estado do React e devolver o foco a quem abriu.
 */

import { X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';

export interface ModalProps {
  aberto: boolean;
  aoFechar: () => void;
  titulo: string;
  /** Linha de apoio sob o titulo. */
  descricao?: string;
  children: ReactNode;
  /** Acoes no rodape; sem elas o rodape nao e renderizado. */
  rodape?: ReactNode;
}

export default function Modal({
  aberto,
  aoFechar,
  titulo,
  descricao,
  children,
  rodape,
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const focoAnterior = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialogo = ref.current;
    if (dialogo === null) return;

    if (aberto && !dialogo.open) {
      focoAnterior.current = document.activeElement as HTMLElement | null;
      dialogo.showModal();
    } else if (!aberto && dialogo.open) {
      dialogo.close();
      focoAnterior.current?.focus();
    }
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      // `cancel` cobre o Esc: sem isto o dialogo fecharia no DOM enquanto o
      // estado do React continuaria dizendo "aberto", e a proxima abertura nao
      // aconteceria.
      onCancel={(evento) => {
        evento.preventDefault();
        aoFechar();
      }}
      onClose={aoFechar}
      // Clique fora: o `<dialog>` recebe o evento quando o alvo e ele proprio,
      // ou seja, o backdrop, e nunca quando e um filho.
      onClick={(evento) => {
        if (evento.target === ref.current) aoFechar();
      }}
      aria-labelledby="modal-titulo"
      className="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-[4px] border border-line
                 bg-surface p-0 text-ink shadow-[0_8px_24px_rgb(12_43_51/0.18)]
                 backdrop:bg-ink/35 backdrop:backdrop-blur-[2px]"
    >
      <header className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div>
          <h2 id="modal-titulo" className="text-[17px]">
            {titulo}
          </h2>
          {descricao !== undefined && (
            <p className="mt-1 text-sm text-ink-60">{descricao}</p>
          )}
        </div>
        <button
          type="button"
          onClick={aoFechar}
          aria-label="Fechar"
          className="-m-1 rounded-[4px] p-1 text-ink-60 transition-colors hover:bg-paper hover:text-ink"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      <div className="max-h-[60vh] overflow-y-auto p-5 text-sm leading-relaxed">
        {children}
      </div>

      {rodape !== undefined && (
        <footer className="flex justify-end gap-2 border-t border-line bg-paper p-4">
          {rodape}
        </footer>
      )}
    </dialog>
  );
}
