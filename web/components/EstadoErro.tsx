/**
 * `EstadoErro` — traduz o envelope de erro da API em uma explicacao acionavel
 * (task 12.4; Req 4.3).
 *
 * Decisoes de projeto:
 *
 * 1. **Ramificacao por `codigo`, nunca por texto.** O cliente (`lib/api.ts`)
 *    preserva `codigo`/`mensagem`/`detalhes` de toda falha — inclusive das que
 *    nao tem envelope, que recebem os codigos sinteticos `ERRO_REDE`,
 *    `TIMEOUT` e `RESPOSTA_INVALIDA`. Aqui cada codigo conhecido vira uma
 *    mensagem em pt-BR que diz o que aconteceu e o que fazer a seguir; a
 *    `mensagem` crua da API e reservada ao caso `default`, para que um codigo
 *    novo no backend apareca na tela em vez de ser engolido.
 * 2. **`detalhes` e lido defensivamente.** O tipo em `lib/tipos.ts`
 *    (`DetalhesRecorteIndisponivel`) descreve a *intencao* do backend, mas em
 *    runtime `detalhes` e `Record<string, unknown>`: um envelope diferente do
 *    esperado nao pode quebrar a renderizacao. Por isso
 *    `edicoes_que_suportam` so e exibida depois de validada como lista de
 *    numeros finitos ({@link edicoesQueSuportam}), e `edicao`/`dimensao`
 *    passam pelos mesmos guardas — sem eles, a mensagem cai para uma versao
 *    generica em vez de imprimir `undefined`.
 * 3. **Nada de detalhe tecnico bruto.** Nenhum caso serializa `detalhes`,
 *    `cause` ou corpo de resposta na tela (Req 4.3: mensagem para a pessoa, nao
 *    despejo de JSON). O `codigo` aparece em uma linha discreta ao final, o
 *    suficiente para um relato de suporte.
 * 4. **Anunciado a tecnologia assistiva**: `role="alert"` na regiao, cabecalho
 *    proprio associado por `aria-labelledby`, e a cor do bloco nunca e o unico
 *    sinal — todo o significado esta no texto.
 */

import type { ReactNode } from 'react';

import {
  CODIGO_ERRO_REDE,
  CODIGO_RESPOSTA_INVALIDA,
  CODIGO_TIMEOUT,
  type ErroApi,
} from '@/lib/api';
import { ROTULOS_DIMENSAO, type Dimensao } from '@/lib/tipos';

/** Numeros de edicao formatados na lista de "edicoes que suportam". */
const FORMATO_EDICAO = new Intl.NumberFormat('pt-BR', { useGrouping: false });

export interface EstadoErroProps {
  erro: ErroApi;
}

/**
 * Extrai `detalhes.edicoes_que_suportam` (Req 2.6/4.3) de forma defensiva.
 *
 * Aceita apenas numeros finitos, remove duplicatas e ordena de forma crescente,
 * para que a orientacao exibida seja estavel. Qualquer outra forma (ausente,
 * nao-lista, itens de outro tipo) resulta em lista vazia — e a UI diz que
 * nenhuma edicao suporta o recorte em vez de inventar.
 */
export function edicoesQueSuportam(detalhes: Record<string, unknown>): number[] {
  const bruto: unknown = detalhes.edicoes_que_suportam;
  if (!Array.isArray(bruto)) return [];
  const validas = bruto.filter(
    (item): item is number => typeof item === 'number' && Number.isFinite(item),
  );
  return Array.from(new Set(validas)).sort((a, b) => a - b);
}

/** Le `detalhes.edicao` quando presente e numerica. */
function edicaoDe(detalhes: Record<string, unknown>): number | null {
  const bruto: unknown = detalhes.edicao;
  return typeof bruto === 'number' && Number.isFinite(bruto) ? bruto : null;
}

/**
 * Le `detalhes.dimensao` e traduz para o rotulo legivel quando e uma dimensao
 * conhecida; um nome desconhecido e mostrado como veio (o backend e a fonte).
 */
function rotuloDimensaoDe(detalhes: Record<string, unknown>): string | null {
  const bruto: unknown = detalhes.dimensao;
  if (typeof bruto !== 'string') return null;
  const chave = bruto.trim();
  if (chave.length === 0) return null;
  return chave in ROTULOS_DIMENSAO ? ROTULOS_DIMENSAO[chave as Dimensao] : chave;
}

/** Le `detalhes.timeout_ms` (posto pelo cliente) em segundos inteiros. */
function segundosDeEspera(detalhes: Record<string, unknown>): number | null {
  const bruto: unknown = detalhes.timeout_ms;
  if (typeof bruto !== 'number' || !Number.isFinite(bruto) || bruto <= 0) return null;
  return Math.round(bruto / 1000);
}

/** "na edicao 2023" quando o envelope diz qual; "nesta edicao" quando nao. */
function naEdicao(edicao: number | null): string {
  return edicao === null ? 'nesta edicao' : `na edicao ${FORMATO_EDICAO.format(edicao)}`;
}

/** Junta numeros de edicao em uma enumeracao legivel ("2022, 2023 e 2025"). */
function enumerarEdicoes(edicoes: number[]): string {
  const rotulos = edicoes.map((edicao) => FORMATO_EDICAO.format(edicao));
  if (rotulos.length <= 1) return rotulos.join('');
  return `${rotulos.slice(0, -1).join(', ')} e ${rotulos[rotulos.length - 1] ?? ''}`;
}

/** Conteudo da mensagem: titulo curto, explicacao e orientacao do que fazer. */
interface Mensagem {
  titulo: string;
  explicacao: ReactNode;
  orientacao: ReactNode;
}

