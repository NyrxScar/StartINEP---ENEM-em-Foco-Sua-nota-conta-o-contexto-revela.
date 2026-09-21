/**
 * `Cabecalho` — busca de secoes, acesso rapido e conta.
 *
 * A busca navega entre **secoes do painel**, nao entre dados: a API nao expoe
 * um indice pesquisavel (nao ha escolas, participantes nem linhas para
 * procurar), e um campo que promete busca em dados e devolve nada seria uma
 * promessa falsa. O placeholder diz exatamente o que o campo faz.
 *
 * O resultado e uma lista `role="listbox"` navegavel por setas, com Enter para
 * abrir e Esc para fechar — combinacao padrao de combobox, para que quem usa
 * teclado nao precise aprender nada novo aqui.
 */

import { Menu, Search, UserRound } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { NAVEGACAO } from '@/components/layout/navegacao';

export interface CabecalhoProps {
  aoAbrirMenu: () => void;
}

/** Normaliza para comparar sem acento e sem caixa. */
function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

export default function Cabecalho({ aoAbrirMenu }: CabecalhoProps) {
  const navegar = useNavigate();
  const [termo, setTermo] = useState('');
  const [aberta, setAberta] = useState(false);
  const [destacado, setDestacado] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const resultados = useMemo(() => {
    const alvo = normalizar(termo);
    if (alvo.length === 0) return [];
    return NAVEGACAO.filter(
      (item) =>
        normalizar(item.rotulo).includes(alvo) || normalizar(item.descricao).includes(alvo),
    );
  }, [termo]);

  // Fecha ao clicar fora; a lista some sem roubar o foco de onde a pessoa foi.
  useEffect(() => {
    if (!aberta) return;
    function aoClicar(evento: MouseEvent) {
      if (!containerRef.current?.contains(evento.target as Node)) setAberta(false);
    }
    document.addEventListener('mousedown', aoClicar);
    return () => document.removeEventListener('mousedown', aoClicar);
  }, [aberta]);

  function abrir(indice: number) {
    const alvo = resultados[indice];
    if (alvo === undefined) return;
    navegar(alvo.para);
    setTermo('');
    setAberta(false);
  }

  function aoTeclar(evento: React.KeyboardEvent<HTMLInputElement>) {
    if (evento.key === 'Escape') {
      setAberta(false);
      return;
    }
    if (resultados.length === 0) return;
    if (evento.key === 'ArrowDown') {
      evento.preventDefault();
      setDestacado((n) => (n + 1) % resultados.length);
    } else if (evento.key === 'ArrowUp') {
      evento.preventDefault();
      setDestacado((n) => (n - 1 + resultados.length) % resultados.length);
    } else if (evento.key === 'Enter') {
      evento.preventDefault();
      abrir(destacado);
    }
  }

  return (
    <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/85 px-4 py-3 backdrop-blur-md sm:px-6">
      <button
        type="button"
        onClick={aoAbrirMenu}
        aria-label="Abrir navegacao"
        className="rounded-[4px] p-2 text-ink-80 transition-colors hover:bg-paper lg:hidden"
      >
        <Menu size={19} aria-hidden="true" />
      </button>

      <p className="whitespace-nowrap font-display text-[15px] font-semibold text-ink lg:hidden">
        Radar ENEM
      </p>

      <div ref={containerRef} className="relative ml-auto w-full max-w-sm lg:ml-0">
        <Search
          size={15}
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-40"
        />
        <input
          type="search"
          value={termo}
          role="combobox"
          aria-expanded={aberta && resultados.length > 0}
          aria-controls="busca-secoes"
          aria-autocomplete="list"
          aria-label="Buscar secao do painel"
          placeholder="Buscar secao do painel"
          onChange={(evento) => {
            setTermo(evento.target.value);
            setAberta(true);
            setDestacado(0);
          }}
          onFocus={() => setAberta(true)}
          onKeyDown={aoTeclar}
          className="w-full rounded-[4px] border border-line bg-paper py-2 pl-9 pr-3 text-sm
                     text-ink transition-colors placeholder:text-ink-40 hover:border-line-forte
                     focus:border-coorte focus:bg-surface"
        />

        {aberta && termo.trim().length > 0 && (
          <ul
            id="busca-secoes"
            role="listbox"
            aria-label="Secoes encontradas"
            className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-[4px] border border-line bg-surface shadow-[0_8px_24px_rgb(12_43_51/0.12)]"
          >
            {resultados.length === 0 ? (
              <li className="px-3 py-2.5 text-sm text-ink-60">
                Nenhuma secao corresponde a &ldquo;{termo}&rdquo;.
              </li>
            ) : (
              resultados.map((item, indice) => (
                <li key={item.para}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={indice === destacado}
                    onMouseEnter={() => setDestacado(indice)}
                    onClick={() => abrir(indice)}
                    className={`flex w-full flex-col items-start px-3 py-2 text-left text-sm transition-colors ${
                      indice === destacado ? 'bg-paper' : ''
                    }`}
                  >
                    <span className="font-medium text-ink">{item.rotulo}</span>
                    <span className="text-xs text-ink-60">{item.descricao}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        )}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span className="hidden text-right text-xs leading-tight text-ink-60 sm:block">
          Acesso publico
          <span className="block text-ink-40">Dados abertos do INEP</span>
        </span>
        <span
          aria-hidden="true"
          className="grid size-9 place-items-center rounded-full border border-line bg-paper text-ink-60"
        >
          <UserRound size={17} strokeWidth={1.75} />
        </span>
      </div>
    </header>
  );
}
