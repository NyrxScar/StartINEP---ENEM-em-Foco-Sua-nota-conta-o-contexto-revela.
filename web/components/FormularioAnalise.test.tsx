/**
 * Testes de componente de `FormularioAnalise` — entrada guiada pela capacidade
 * (task 12.5; Req 4.2 e 4.6).
 *
 * O que estes testes protegem:
 *
 * - **Nota fora de 0–1000 nunca chega a API** (Req 4.2). A guarda client-side
 *   existe para dar retorno imediato; se ela falhar em silencio, a pessoa recebe
 *   um 422 vindo de longe. Por isso cada caso afirma as tres consequencias
 *   juntas: mensagem anunciada, `aria-invalid` no campo e `analisar` **nao**
 *   chamado.
 * - **A capacidade da edicao remove o impossivel da tela** (Req 4.6): dimensao
 *   nao suportada nao aparece, perfil nao combinavel com nota nao aparece, e
 *   edicao sem notas desabilita a submissao com a razao visivel e associada ao
 *   botao.
 *
 * As consultas sao por rotulo e por papel de proposito: se um `<label htmlFor>`
 * se desconectar do controle, ou o botao perder o nome acessivel, o teste falha —
 * ou seja, a afordancia de acessibilidade e parte do que esta sob teste (Req 4.4).
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import FormularioAnalise, { validarNota } from '@/components/FormularioAnalise';
import type { ResultadoAnalise } from '@/lib/tipos';

import {
  analisarMock,
  deferir,
  obterCapacidadeMock,
  prepararApi,
} from '../test/apiMockada';
import { criarCapacidade, criarInfoEdicao, criarResultado } from '../test/fixtures';

// Apenas as funcoes de rede sao dubladas; `ErroApi` e os codigos sinteticos
// continuam sendo os reais (ver test/apiMockada.ts).
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

/** Monta o formulario e espera o catalogo/capacidade assentarem. */
async function montar() {
  const onResultado = vi.fn();
  const onErro = vi.fn();
  const onCarregando = vi.fn();

  render(
    <FormularioAnalise
      onResultado={onResultado}
      onErro={onErro}
      onCarregando={onCarregando}
    />,
  );

  await screen.findAllByRole('option', { name: /^\d{4}/ });
  await waitFor(() => {
    expect(obterCapacidadeMock).toHaveBeenCalled();
  });

  return { onResultado, onErro, onCarregando };
}

describe('validarNota', () => {
  it('recusa texto vazio, nao numerico e fora de 0..1000', () => {
    expect(validarNota('')).toEqual({
      ok: false,
      mensagem: 'Informe sua nota para calcular a posicao.',
    });
    expect(validarNota('   ')).toEqual({
      ok: false,
      mensagem: 'Informe sua nota para calcular a posicao.',
    });
    expect(validarNota('abc')).toEqual({
      ok: false,
      mensagem: 'A nota deve ser um numero, como 623.5.',
    });
    expect(validarNota('-0.1')).toEqual({
      ok: false,
      mensagem: 'A nota deve estar entre 0 e 1000.',
    });
    expect(validarNota('1000.1')).toEqual({
      ok: false,
      mensagem: 'A nota deve estar entre 0 e 1000.',
    });
  });

  it('aceita os limites do intervalo e virgula decimal', () => {
    expect(validarNota('0')).toEqual({ ok: true, nota: 0 });
    expect(validarNota('1000')).toEqual({ ok: true, nota: 1000 });
    expect(validarNota(' 623,5 ')).toEqual({ ok: true, nota: 623.5 });
  });
});