/** Mapeia o `codigo` do envelope para a mensagem exibida. */
export function mensagemDe(erro: ErroApi): Mensagem {
  const { detalhes } = erro;
  const edicao = edicaoDe(detalhes);

  switch (erro.codigo) {
    case 'RECORTE_INDISPONIVEL': {
      const dimensao = rotuloDimensaoDe(detalhes);
      const suportam = edicoesQueSuportam(detalhes);
      return {
        titulo: 'Este recorte nao esta disponivel nesta edicao',
        explicacao: (
          <p>
            {dimensao !== null
              ? `O recorte por ${dimensao} nao existe nos dados publicados ${naEdicao(edicao)}, `
              : `Um dos recortes escolhidos nao existe nos dados publicados ${naEdicao(edicao)}, `}
            portanto nao ha como comparar sua nota dentro dele. Cada edicao publica um
            conjunto diferente de variaveis, e nada aqui e preenchido por estimativa.
          </p>
        ),
        orientacao:
          suportam.length > 0 ? (
            <p>
              Este recorte esta disponivel{' '}
              {suportam.length === 1 ? 'na edicao' : 'nas edicoes'}{' '}
              {enumerarEdicoes(suportam)}. Troque a edicao para usa-lo, ou remova o
              filtro e compare com um grupo mais amplo.
            </p>
          ) : (
            <p>
              Nenhuma edicao disponivel na base publica este recorte. Remova o filtro
              para comparar sua nota com um grupo mais amplo.
            </p>
          ),
      };
    }

    case 'EDICAO_SEM_NOTAS':
      return {
        titulo: 'Esta edicao nao tem notas publicadas',
        explicacao: (
          <p>
            Os microdados {naEdicao(edicao)} trazem inscricoes e perfil, mas ainda nao
            trazem as notas das provas. Sem notas nao existe distribuicao para calcular
            sua posicao.
          </p>
        ),
        orientacao: <p>Escolha uma edicao com notas publicadas para ver seu percentil.</p>,
      };

    case 'PERFIL_NOTA_NAO_COMBINAVEL':
      return {
        titulo: 'Nesta edicao perfil e notas nao podem ser cruzados',
        explicacao: (
          <p>
            {naEdicao(edicao).charAt(0).toUpperCase() + naEdicao(edicao).slice(1)} o perfil
            socioeconomico e as notas foram publicados de forma que nao permite ligar um
            ao outro pessoa por pessoa. Cruzar os dois produziria um numero sem
            sustentacao nos dados, e por isso a consulta e recusada em vez de aproximada.
          </p>
        ),
        orientacao: (
          <p>
            Remova os filtros de perfil (renda, escolaridade, cor/raca) e mantenha apenas
            recortes de localizacao ou escola, ou escolha outra edicao.
          </p>
        ),
      };

    case 'EDICAO_AUSENTE':
      return {
        titulo: 'Edicao nao disponivel na base',
        explicacao: (
          <p>
            Os dados {naEdicao(edicao)} nao estao carregados nesta instalacao, portanto
            nao ha o que consultar.
          </p>
        ),
        orientacao: <p>Escolha uma das edicoes listadas no formulario.</p>,
      };

    case CODIGO_ERRO_REDE:
      return {
        titulo: 'Nao conseguimos falar com a API',
        explicacao: (
          <p>
            A requisicao nao chegou ao servico de analise. Isso costuma ser conexao
            interrompida ou a API fora do ar — nao ha nada de errado com sua nota nem
            com o recorte escolhido.
          </p>
        ),
        orientacao: (
          <p>Confira sua conexao e envie o formulario novamente em alguns instantes.</p>
        ),
      };

    case CODIGO_TIMEOUT: {
      const segundos = segundosDeEspera(detalhes);
      return {
        titulo: 'A consulta demorou mais do que o esperado',
        explicacao: (
          <p>
            A API nao respondeu
            {segundos !== null ? ` em ${FORMATO_EDICAO.format(segundos)} segundos` : ' em tempo'}
            , entao a requisicao foi encerrada. O servico pode estar sobrecarregado neste
            momento.
          </p>
        ),
        orientacao: <p>Tente enviar novamente; se persistir, volte mais tarde.</p>,
      };
    }

    case CODIGO_RESPOSTA_INVALIDA:
      return {
        titulo: 'A API respondeu de forma inesperada',
        explicacao: (
          <p>
            A resposta chegou, mas nao no formato que este site sabe interpretar, entao
            preferimos nao exibir nenhum numero a exibir um numero duvidoso.
          </p>
        ),
        orientacao: <p>Tente novamente; se continuar, avise a equipe responsavel.</p>,
      };

    // Qualquer codigo fora do mapa (ex.: NOTA_FORA_INTERVALO, AREA_INVALIDA,
    // REQUISICAO_INVALIDA, MANIFESTO_*, CAPACIDADE_INDETERMINADA, ou um codigo
    // novo no backend): a mensagem do envelope e exibida como veio, para que
    // nada seja silenciosamente descartado.
    default:
      return {
        titulo: 'Nao foi possivel concluir a analise',
        explicacao: <p>{erro.mensagem}</p>,
        orientacao: <p>Ajuste os dados do formulario e tente novamente.</p>,
      };
  }
}

export default function EstadoErro({ erro }: EstadoErroProps) {
  const { titulo, explicacao, orientacao } = mensagemDe(erro);

  return (
    <section className="estado-erro" role="alert" aria-labelledby="estado-erro-titulo">
      <h2 id="estado-erro-titulo">{titulo}</h2>
      {explicacao}
      {orientacao}
      <p className="ajuda">Codigo do erro: {erro.codigo}</p>
    </section>
  );
}
