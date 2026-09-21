/**
 * Tabela de rotas.
 *
 * Cada secao do painel tem URL propria para que um diagnostico ou um
 * comparativo seja compartilhavel por link e o botao voltar funcione. Todas
 * penduram no mesmo `Layout`, que detem a casca e o estado de saude do servico.
 *
 * As paginas sao carregadas sob demanda: quem abre o Diagnostico nao baixa o
 * codigo do comparativo nem o do panorama. So o Diagnostico e estatico, por ser
 * a rota de entrada — carrega-lo sob demanda custaria um ida-e-volta extra
 * justamente na primeira tela.
 */

import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import Layout from '@/components/layout/Layout';
import { Esqueleto } from '@/components/ui/Carregando';
import Diagnostico from '@/pages/Diagnostico';

const PerfilEscola = lazy(() => import('@/pages/PerfilEscola'));
const Panorama = lazy(() => import('@/pages/Panorama'));
const Comparativo = lazy(() => import('@/pages/Comparativo'));
const Explorador = lazy(() => import('@/pages/Explorador'));

function Aguardando() {
  return (
    <div className="space-y-4" role="status" aria-label="Carregando secao">
      <Esqueleto className="h-8 w-64" />
      <Esqueleto className="h-4 w-full max-w-md" />
      <Esqueleto className="h-52 w-full" />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Diagnostico />} />
        <Route
          path="escolas"
          element={
            <Suspense fallback={<Aguardando />}>
              <PerfilEscola />
            </Suspense>
          }
        />
        <Route
          path="panorama"
          element={
            <Suspense fallback={<Aguardando />}>
              <Panorama />
            </Suspense>
          }
        />
        <Route
          path="comparativo"
          element={
            <Suspense fallback={<Aguardando />}>
              <Comparativo />
            </Suspense>
          }
        />
        <Route
          path="explorador"
          element={
            <Suspense fallback={<Aguardando />}>
              <Explorador />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
