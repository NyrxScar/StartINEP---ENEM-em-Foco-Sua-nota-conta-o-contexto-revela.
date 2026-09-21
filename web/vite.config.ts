/**
 * Build e dev-server do frontend (Vite + React + Tailwind v4).
 *
 * Decisoes:
 *
 * 1. **O alias `@` aponta para a raiz do projeto**, nao para `src/`. Os modulos
 *    ja viviam em `lib/`, `components/` e `test/` na raiz desde a versao Next;
 *    manter o mesmo especificador (`@/lib/api`) significa que nenhum import
 *    mudou na migracao e que `vi.mock('@/lib/api')` continua interceptando
 *    exatamente o mesmo modulo que o componente carrega.
 * 2. **Tailwind entra pelo plugin oficial do Vite** (v4), sem `tailwind.config.js`
 *    nem PostCSS: os tokens de design sao declarados em `@theme` dentro de
 *    `styles.css`, que e a fonte unica da paleta.
 * 3. **`manualChunks` separa o vendor** para que uma troca de codigo da aplicacao
 *    nao invalide o cache do React/React Router no navegador. `react-dom/client`
 *    e listado a parte: e um especificador distinto de `react-dom` e, sem ele,
 *    o runtime inteiro do DOM cai no chunk da aplicacao.
 */

import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('.', import.meta.url)) },
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-dom/client', 'react-router-dom'],
        },
      },
    },
  },
  server: { port: 5173 },
});
