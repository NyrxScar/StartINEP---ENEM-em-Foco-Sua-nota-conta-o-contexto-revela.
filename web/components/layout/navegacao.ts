/**
 * Secoes do painel, em um so lugar.
 *
 * A barra lateral, a busca do cabecalho e as rotas leem desta lista, de modo
 * que acrescentar uma secao e editar um item — e nao tres arquivos que podem
 * divergir entre si.
 *
 * Toda secao tem endpoint que a sustente. O que varia e *quanto* cada edicao
 * publica: o perfil de escola depende de a pessoa declarar vinculo escolar, e a
 * consulta por instituicao so funciona em 2024, unica edicao com CO_ESCOLA. Essa
 * variacao e dita dentro de cada pagina, a partir da capacidade da edicao, e nao
 * presumida aqui.
 */

import {
  ChartColumnBig,
  Database,
  GitCompareArrows,
  LayoutDashboard,
  School,
  type LucideIcon,
} from 'lucide-react';

export interface ItemNavegacao {
  para: string;
  rotulo: string;
  descricao: string;
  icone: LucideIcon;
}

export const NAVEGACAO: ItemNavegacao[] = [
  {
    para: '/',
    rotulo: 'Diagnostico',
    descricao: 'Sua nota dentro de um recorte comparavel',
    icone: LayoutDashboard,
  },
  {
    para: '/escolas',
    rotulo: 'Perfil de escola',
    descricao: 'Nota por tipo, rede e localizacao',
    icone: School,
  },
  {
    para: '/panorama',
    rotulo: 'Panorama ENEM',
    descricao: 'O que cada edicao publica',
    icone: ChartColumnBig,
  },
  {
    para: '/comparativo',
    rotulo: 'Comparar edicoes',
    descricao: 'A mesma nota ao longo dos anos',
    icone: GitCompareArrows,
  },
  {
    para: '/explorador',
    rotulo: 'Explorador de dados',
    descricao: 'Quebrar uma area por qualquer dimensao',
    icone: Database,
  },
];
