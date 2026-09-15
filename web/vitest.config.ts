/**
 * Configuracao do runner de testes de componente (task 12.5).
 *
 * Decisoes:
 *
 * 1. **Vitest + jsdom + Testing Library**, nao um runner de navegador. A task
 *    pede testes *de componente* com a API mockada; subir Chromium (Playwright/
 *    Cypress) custaria minutos de CI e nao verificaria nada a mais nos casos
 *    cobertos aqui. `jsdom` entrega DOM, `role`/`aria-*` e eventos suficientes
 *    para asserir as afordancias de acessibilidade que o design exige (Req 4.4).
 * 2. **Sem `@vitejs/plugin-react`.** O plugin existe para Fast Refresh e para o
 *    Babel do React Compiler; em teste nenhum dos dois se aplica. O `tsconfig`
 *    do Next usa `jsx: "preserve"` (o Next e quem transforma), entao aqui a
 *    transformacao e declarada explicitamente via `esbuild.jsx: 'automatic'` —
 *    uma dependencia a menos e uma cadeia de transitivas a menos.
 * 3. **O alias `@/*` e resolvido aqui**, espelhando `tsconfig.json`
 *    (`paths: {"@/*": ["./*"]}`), para que os componentes sejam importados nos
 *    testes exatamente como sao em producao — e para que `vi.mock('@/lib/api')`
 *    intercepte o mesmo especificador que o componente usa.
 * 4. `globals: false`: `describe`/`it`/`expect` sao importados de `vitest` em
 *    cada arquivo. Explicito, e evita depender de tipos globais no `tsc`.
 */

import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./test/setup.ts'],
    include: ['**/*.test.ts', '**/*.test.tsx'],
    exclude: ['node_modules/**', '.next/**'],
    restoreMocks: true,
  },
});
