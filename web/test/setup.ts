/**
 * Setup global dos testes de componente.
 *
 * - `@testing-library/jest-dom/vitest` registra os matchers de DOM
 *   (`toBeDisabled`, `toHaveAttribute`, `toBeInTheDocument`, ...) no `expect` do
 *   Vitest e ja declara os tipos correspondentes.
 * - `cleanup()` desmonta a arvore renderizada apos cada teste. E explicito de
 *   proposito: com `globals: false` a Testing Library nao registra o `afterEach`
 *   automatico, e um componente montado que sobrevive ao teste seguinte
 *   produziria "found multiple elements" em queries por papel/rotulo.
 */

import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
