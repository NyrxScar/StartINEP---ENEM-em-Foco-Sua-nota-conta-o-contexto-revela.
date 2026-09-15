/**
 * Testes de `PainelAnalise` — o fluxo completo com a API mockada (task 12.5;
 * Req 4.3, 4.4, 4.5 e 5.3).
 *
 * Aqui os componentes sao exercitados juntos, do jeito que a pessoa os encontra:
 * preencher a nota, submeter e observar o que a tela passa a dizer. E o unico
 * nivel em que da para afirmar a **exclusividade** dos estados de UI — que
 * carregamento, erro e resultado nunca coexistem — e por isso as assercoes usam
 * `data-estado` (o gancho estavel que a 12.4 deixou no wrapper) junto com o
 * conteudo visivel.
 *
 * O equivalente textual (Req 4.4) e verificado pelas **tabelas**, nao pelo SVG:
 * um grafico que renderiza sozinho nao entrega o resultado a quem usa leitor de
 * tela, entao a garantia de acessibilidade so vale se o teste falhar quando a
 * tabela desaparecer.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import PainelAnalise, { estadoDe } from '@/components/PainelAnalise';
import { CODIGO_ERRO_REDE, CODIGO_TIMEOUT, ErroApi } from '@/lib/api';
import type { ResultadoAnalise } from '@/lib/tipos';

import { analisarMock, deferir, obterCapacidadeMock, prepararApi } from '../test/apiMockada';
import {
  criarLinhagem,
  criarResultado,
  criarResultadoSuprimido,
} from '../test/fixtures';

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...real,
    analisar: vi.fn(),
    listarEdicoes: vi.fn(),
    obterCapacidade: vi.fn(),
  };
});

const ROTULO_NOTA = 'Sua nota (de 0 a 1000)';
const NOME_ENVIO = 'Ver minha posicao';

/** O `data-estado` vigente do painel (gancho de teste da 12.4). */
function estadoNoDom(): string | null {
  return document.querySelector('[data-estado]')?.getAttribute('data-estado') ?? null;
}

/** Monta o painel, preenche a nota e submete. */
async function submeter(nota = '650') {
  const usuario = userEvent.setup();
  render(<PainelAnalise />);

  await screen.findAllByRole('option', { name: /^\d{4}/ });
  await waitFor(() => {
    expect(obterCapacidadeMock).toHaveBeenCalled();
  });

  const botao = screen.getByRole('button', { name: NOME_ENVIO });
  await waitFor(() => {
    expect(botao).toBeEnabled();
  });

  await usuario.type(screen.getByLabelText(ROTULO_NOTA), nota);
  await usuario.click(botao);
  return usuario;
}

describe('estadoDe', () => {
  const erro = new ErroApi({ codigo: 'RECORTE_INDISPONIVEL', mensagem: 'x' });

  it('sem sinais, o painel esta ocioso', () => {
    expect(estadoDe(false, null, null)).toEqual({ tipo: 'ocioso' });
  });

  it('carregamento tem precedencia sobre erro e resultado anteriores', () => {
    expect(estadoDe(true, erro, criarResultado())).toEqual({ tipo: 'carregando' });
  });

  it('erro tem precedencia sobre resultado anterior', () => {
    expect(estadoDe(false, erro, criarResultado())).toEqual({ tipo: 'erro', erro });
  });

  it('resultado marcado como insuficiente vira estado proprio', () => {
    const resultado = criarResultadoSuprimido();
    expect(estadoDe(false, null, resultado)).toEqual({
      tipo: 'amostra-insuficiente',
      resultado,
    });
  });

  it('detalhes anulados pela guarda de privacidade tambem sao insuficiencia', () => {
    const semDistribuicao = criarResultado({ distribuicao: null });
    expect(estadoDe(false, null, semDistribuicao).tipo).toBe('amostra-insuficiente');

    const semPercentil = criarResultado({ percentil: null });
    expect(estadoDe(false, null, semPercentil).tipo).toBe('amostra-insuficiente');
  });

  it('resultado completo e exibido como resultado', () => {
    const resultado = criarResultado();
    expect(estadoDe(false, null, resultado)).toEqual({ tipo: 'resultado', resultado });
  });
});

