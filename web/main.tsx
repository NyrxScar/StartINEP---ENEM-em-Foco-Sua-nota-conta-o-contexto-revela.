/**
 * Ponto de entrada do bundle. Monta a aplicacao sob `BrowserRouter` para que
 * cada secao do painel tenha URL propria — um diagnostico ou um comparativo
 * precisa ser compartilhavel por link, e o botao voltar do navegador precisa
 * funcionar como a pessoa espera.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from '@/App';
import '@/styles.css';

const raiz = document.getElementById('raiz');
if (raiz === null) throw new Error('Elemento #raiz ausente no index.html.');

createRoot(raiz).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
