/**
 * `BarraLateral` — navegacao principal.
 *
 * Decisoes:
 *
 * 1. **Superficie em tinta petroleo.** A barra e escura e a area de conteudo
 *    clara: isso ancora a aplicacao e deixa o painel de dados respirar sem
 *    precisar de moldura. O item ativo e marcado por uma regua ocre de 2px e
 *    texto mais claro — nao por uma pilula preenchida, que competiria com os
 *    graficos pelo mesmo recurso visual.
 * 2. **A limitacao aparece na navegacao.** Secoes sem endpoint que as sustente
 *    levam um "sem dados" discreto. A pessoa descobre o limite antes de clicar,
 *    e nao depois de esperar um carregamento que nunca vem.
 * 3. **Uma so marcacao para as duas larguras.** Em telas estreitas o mesmo
 *    elemento vira gaveta sobre a pagina (`aria-hidden` quando fechada, foco
 *    devolvido ao fechar); em telas largas e uma coluna fixa. Duplicar a lista
 *    em dois componentes seria duas listas para manter em sincronia.
 */

import { X } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { NAVEGACAO } from '@/components/layout/navegacao';
import type { Saude } from '@/lib/tipos';

export interface BarraLateralProps {
  aberta: boolean;
  aoFechar: () => void;
  saude: Saude | null;
  saudeIndisponivel: boolean;
}

function EstadoServico({
  saude,
  indisponivel,
}: {
  saude: Saude | null;
  indisponivel: boolean;
}) {
  const { cor, texto, detalhe } = indisponivel
    ? { cor: 'bg-[#d16a6a]', texto: 'API inacessivel', detalhe: 'Verifique VITE_API_URL.' }
    : saude === null
      ? { cor: 'bg-ink-40', texto: 'Verificando servico', detalhe: '' }
      : saude.status === 'ok'
        ? {
            cor: 'bg-[#4fb3a1]',
            texto: 'Servico operacional',
            detalhe:
              saude.edicoes.length > 0
                ? `${saude.edicoes.length} ${saude.edicoes.length === 1 ? 'edicao carregada' : 'edicoes carregadas'}`
                : 'Nenhuma edicao carregada',
          }
        : {
            cor: 'bg-[#e0a458]',
            texto: 'Servico degradado',
            detalhe: 'Base de dados inacessivel.',
          };

  return (
    <div className="border-t border-white/10 px-5 py-4">
      <p className="flex items-center gap-2 text-[13px] font-medium text-white/85">
        <span aria-hidden="true" className={`size-2 rounded-full ${cor}`} />
        {texto}
      </p>
      {detalhe !== '' && <p className="mt-1 pl-4 text-xs text-white/45">{detalhe}</p>}
    </div>
  );
}

export default function BarraLateral({
  aberta,
  aoFechar,
  saude,
  saudeIndisponivel,
}: BarraLateralProps) {
  return (
    <>
      {/* Cortina da gaveta em telas estreitas. Decorativa: fechar tambem esta
          no botao com rotulo e no Esc do proprio foco. */}
      {aberta && (
        <button
          type="button"
          aria-label="Fechar navegacao"
          onClick={aoFechar}
          className="fixed inset-0 z-30 bg-ink/40 backdrop-blur-[1px] lg:hidden"
        />
      )}

      <nav
        aria-label="Secoes do painel"
        className={`fixed inset-y-0 left-0 z-40 flex w-[17rem] flex-col bg-ink text-white/70
                    transition-transform duration-200 lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0
                    ${aberta ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center justify-between gap-2 px-5 py-5 lg:pb-6">
          <div>
            <p className="font-display text-[17px] font-semibold tracking-tight text-white">
              Radar ENEM
            </p>
            <p className="mt-0.5 text-xs text-white/45">Microdados do INEP</p>
          </div>
          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar navegacao"
            className="rounded-[4px] p-1 text-white/60 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <ul className="flex-1 space-y-0.5 overflow-y-auto px-3">
          {NAVEGACAO.map(({ para, rotulo, descricao, icone: Icone, apoiada }) => (
            <li key={para}>
              <NavLink
                to={para}
                end={para === '/'}
                onClick={aoFechar}
                className={({ isActive }) =>
                  `group flex items-start gap-3 border-l-2 py-2.5 pl-3 pr-2 text-sm transition-colors ${
                    isActive
                      ? 'border-voce bg-white/[0.07] text-white'
                      : 'border-transparent text-white/65 hover:bg-white/5 hover:text-white/90'
                  }`
                }
              >
                <Icone size={17} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 font-medium">
                    {rotulo}
                    {!apoiada && (
                      <span className="rounded-sm bg-white/10 px-1.5 py-px text-[10px] font-normal text-white/55">
                        sem dados
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-white/40">
                    {descricao}
                  </span>
                </span>
              </NavLink>
            </li>
          ))}
        </ul>

        <EstadoServico saude={saude} indisponivel={saudeIndisponivel} />
      </nav>
    </>
  );
}