describe('PainelAnalise — resultado bem-sucedido (Req 4.3/4.4)', () => {
  it('exibe o percentil e o equivalente textual da distribuicao', async () => {
    prepararApi();
    analisarMock.mockResolvedValue(criarResultado());
    await submeter();

    const tabelaQuantis = await screen.findByRole('table', {
      name: /Quantis das notas de Ciencias da Natureza/,
    });
    expect(estadoNoDom()).toBe('resultado');

    // Percentil em prosa, nao apenas no grafico.
    expect(
      screen.getByText(/esta acima de 72,5% das notas do grupo comparado na edicao 2023/),
    ).toBeInTheDocument();
    expect(screen.getByText(/1\.234 pessoas com nota valida/)).toBeInTheDocument();

    // Equivalente textual: os mesmos numeros do SVG em tabela navegavel.
    expect(within(tabelaQuantis).getByRole('rowheader', { name: 'Mediana' })).toBeInTheDocument();
    expect(within(tabelaQuantis).getByRole('cell', { name: '520,0' })).toBeInTheDocument();
    expect(within(tabelaQuantis).getByRole('cell', { name: '450,0' })).toBeInTheDocument();
    expect(within(tabelaQuantis).getByRole('cell', { name: '610,0' })).toBeInTheDocument();

    const tabelaFaixas = screen.getByRole('table', { name: /por faixa no grupo comparado/ });
    expect(
      within(tabelaFaixas).getByRole('rowheader', { name: '500,0 a 600,0' }),
    ).toBeInTheDocument();
    expect(within(tabelaFaixas).getByRole('cell', { name: 'sua nota esta aqui' })).toBeInTheDocument();

    // O grafico existe, mas como reforco: tem nome acessivel proprio.
    expect(screen.getByRole('img', { name: /Histograma das notas/ })).toBeInTheDocument();
  });

  it('apresenta a linhagem do resultado exibido (Req 5.3)', async () => {
    prepararApi();
    analisarMock.mockResolvedValue(criarResultado());
    await submeter();

    const linhagem = await screen.findByRole('region', { name: 'Origem dos dados' });
    expect(within(linhagem).getByText(/Edicao 2023/)).toBeInTheDocument();
    expect(within(linhagem).getByText(/dados carregados em 12 de mar/)).toBeInTheDocument();
    expect(within(linhagem).getByText('sha256:abc123')).toBeInTheDocument();
  });

  it('linhagem sem manifesto e sem data de carga e exibida como ausencia', async () => {
    prepararApi();
    analisarMock.mockResolvedValue(
      criarResultado({
        linhagem: criarLinhagem({
          edicoes: [2023],
          manifestos: { '2023': null },
          datas_carga: { '2023': null },
        }),
      }),
    );
    await submeter();

    const linhagem = await screen.findByRole('region', { name: 'Origem dos dados' });
    expect(within(linhagem).getByText(/data de carga nao disponivel/)).toBeInTheDocument();
    expect(
      within(linhagem).getByText(/Manifesto nao disponivel nesta instalacao/),
    ).toBeInTheDocument();
    expect(linhagem.textContent).not.toContain('null');
    expect(linhagem.textContent).not.toContain('Invalid Date');
    expect(linhagem.textContent).not.toContain('undefined');
  });
});

