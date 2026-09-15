import type { NextConfig } from 'next';

/**
 * Configuracao do Next.js do frontend do Radar ENEM.
 *
 * `output: 'standalone'` existe para a imagem Docker (task 13.2): o build
 * emite `.next/standalone/` com um `server.js` e apenas o subconjunto de
 * `node_modules` efetivamente alcancado pelo tracing de dependencias. Assim a
 * imagem de runtime nao precisa do `node_modules` completo nem de `npm`, e o
 * frontend continua sendo empacotado de forma independente da imagem da API
 * (Req 7.1).
 *
 * `reactStrictMode` fica ligado por ser o default recomendado do App Router.
 */
const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
};

export default nextConfig;
