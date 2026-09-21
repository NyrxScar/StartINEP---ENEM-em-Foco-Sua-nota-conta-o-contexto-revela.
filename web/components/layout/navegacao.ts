/**
 * Secoes do painel, em um so lugar.
 *
 * A barra lateral, a busca do cabecalho e as rotas leem desta lista, de modo
 * que acrescentar uma secao e editar um item — e nao tres arquivos que podem
 * divergir entre si.
 *
 * `apoiada` marca se a secao tem endpoint que a sustente. As duas secoes com
 * `apoiada: false` continuam navegaveis de proposito: a API do Radar ENEM e
 * agregada e anonimizada por desenho, sem dado por escola nem linha por
 * participante, e a interface prefere dizer isso em uma tela honesta a esconder
 * a secao e deixar a limitacao invisivel.
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
  apoiada: boolean;
}

export const NAVEGACAO: ItemNavegacao[] = [
  {
    para: '/',
    rotulo: 'Diagnostico',
    descricao: 'Sua nota dentro de um recorte comparavel',
    icone: LayoutDashboard,
    apoiada: true,
  },
  {
    para: '/escolas',
    rotulo: 'Relatorios por escola',
    descricao: 'Desempenho agregado por instituicao',
    icone: School,
    apoiada: false,
  },
  {
    para: '/panorama',
    rotulo: 'Panorama ENEM',
    descricao: 'O que cada edicao publica',
    icone: ChartColumnBig,
    apoiada: true,
  },
  {
    para: '/comparativo',
    rotulo: 'Comparar edicoes',
    descricao: 'A mesma nota ao longo dos anos',
    icone: GitCompareArrows,
    apoiada: true,
  },
  {
    para: '/explorador',
    rotulo: 'Explorador de dados',
    descricao: 'Consulta livre sobre a base',
    icone: Database,
    apoiada: false,
  },
];
