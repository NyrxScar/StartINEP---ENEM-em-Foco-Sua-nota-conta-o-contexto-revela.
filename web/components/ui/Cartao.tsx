/**
 * `Cartao` — superficie de conteudo.
 *
 * Duas variantes, nao uma so aplicada a tudo: `contorno` para blocos que
 * precisam se separar do fundo, e `plano` para conteudo que deve continuar
 * lendo como parte da pagina. A distincao existe porque picotar a interface em
 * cartoes identicos, todos com a mesma sombra e o mesmo raio, apaga a
 * hierarquia em vez de cria-la — o histograma, por exemplo, e servido sem
 * moldura nenhuma para poder ser o elemento dominante da tela.
 */

import type { ReactNode } from 'react';

export interface CartaoProps {
  titulo?: string;
  /** Linha de apoio sob o titulo. */
  descricao?: ReactNode;
  /** Conteudo alinhado a direita do cabecalho (acoes, distintivos). */
  acoes?: ReactNode;
  variante?: 'contorno' | 'plano';
  /** Remove o respiro interno, para conteudo que gerencia o proprio (tabelas). */
  semPadding?: boolean;
  className?: string;
  children: ReactNode;
}

export default function Cartao({
  titulo,
  descricao,
  acoes,
  variante = 'contorno',
  semPadding = false,
  className = '',
  children,
}: CartaoProps) {
  const superficie =
    variante === 'contorno'
      ? 'bg-surface border border-line rounded-[4px] shadow-[0_1px_2px_rgb(12_43_51/0.06)]'
      : 'bg-transparent';

  return (
    <section className={`${superficie} ${className}`}>
      {(titulo !== undefined || acoes !== undefined) && (
        <header
          className={`flex flex-wrap items-start justify-between gap-3 ${
            semPadding ? 'px-5 pt-5 pb-3' : 'p-5 pb-3'
          }`}
        >
          <div className="min-w-0">
            {titulo !== undefined && (
              <h2 className="text-[17px] text-ink">{titulo}</h2>
            )}
            {descricao !== undefined && (
              <p className="mt-1 text-sm text-ink-60 prosa">{descricao}</p>
            )}
          </div>
          {acoes !== undefined && <div className="shrink-0">{acoes}</div>}
        </header>
      )}
      <div className={semPadding ? '' : titulo !== undefined ? 'px-5 pb-5' : 'p-5'}>
        {children}
      </div>
    </section>
  );
}
