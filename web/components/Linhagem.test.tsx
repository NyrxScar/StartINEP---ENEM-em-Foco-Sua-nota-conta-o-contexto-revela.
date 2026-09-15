/**
 * Testes de `Linhagem` (task 12.5; Req 5.3).
 *
 * A linhagem existe para responder "de qual edicao e de qual carga vem este
 * numero?". O risco real nao e formatar bonito, e **vazar ausencia**: a silver e
 * seus Manifestos sao contrato de entrada externo, e `manifestos`/`datas_carga`
 * sao anulaveis por tipo. Por isso as assercoes cobram o texto explicito de
 * indisponibilidade e proibem `null`, `undefined` e `Invalid Date` na tela.
 *
 * As datas sao verificadas por trecho (mes e hora), nao por igualdade exata: o
 * formato de `Intl.DateTimeFormat` e detalhe de apresentacao e pode variar entre
 * versoes de ICU; o que precisa valer e que a data aparece legivel.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Linhagem, { formatarDataCarga, itensDaLinhagem } from '@/components/Linhagem';

import { criarLinhagem } from '../test/fixtures';

describe('formatarDataCarga', () => {
  it('devolve null para ausencia, vazio e data nao interpretavel', () => {
    expect(formatarDataCarga(null)).toBeNull();
    expect(formatarDataCarga(undefined)).toBeNull();
    expect(formatarDataCarga('')).toBeNull();
    expect(formatarDataCarga('   ')).toBeNull();
    expect(formatarDataCarga('carga-de-ontem')).toBeNull();
  });

  it('formata um timestamp ISO 8601 em pt-BR', () => {
    const formatada = formatarDataCarga('2025-03-12T14:32:00');
    expect(formatada).toMatch(/12 de mar/);
    expect(formatada).toMatch(/2025/);
    expect(formatada).toMatch(/14:32/);
  });
});

describe('itensDaLinhagem', () => {
  it('ordena as edicoes e resolve manifesto e data de cada uma', () => {
    const itens = itensDaLinhagem(
      criarLinhagem({
        edicoes: [2023, 2021, 2022],
        manifestos: { '2021': 'sha256:a', '2022': '   ', '2023': null },
        datas_carga: { '2021': '2025-03-12T14:32:00', '2022': 'invalida' },
      }),
    );

    expect(itens.map((item) => item.edicao)).toEqual([2021, 2022, 2023]);
    expect(itens).toEqual([
      expect.objectContaining({ edicao: 2021, manifesto: 'sha256:a' }),
      expect.objectContaining({ edicao: 2022, manifesto: null, dataCarga: null }),
      expect.objectContaining({ edicao: 2023, manifesto: null, dataCarga: null }),
    ]);
  });
});

describe('Linhagem — origem dos dados (Req 5.3)', () => {
  it('lista edicao, data de carga e manifesto', () => {
    render(<Linhagem linhagem={criarLinhagem()} />);

    const bloco = screen.getByRole('region', { name: 'Origem dos dados' });
    const itens = within(bloco).getAllByRole('listitem');
    expect(itens).toHaveLength(1);
    expect(within(bloco).getByText('Edicao 2023')).toBeInTheDocument();
    expect(within(bloco).getByText(/dados carregados em 12 de mar/)).toBeInTheDocument();
    expect(within(bloco).getByText('sha256:abc123')).toBeInTheDocument();
  });

  it('exibe ausencia como texto, nunca null nem Invalid Date', () => {
    render(
      <Linhagem
        linhagem={criarLinhagem({
          edicoes: [2024],
          manifestos: { '2024': null },
          datas_carga: { '2024': null },
        })}
      />,
    );

    const bloco = screen.getByRole('region', { name: 'Origem dos dados' });
    expect(within(bloco).getByText(/data de carga nao disponivel/)).toBeInTheDocument();
    expect(
      within(bloco).getByText(/Manifesto nao disponivel nesta instalacao/),
    ).toBeInTheDocument();
    expect(bloco.textContent).not.toContain('null');
    expect(bloco.textContent).not.toContain('undefined');
    expect(bloco.textContent).not.toContain('Invalid Date');
  });

  it('linhagem sem edicoes diz que a resposta nao informou a origem', () => {
    render(<Linhagem linhagem={criarLinhagem({ edicoes: [] })} />);

    expect(
      screen.getByText(/A resposta nao informou quais edicoes fundamentam este resultado/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
  });
});
