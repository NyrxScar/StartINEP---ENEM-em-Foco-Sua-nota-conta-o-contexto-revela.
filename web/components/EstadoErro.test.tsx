/**
 * Testes de `EstadoErro` (task 12.5; Req 4.3).
 *
 * O cliente real (`lib/api.ts`) e usado sem duble: os erros aqui sao instancias
 * de `ErroApi` construidas como o cliente as constroi, inclusive com os codigos
 * sinteticos de transporte. Testar a ramificacao com um objeto qualquer
 * dublando o erro verificaria o duble, nao o produto.
 *
 * Duas invariantes guiam as assercoes: cada codigo conhecido produz uma
 * explicacao acionavel (o que aconteceu **e** o que fazer), e nenhum caso
 * derrama `detalhes` na tela — o envelope e para a maquina, o texto e para a
 * pessoa.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import EstadoErro, { edicoesQueSuportam, mensagemDe } from '@/components/EstadoErro';
import {
  CODIGO_ERRO_REDE,
  CODIGO_RESPOSTA_INVALIDA,
  CODIGO_TIMEOUT,
  ErroApi,
} from '@/lib/api';

/** Atalho para montar um erro com envelope, como a API o entrega. */
function erroApi(
  codigo: string,
  detalhes: Record<string, unknown> = {},
  mensagem = 'Mensagem crua da API.',
): ErroApi {
  return new ErroApi({ codigo, mensagem, detalhes, status: 409, temEnvelope: true });
}

describe('edicoesQueSuportam', () => {
  it('devolve lista vazia quando o detalhe esta ausente ou nao e lista', () => {
    expect(edicoesQueSuportam({})).toEqual([]);
    expect(edicoesQueSuportam({ edicoes_que_suportam: null })).toEqual([]);
    expect(edicoesQueSuportam({ edicoes_que_suportam: '2023' })).toEqual([]);
  });

  it('mantem apenas numeros finitos, sem duplicatas e em ordem crescente', () => {
    expect(
      edicoesQueSuportam({
        edicoes_que_suportam: [2023, '2022', 2021, 2021, Number.NaN, null, 2022],
      }),
    ).toEqual([2021, 2022, 2023]);
  });
});

describe('mensagemDe', () => {
  it('usa a mensagem do envelope para codigos fora do mapa', () => {
    const mensagem = mensagemDe(erroApi('CODIGO_NOVO_DO_BACKEND', {}, 'Algo especifico.'));
    expect(mensagem.titulo).toBe('Nao foi possivel concluir a analise');
  });

  it('nomeia cada estado conhecido', () => {
    expect(mensagemDe(erroApi('RECORTE_INDISPONIVEL')).titulo).toBe(
      'Este recorte nao esta disponivel nesta edicao',
    );
    expect(mensagemDe(erroApi('EDICAO_SEM_NOTAS')).titulo).toBe(
      'Esta edicao nao tem notas publicadas',
    );
    expect(mensagemDe(erroApi('PERFIL_NOTA_NAO_COMBINAVEL')).titulo).toBe(
      'Nesta edicao perfil e notas nao podem ser cruzados',
    );
    expect(mensagemDe(erroApi(CODIGO_ERRO_REDE)).titulo).toBe(
      'Nao conseguimos falar com a API',
    );
    expect(mensagemDe(erroApi(CODIGO_TIMEOUT)).titulo).toBe(
      'A consulta demorou mais do que o esperado',
    );
    expect(mensagemDe(erroApi(CODIGO_RESPOSTA_INVALIDA)).titulo).toBe(
      'A API respondeu de forma inesperada',
    );
  });
});

