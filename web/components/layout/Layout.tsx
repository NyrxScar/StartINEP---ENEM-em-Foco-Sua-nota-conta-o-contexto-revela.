/**
 * `Layout` — casca da aplicacao: barra lateral, cabecalho, conteudo e rodape.
 *
 * Detalhes que costumam faltar e aqui sao explicitos:
 *
 * 1. **Link para pular ao conteudo**, primeiro elemento focavel da pagina. Sem
 *    ele, quem navega por teclado atravessa a navegacao inteira a cada troca de
 *    rota.
 * 2. **O foco vai para o conteudo a cada mudanca de rota.** Uma SPA nao recarrega
 *    a pagina, entao o leitor de tela continuaria lendo a tela anterior; mover o
 *    foco para o `<main>` restaura o comportamento que a navegacao entre paginas
 *    daria de graca.
 * 3. **A gaveta fecha ao trocar de rota** em telas estreitas, e a pagina volta ao
 *    topo — o que se espera de uma navegacao.
 * 4. **Nada disso acontece na primeira renderizacao.** Mover o foco para o
 *    `<main>` ao abrir a pagina faria o primeiro Tab pular justamente o link de
 *    pular e a barra lateral inteira, que e o oposto do objetivo. Na carga
 *    inicial o navegador ja posiciona o foco no topo do documento; so a
 *    navegacao subsequente precisa de correcao.
 *
 *    A guarda compara a **rota anterior**, e nao um sinalizador de "primeira
 *    montagem": em modo estrito o React executa cada efeito duas vezes no
 *    desenvolvimento, e um sinalizador consumido na primeira execucao deixaria
 *    a segunda passar direto. Comparar a rota e idempotente por construcao.
 */

import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import BarraLateral from '@/components/layout/BarraLateral';
import Cabecalho from '@/components/layout/Cabecalho';
import Rodape from '@/components/layout/Rodape';
import { verificarSaude } from '@/lib/api';
import type { Saude } from '@/lib/tipos';

export default function Layout() {
  const [menuAberto, setMenuAberto] = useState(false);
  const [saude, setSaude] = useState<Saude | null>(null);
  const [saudeIndisponivel, setSaudeIndisponivel] = useState(false);
  const { pathname } = useLocation();
  const principalRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const controlador = new AbortController();
    verificarSaude({ signal: controlador.signal })
      .then((resposta) => {
        setSaude(resposta);
        setSaudeIndisponivel(false);
      })
      .catch(() => {
        if (!controlador.signal.aborted) {
          setSaude(null);
          setSaudeIndisponivel(true);
        }
      });
    return () => controlador.abort();
  }, []);

  const rotaAnterior = useRef(pathname);
  useEffect(() => {
    if (rotaAnterior.current === pathname) return;
    rotaAnterior.current = pathname;
    setMenuAberto(false);
    window.scrollTo({ top: 0 });
    principalRef.current?.focus();
  }, [pathname]);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50
                   focus:rounded-[4px] focus:bg-ink focus:px-4 focus:py-2 focus:text-sm focus:text-paper"
      >
        Pular para o conteudo
      </a>

      <BarraLateral
        aberta={menuAberto}
        aoFechar={() => setMenuAberto(false)}
        saude={saude}
        saudeIndisponivel={saudeIndisponivel}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Cabecalho aoAbrirMenu={() => setMenuAberto(true)} />

        <main
          id="conteudo"
          ref={principalRef}
          tabIndex={-1}
          className="flex-1 px-4 py-7 outline-none sm:px-6 sm:py-9"
        >
          <div className="mx-auto w-full max-w-6xl">
            <Outlet context={{ saude }} />
          </div>
        </main>

        <Rodape />
      </div>
    </div>
  );
}
