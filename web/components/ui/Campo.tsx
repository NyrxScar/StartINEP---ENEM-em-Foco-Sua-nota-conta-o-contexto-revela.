/**
 * `Campo`, `Entrada` e `Selecao` — controles de formulario.
 *
 * `Campo` e o involucro que garante o que nao pode ser esquecido: um `<label>`
 * ligado pelo `htmlFor`, o texto de ajuda e a mensagem de erro referenciados
 * por `aria-describedby`, e `aria-invalid` no controle quando ha erro. Os
 * componentes de controle nao inventam ids; quem usa passa um `id` estavel, o
 * que mantem o `<label>` correto mesmo com listas dinamicas de filtros.
 */

import type { InputHTMLAttributes, Ref, ReactNode, SelectHTMLAttributes } from 'react';

const CONTROLE =
  'w-full rounded-[4px] border border-line-forte bg-surface px-3 py-2 text-sm ' +
  'text-ink transition-colors duration-150 placeholder:text-ink-40 ' +
  'hover:border-ink-40 focus:border-coorte disabled:cursor-not-allowed ' +
  'disabled:bg-paper disabled:text-ink-40 aria-[invalid=true]:border-vinho';

export interface CampoProps {
  id: string;
  rotulo: string;
  /** Texto de apoio permanente, sempre associado ao controle. */
  ajuda?: ReactNode;
  /** Mensagem de erro; quando presente, e anunciada e marca o controle. */
  erro?: string | null;
  children: (props: {
    id: string;
    'aria-describedby': string | undefined;
    'aria-invalid': true | undefined;
  }) => ReactNode;
}

export function Campo({ id, rotulo, ajuda, erro, children }: CampoProps) {
  const idAjuda = ajuda !== undefined ? `${id}-ajuda` : null;
  const idErro = erro != null && erro.length > 0 ? `${id}-erro` : null;
  const descritores = [idErro, idAjuda].filter((valor): valor is string => valor !== null);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink-80">
        {rotulo}
      </label>
      {children({
        id,
        'aria-describedby': descritores.length > 0 ? descritores.join(' ') : undefined,
        'aria-invalid': idErro !== null ? true : undefined,
      })}
      {idAjuda !== null && (
        <p id={idAjuda} className="text-xs text-ink-60">
          {ajuda}
        </p>
      )}
      {idErro !== null && (
        <p id={idErro} role="alert" className="text-xs font-medium text-vinho">
          {erro}
        </p>
      )}
    </div>
  );
}

/**
 * `ref` e declarado explicitamente: no React 19 componentes de funcao recebem
 * `ref` como prop comum, mas `InputHTMLAttributes` nao o inclui, e o formulario
 * precisa dele para mover o foco ao campo invalido.
 */
export interface EntradaProps extends InputHTMLAttributes<HTMLInputElement> {
  ref?: Ref<HTMLInputElement>;
}

export function Entrada({ className = '', ...resto }: EntradaProps) {
  return <input className={`${CONTROLE} ${className}`} {...resto} />;
}

export interface SelecaoProps extends SelectHTMLAttributes<HTMLSelectElement> {
  ref?: Ref<HTMLSelectElement>;
}

export function Selecao({ className = '', children, ...resto }: SelecaoProps) {
  return (
    <select className={`${CONTROLE} ${className} pr-8`} {...resto}>
      {children}
    </select>
  );
}