describe('EstadoErro — recorte indisponivel (Req 4.3)', () => {
  it('explica o recorte e indica as edicoes que o suportam', () => {
    render(
      <EstadoErro
        erro={erroApi('RECORTE_INDISPONIVEL', {
          dimensao: 'renda_familiar',
          edicao: 2024,
          edicoes_que_suportam: [2023, 2022],
        })}
      />,
    );

    const alerta = screen.getByRole('alert');
    expect(
      screen.getByRole('heading', { name: 'Este recorte nao esta disponivel nesta edicao' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/O recorte por Renda familiar nao existe nos dados publicados na edicao 2024/),
    ).toBeInTheDocument();
    expect(screen.getByText(/nas edicoes 2022 e 2023/)).toBeInTheDocument();
    expect(alerta).toHaveTextContent('Codigo do erro: RECORTE_INDISPONIVEL');
  });

  it('sem edicoes que suportem, orienta a remover o filtro', () => {
    render(
      <EstadoErro
        erro={erroApi('RECORTE_INDISPONIVEL', {
          dimensao: 'escolaridade_pai',
          edicoes_que_suportam: [],
        })}
      />,
    );

    expect(
      screen.getByText(/Nenhuma edicao disponivel na base publica este recorte/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/O recorte por Escolaridade do pai nao existe nos dados publicados nesta edicao/),
    ).toBeInTheDocument();
  });

  it('uma unica edicao e anunciada no singular', () => {
    render(
      <EstadoErro
        erro={erroApi('RECORTE_INDISPONIVEL', { edicoes_que_suportam: [2022] })}
      />,
    );
    expect(screen.getByText(/na edicao 2022\. Troque a edicao/)).toBeInTheDocument();
  });
});

describe('EstadoErro — limitacoes da edicao (Req 4.3)', () => {
  it('edicao sem notas orienta a trocar de edicao', () => {
    render(<EstadoErro erro={erroApi('EDICAO_SEM_NOTAS', { edicao: 2025 })} />);

    expect(screen.getByText(/Os microdados na edicao 2025/)).toBeInTheDocument();
    expect(
      screen.getByText(/Escolha uma edicao com notas publicadas para ver seu percentil/),
    ).toBeInTheDocument();
  });

  it('perfil nao combinavel orienta a remover os filtros de perfil', () => {
    render(<EstadoErro erro={erroApi('PERFIL_NOTA_NAO_COMBINAVEL', { edicao: 2024 })} />);

    expect(screen.getByText(/Remova os filtros de perfil/)).toBeInTheDocument();
  });
});

describe('EstadoErro — falhas de transporte (Req 4.3)', () => {
  it('erro de rede nao expoe a URL nem o corpo da falha', () => {
    render(
      <EstadoErro
        erro={
          new ErroApi({
            codigo: CODIGO_ERRO_REDE,
            mensagem: 'Nao foi possivel contatar a API do Radar ENEM.',
            detalhes: { url_base: 'http://localhost:8000' },
          })
        }
      />,
    );

    const alerta = screen.getByRole('alert');
    expect(screen.getByText(/A requisicao nao chegou ao servico de analise/)).toBeInTheDocument();
    expect(alerta.textContent).not.toContain('url_base');
    expect(alerta.textContent).not.toContain('localhost');
  });

  it('timeout informa quanto tempo foi esperado', () => {
    render(
      <EstadoErro
        erro={
          new ErroApi({
            codigo: CODIGO_TIMEOUT,
            mensagem: 'A API nao respondeu em 30 segundos.',
            detalhes: { timeout_ms: 30_000 },
          })
        }
      />,
    );

    const alerta = screen.getByRole('alert');
    expect(screen.getByText(/A API nao respondeu em 30 segundos/)).toBeInTheDocument();
    expect(alerta.textContent).not.toContain('timeout_ms');
    expect(alerta.textContent).not.toContain('30000');
  });

  it('codigo desconhecido exibe a mensagem do envelope em vez de engoli-la', () => {
    render(<EstadoErro erro={erroApi('CAPACIDADE_INDETERMINADA', {}, 'Contrato ilegivel.')} />);

    expect(screen.getByText('Contrato ilegivel.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Codigo do erro: CAPACIDADE_INDETERMINADA',
    );
  });
});