describe('FormularioAnalise — validacao de nota (Req 4.2)', () => {
  it('nota acima de 1000 produz erro acessivel e nao chama a API', async () => {
    prepararApi();
    const usuario = userEvent.setup();
    await montar();

    const campoNota = screen.getByLabelText(ROTULO_NOTA);
    await usuario.type(campoNota, '1500');
    await usuario.click(screen.getByRole('button', { name: NOME_ENVIO }));

    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('A nota deve estar entre 0 e 1000.');
    expect(campoNota).toHaveAttribute('aria-invalid', 'true');
    expect((campoNota.getAttribute('aria-describedby') ?? '').split(' ')).toContain(
      alerta.id,
    );
    expect(campoNota).toHaveFocus();
    expect(analisarMock).not.toHaveBeenCalled();
  });

  it('nota negativa nao chama a API', async () => {
    prepararApi();
    const usuario = userEvent.setup();
    await montar();

    await usuario.type(screen.getByLabelText(ROTULO_NOTA), '-5');
    await usuario.click(screen.getByRole('button', { name: NOME_ENVIO }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A nota deve estar entre 0 e 1000.',
    );
    expect(analisarMock).not.toHaveBeenCalled();
  });

  it('submissao sem nota exibe o pedido de preenchimento', async () => {
    prepararApi();
    const usuario = userEvent.setup();
    await montar();

    await usuario.click(screen.getByRole('button', { name: NOME_ENVIO }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Informe sua nota para calcular a posicao.',
    );
    expect(analisarMock).not.toHaveBeenCalled();
  });

  it.each<[string, number]>([
    ['0', 0],
    ['1000', 1000],
  ])('aceita a nota-limite %s e submete o recorte vazio', async (texto, nota) => {
    prepararApi();
    analisarMock.mockResolvedValue(criarResultado());
    const usuario = userEvent.setup();
    const { onResultado } = await montar();

    await usuario.type(screen.getByLabelText(ROTULO_NOTA), texto);
    await usuario.click(screen.getByRole('button', { name: NOME_ENVIO }));

    await waitFor(() => {
      expect(onResultado).toHaveBeenCalledTimes(1);
    });
    expect(analisarMock).toHaveBeenCalledWith(
      { edicao: 2023, area: 'cn', nota, recorte: { filtros: {} } },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('FormularioAnalise — capacidade da edicao (Req 4.6)', () => {
  it('oferece apenas as dimensoes suportadas pela edicao', async () => {
    prepararApi({
      edicoes: [
        criarInfoEdicao({
          edicao: 2023,
          capacidade: criarCapacidade({
            edicao: 2023,
            dimensoes_suportadas: ['regiao', 'uf_prova'],
          }),
        }),
      ],
    });
    await montar();

    expect(screen.getByLabelText('Regiao')).toBeInTheDocument();
    expect(screen.getByLabelText('UF da prova')).toBeInTheDocument();
    expect(screen.queryByLabelText('Renda familiar')).toBeNull();
    expect(screen.queryByLabelText('Tipo de escola')).toBeNull();
    expect(screen.getByText(/Indisponiveis:.*Renda familiar/)).toBeInTheDocument();
  });

  it('nao oferece dimensoes de perfil quando perfil e nota nao se combinam', async () => {
    prepararApi({
      edicoes: [
        criarInfoEdicao({
          edicao: 2024,
          capacidade: criarCapacidade({
            edicao: 2024,
            perfil_combinavel_com_notas: false,
          }),
        }),
      ],
    });
    await montar();

    expect(screen.getByLabelText('Regiao')).toBeInTheDocument();
    expect(screen.getByLabelText('Tipo de escola')).toBeInTheDocument();
    expect(screen.queryByLabelText('Renda familiar')).toBeNull();
    expect(screen.queryByLabelText('Cor/raca')).toBeNull();
    expect(screen.queryByLabelText('Escolaridade do pai')).toBeNull();
    expect(screen.queryByLabelText('Escolaridade da mae')).toBeNull();
    expect(
      screen.getByText(/perfil socioeconomico e as notas estao em arquivos/),
    ).toBeInTheDocument();
  });

  it('desabilita a submissao e exibe a razao quando a edicao nao tem notas', async () => {
    prepararApi({
      edicoes: [
        criarInfoEdicao({
          edicao: 2025,
          capacidade: criarCapacidade({ edicao: 2025, possui_notas: false }),
        }),
      ],
    });
    const usuario = userEvent.setup();
    await montar();

    const botao = screen.getByRole('button', { name: NOME_ENVIO });
    await waitFor(() => {
      expect(botao).toBeDisabled();
    });

    const razao = await screen.findByRole('alert');
    expect(razao).toHaveTextContent(/A edicao 2025 nao possui notas publicadas/);
    expect(botao).toHaveAttribute('aria-describedby', razao.id);

    await usuario.type(screen.getByLabelText(ROTULO_NOTA), '650');
    await usuario.click(botao);
    expect(analisarMock).not.toHaveBeenCalled();
  });
});

describe('FormularioAnalise — requisicao em andamento (Req 4.5)', () => {
  it('anuncia o envio ao pai e bloqueia o botao enquanto consulta', async () => {
    prepararApi();
    const emVoo = deferir<ResultadoAnalise>();
    analisarMock.mockReturnValue(emVoo.promessa);
    const usuario = userEvent.setup();
    const { onCarregando, onResultado } = await montar();

    await usuario.type(screen.getByLabelText(ROTULO_NOTA), '650');
    await usuario.click(screen.getByRole('button', { name: NOME_ENVIO }));

    const consultando = await screen.findByRole('button', { name: 'Consultando...' });
    expect(consultando).toBeDisabled();
    expect(onCarregando).toHaveBeenCalledWith(true);

    emVoo.resolver(criarResultado());

    await waitFor(() => {
      expect(onResultado).toHaveBeenCalledTimes(1);
    });
    expect(onCarregando).toHaveBeenLastCalledWith(false);
    expect(screen.getByRole('button', { name: NOME_ENVIO })).toBeEnabled();
  });
});