describe('PainelAnalise — carregamento (Req 4.5)', () => {
  it('anuncia a consulta em andamento e nada mais', async () => {
    prepararApi();
    const emVoo = deferir<ResultadoAnalise>();
    analisarMock.mockReturnValue(emVoo.promessa);
    await submeter();

    expect(await screen.findByText('Consultando a distribuicao...')).toBeInTheDocument();
    expect(estadoNoDom()).toBe('carregando');
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    emVoo.resolver(criarResultado());

    await screen.findByRole('table', { name: /Quantis das notas/ });
    expect(estadoNoDom()).toBe('resultado');
    expect(screen.queryByText('Consultando a distribuicao...')).toBeNull();
  });
});

describe('PainelAnalise — amostra insuficiente (Req 4.4)', () => {
  it('explica a supressao sem percentil e sem contagens', async () => {
    prepararApi();
    analisarMock.mockResolvedValue(criarResultadoSuprimido());
    await submeter();

    const explicacao = await screen.findByText(/pequeno demais para divulgar a distribuicao/);
    expect(explicacao).toHaveAttribute('role', 'status');
    expect(estadoNoDom()).toBe('amostra-insuficiente');

    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByText(/esta acima de/)).toBeNull();
    expect(screen.queryByText(/pessoas com nota valida/)).toBeNull();

    const painel = screen.getByRole('region', { name: 'Sua posicao' });
    expect(painel.textContent).not.toMatch(/\d+,\d/);
  });
});

describe('PainelAnalise — estados de erro (Req 4.3)', () => {
  it('recorte indisponivel lista as edicoes que suportam o recorte', async () => {
    prepararApi();
    analisarMock.mockRejectedValue(
      new ErroApi({
        codigo: 'RECORTE_INDISPONIVEL',
        mensagem: 'O recorte por renda_familiar nao esta disponivel na edicao 2023.',
        detalhes: {
          dimensao: 'renda_familiar',
          edicao: 2023,
          edicoes_que_suportam: [2022, 2021],
        },
        status: 409,
        temEnvelope: true,
      }),
    );
    await submeter();

    const alerta = await screen.findByRole('alert');
    expect(estadoNoDom()).toBe('erro');
    expect(
      within(alerta).getByRole('heading', {
        name: 'Este recorte nao esta disponivel nesta edicao',
      }),
    ).toBeInTheDocument();
    expect(
      within(alerta).getByText(/O recorte por Renda familiar nao existe nos dados publicados na edicao 2023/),
    ).toBeInTheDocument();
    expect(within(alerta).getByText(/nas edicoes 2021 e 2022/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('API inalcancavel produz mensagem humana, sem despejo tecnico', async () => {
    prepararApi();
    analisarMock.mockRejectedValue(
      new ErroApi({
        codigo: CODIGO_ERRO_REDE,
        mensagem: 'Nao foi possivel contatar a API do Radar ENEM.',
        detalhes: { url_base: 'http://localhost:8000' },
      }),
    );
    await submeter();

    const alerta = await screen.findByRole('alert');
    expect(
      within(alerta).getByRole('heading', { name: 'Nao conseguimos falar com a API' }),
    ).toBeInTheDocument();
    expect(within(alerta).getByText(/Confira sua conexao/)).toBeInTheDocument();
    expect(alerta.textContent).not.toContain('url_base');
    expect(alerta.textContent).not.toContain('localhost');
    expect(alerta.textContent).not.toContain('{');
  });

  it('timeout informa a espera sem expor detalhes crus', async () => {
    prepararApi();
    analisarMock.mockRejectedValue(
      new ErroApi({
        codigo: CODIGO_TIMEOUT,
        mensagem: 'A API nao respondeu em 30 segundos.',
        detalhes: { timeout_ms: 30_000 },
      }),
    );
    await submeter();

    const alerta = await screen.findByRole('alert');
    expect(
      within(alerta).getByRole('heading', {
        name: 'A consulta demorou mais do que o esperado',
      }),
    ).toBeInTheDocument();
    expect(within(alerta).getByText(/em 30 segundos/)).toBeInTheDocument();
    expect(alerta.textContent).not.toContain('timeout_ms');
    expect(alerta.textContent).not.toContain('30000');
  });
});
