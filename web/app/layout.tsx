import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Radar ENEM — sua nota conta, o contexto revela',
  description:
    'Informe sua nota do ENEM e veja sua posicao na distribuicao dentro de um recorte comparavel.',
};

// Layout utilizavel a partir de 320px (design, secao Frontend/Responsividade).
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

/**
 * Layout raiz do App Router.
 *
 * `lang="pt-BR"` e obrigatorio para leitores de tela pronunciarem o conteudo
 * corretamente (WCAG 3.1.1 — Req 4.4). A estrutura usa marcos semanticos
 * (`header`/`main`/`footer`) e um link "pular para o conteudo", de modo que os
 * componentes das tasks 12.2–12.4 entrem dentro de `<main id="conteudo">` sem
 * precisar reintroduzir semantica.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <a className="pular-para-conteudo" href="#conteudo">
          Pular para o conteudo
        </a>
        <header>
          <p className="marca">Radar ENEM</p>
        </header>
        <main id="conteudo">{children}</main>
        <footer>
          <p>
            Dados: microdados publicos do ENEM (INEP). O Radar ENEM apresenta apenas
            estatisticas agregadas.
          </p>
        </footer>
      </body>
    </html>
  );
}
