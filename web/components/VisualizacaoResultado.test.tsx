/**
 * Testes de `VisualizacaoResultado` (task 12.5; Req 4.2 e 4.4).
 *
 * Nao ha API aqui: o componente e uma funcao do `ResultadoAnalise` para o DOM,
 * entao os testes o alimentam direto com fixtures. Duas garantias sao o alvo:
 *
 * 1. **O grafico nunca e o unico portador do resultado.** O SVG e verificado
 *    apenas por ter nome acessivel; o conteudo e cobrado das tabelas de quantis
 *    e de faixas, que precisam trazer os mesmos numeros.
 * 2. **Amostra insuficiente nao inventa numero.** Nenhuma tabela, nenhum
 *    grafico, nenhuma contagem — so a explicacao.
 *
 * `estimarPosicao` tem teste unitario proprio porque e a unica aritmetica do
 * componente e a fonte do marcador "sua nota esta aqui": um erro ali desloca a
 * leitura da propria posicao.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import VisualizacaoResultado, { estimarPosicao } from '@/components/VisualizacaoResultado';
import type { FaixaHistograma } from '@/lib/tipos';

import {
  criarDistribuicao,
  criarFaixas,
  criarResultado,
  criarResultadoSuprimido,
} from '../test/fixtures';

describe('estimarPosicao', () => {
  const faixas = criarFaixas(); // 10 / 30 / 40 / 20 pessoas, total 100

  it('nao posiciona nada quando nao ha histograma', () => {
    expect(estimarPosicao([], 50)).toBeNull();
  });

  it('nao posiciona nada quando todas as contagens sao zero', () => {
    const vazias: FaixaHistograma[] = [
      { limite_inferior: 0, limite_superior: 500, contagem: 0 },
      { limite_inferior: 500, limite_superior: 1000, contagem: 0 },
    ];
    expect(estimarPosicao(vazias, 50)).toBeNull();
  });

  it('interpola a posicao dentro da faixa que contem o percentil', () => {
    // Cumulativo 10/40/80/100; o percentil 72,5 cai na terceira faixa.
    expect(estimarPosicao(faixas, 72.5)).toEqual({
      indice: 2,
      fracao: 0.8125,
      nota: 581.25,
    });
  });

  it('ancora os extremos no inicio da primeira e no fim da ultima faixa', () => {
    expect(estimarPosicao(faixas, 0)).toEqual({ indice: 0, fracao: 0, nota: 300 });
    expect(estimarPosicao(faixas, 100)).toEqual({ indice: 3, fracao: 1, nota: 700 });
  });

  it('trata percentis fora de 0..100 como os proprios limites', () => {
    expect(estimarPosicao(faixas, -10)).toEqual(estimarPosicao(faixas, 0));
    expect(estimarPosicao(faixas, 150)).toEqual(estimarPosicao(faixas, 100));
  });
});

describe('VisualizacaoResultado — equivalente textual (Req 4.4)', () => {
  it('descreve a distribuicao em prosa e em tabelas, alem do grafico', () => {
    render(<VisualizacaoResultado resultado={criarResultado()} />);

    expect(
      screen.getByText(/Sua nota de Ciencias da Natureza esta acima de 72,5%/),
    ).toBeInTheDocument();

    const grafico = screen.getByRole('img', {
      name: /Histograma das notas de Ciencias da Natureza na edicao 2023/,
    });
    expect(grafico).toHaveAccessibleName(/Os mesmos numeros estao nas tabelas a seguir/);

    const quantis = screen.getByRole('table', { name: /Quantis das notas/ });
    expect(within(quantis).getByRole('rowheader', { name: 'Menor nota (minimo)' })).toBeInTheDocument();
    expect(within(quantis).getByRole('cell', { name: '300,0' })).toBeInTheDocument();
    expect(within(quantis).getByRole('rowheader', { name: 'Mediana' })).toBeInTheDocument();
    expect(within(quantis).getByRole('cell', { name: '520,0' })).toBeInTheDocument();
    expect(within(quantis).getByRole('cell', { name: '700,0' })).toBeInTheDocument();
  });

  it('detalha cada faixa do grafico e marca a faixa da propria nota', () => {
    render(<VisualizacaoResultado resultado={criarResultado()} />);

    expect(screen.getByText('Numeros de cada faixa do grafico')).toBeInTheDocument();

    const faixas = screen.getByRole('table', { name: /por faixa no grupo comparado/ });
    expect(within(faixas).getByRole('rowheader', { name: '300,0 a 400,0' })).toBeInTheDocument();
    expect(within(faixas).getByRole('rowheader', { name: '600,0 a 700,0' })).toBeInTheDocument();
    expect(within(faixas).getByRole('cell', { name: '40' })).toBeInTheDocument();
    expect(within(faixas).getByRole('cell', { name: '40,0%' })).toBeInTheDocument();

    const marcadores = within(faixas).getAllByRole('cell', { name: 'sua nota esta aqui' });
    expect(marcadores).toHaveLength(1);
  });

  it('sem faixas, os quantis ainda descrevem a distribuicao', () => {
    render(
      <VisualizacaoResultado
        resultado={criarResultado({ distribuicao: criarDistribuicao({ faixas: [] }) })}
      />,
    );

    expect(screen.getByText(/O histograma nao esta disponivel para este recorte/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('table', { name: /Quantis das notas/ })).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: /por faixa/ })).toBeNull();
  });
});

describe('VisualizacaoResultado — amostra insuficiente (Req 4.4)', () => {
  it('explica a supressao e nao expoe percentil, quantis nem contagens', () => {
    render(<VisualizacaoResultado resultado={criarResultadoSuprimido()} />);

    const aviso = screen.getByRole('status');
    expect(aviso).toHaveTextContent(/pequeno demais para divulgar a distribuicao com seguranca/);
    expect(aviso).toHaveTextContent(/Escolha um recorte mais amplo/);

    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByText(/esta acima de/)).toBeNull();
    expect(screen.queryByText(/pessoas com nota valida/)).toBeNull();
  });
});
