/**
 * `VisualizacaoResultado` — o achado: percentil, distribuicao e os numeros que
 * o sustentam (Req 4.2 e 4.4).
 *
 * Decisoes:
 *
 * 1. **O percentil e o unico numero grande da tela.** Ele responde a pergunta
 *    que trouxe a pessoa ate aqui; quantis, contagens e faixas sao evidencia e
 *    ficam em corpo de texto e tabela. Espalhar varios numeros gigantes
 *    dissolveria a resposta em um painel de metricas.
 * 2. **O grafico nao carrega significado sozinho.** Ele e `role="img"` com
 *    resumo em prosa, e os mesmos numeros aparecem em duas tabelas reais, com
 *    `<caption>` e `<th scope>`. Nada e escondido com `display: none`.
 * 3. **Posicao derivada do percentil.** A API responde apenas agregados — ela
 *    devolve o percentil, nunca a nota informada de volta — entao o marcador e
 *    localizado invertendo a distribuicao cumulativa das faixas. E uma posicao
 *    aproximada, e os rotulos dizem isso.
 * 4. **Amostra insuficiente nao inventa numero.** Com a guarda de privacidade
 *    ativa nao ha grafico, tabela, percentil nem contagem: so a explicacao do
 *    porque (Req 4.4 / 9.3).
 */

import Histograma, { rotuloFaixa, type PosicaoUsuario } from '@/components/Histograma';
import TabelaDados from '@/components/ui/TabelaDados';
import { FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import {
  ROTULOS_AREA,
  type Distribuicao,
  type FaixaHistograma,
  type ResultadoAnalise,
} from '@/lib/tipos';

export interface VisualizacaoResultadoProps {
  resultado: ResultadoAnalise;
}

/**
 * Localiza o percentil no histograma invertendo a distribuicao cumulativa.
 *
 * Devolve `null` quando o histograma nao permite posicionar nada (sem faixas ou
 * com todas as contagens em zero) — preferivel a desenhar um marcador falso.
 */
export function estimarPosicao(
  faixas: FaixaHistograma[],
  percentil: number,
): PosicaoUsuario | null {
  const total = faixas.reduce((soma, faixa) => soma + faixa.contagem, 0);
  if (total <= 0) return null;

  const alvo = (Math.min(Math.max(percentil, 0), 100) / 100) * total;
  let acumulado = 0;

  for (let indice = 0; indice < faixas.length; indice += 1) {
    const faixa = faixas[indice];
    if (faixa === undefined || faixa.contagem <= 0) continue;

    const acumuladoApos = acumulado + faixa.contagem;
    const ultimaComContagem = acumuladoApos >= total;
    if (acumuladoApos >= alvo || ultimaComContagem) {
      const fracao = Math.min(Math.max((alvo - acumulado) / faixa.contagem, 0), 1);
      const largura = faixa.limite_superior - faixa.limite_inferior;
      return { indice, fracao, nota: faixa.limite_inferior + fracao * largura };
    }
    acumulado = acumuladoApos;
  }
  return null;
}

/** Tabela de quantis: uma linha por medida. */
function TabelaQuantis({
  distribuicao,
  rotuloArea,
  edicao,
}: {
  distribuicao: Distribuicao;
  rotuloArea: string;
  edicao: number;
}) {
  const { quantis } = distribuicao;
  const linhas = [
    { medida: 'Menor nota (minimo)', valor: quantis.minimo },
    { medida: 'Primeiro quartil (Q1)', valor: quantis.q1 },
    { medida: 'Mediana', valor: quantis.mediana },
    { medida: 'Terceiro quartil (Q3)', valor: quantis.q3 },
    { medida: 'Maior nota (maximo)', valor: quantis.maximo },
  ];

  return (
    <TabelaDados
      legenda={`Quantis das notas de ${rotuloArea} no grupo comparado, edicao ${edicao}`}
      colunas={[
        { chave: 'medida', cabecalho: 'Medida', celula: (linha) => linha.medida },
        {
          chave: 'valor',
          cabecalho: 'Nota',
          alinhamento: 'fim',
          largura: '40%',
          celula: (linha) => FORMATO_UMA_CASA.format(linha.valor),
        },
      ]}
      linhas={linhas}
      chaveLinha={(linha) => linha.medida}
    />
  );
}

/** Tabela do histograma: uma linha por faixa, com contagem e participacao. */
function TabelaFaixas({
  faixas,
  total,
  posicao,
  rotuloArea,
  edicao,
}: {
  faixas: FaixaHistograma[];
  total: number;
  posicao: PosicaoUsuario | null;
  rotuloArea: string;
  edicao: number;
}) {
  const linhas = faixas.map((faixa, indice) => ({ faixa, indice }));

  return (
    <TabelaDados
      legenda={`Distribuicao das notas de ${rotuloArea} por faixa no grupo comparado, edicao ${edicao}`}
      paginaTamanho={10}
      destacar={({ indice }) => posicao !== null && posicao.indice === indice}
      colunas={[
        {
          chave: 'faixa',
          cabecalho: 'Faixa de nota',
          celula: ({ faixa }) => rotuloFaixa(faixa),
        },
        {
          chave: 'pessoas',
          cabecalho: 'Pessoas',
          alinhamento: 'fim',
          celula: ({ faixa }) => FORMATO_INTEIRO.format(faixa.contagem),
        },
        {
          chave: 'participacao',
          cabecalho: 'Participacao',
          alinhamento: 'fim',
          celula: ({ faixa }) =>
            total > 0
              ? `${FORMATO_UMA_CASA.format((faixa.contagem / total) * 100)}%`
              : 'nao aplicavel',
        },
        {
          chave: 'posicao',
          cabecalho: 'Sua posicao',
          celula: ({ indice }) =>
            posicao !== null && posicao.indice === indice ? 'sua nota esta aqui' : '',
        },
      ]}
      linhas={linhas}
      chaveLinha={({ faixa }) => `${faixa.limite_inferior}-${faixa.limite_superior}`}
    />
  );
}

export default function VisualizacaoResultado({ resultado }: VisualizacaoResultadoProps) {
  const rotuloArea = ROTULOS_AREA[resultado.area];
  const { distribuicao, percentil } = resultado;

  // Amostra insuficiente ou detalhes anulados pela guarda de privacidade.
  if (resultado.estatisticamente_insuficiente || distribuicao === null || percentil === null) {
    return (
      <section
        aria-labelledby="resultado-titulo"
        className="rounded-[4px] border border-line bg-surface"
      >
        <h2 id="resultado-titulo" className="border-b border-line px-5 py-4 text-[17px]">
          Sua posicao
        </h2>
        <p
          role="status"
          className="prosa border-l-2 border-vinho bg-vinho-fraco/50 px-5 py-4 text-sm leading-relaxed text-ink-80"
        >
          O grupo formado por este recorte e pequeno demais para divulgar a
          distribuicao com seguranca, portanto nao exibimos percentil, quantis nem
          contagens — e assim que a desidentificacao dos microdados e respeitada.
          Escolha um recorte mais amplo (menos filtros) para ver sua posicao em{' '}
          {rotuloArea} na edicao {resultado.edicao}.
        </p>
      </section>
    );
  }

  const { faixas } = distribuicao;
  const total = faixas.reduce((soma, faixa) => soma + faixa.contagem, 0);
  const posicao = estimarPosicao(faixas, percentil);
  const percentilFormatado = FORMATO_UMA_CASA.format(percentil);

  const faixaDaPosicao = posicao !== null ? faixas[posicao.indice] : undefined;
  const descricaoGrafico =
    `Histograma das notas de ${rotuloArea} na edicao ${resultado.edicao}, com ` +
    `${FORMATO_INTEIRO.format(faixas.length)} faixas de nota. Mediana do grupo: ` +
    `${FORMATO_UMA_CASA.format(distribuicao.quantis.mediana)}. Sua nota fica acima de ` +
    `${percentilFormatado}% do grupo` +
    (faixaDaPosicao !== undefined
      ? `, por volta da faixa ${rotuloFaixa(faixaDaPosicao)}.`
      : '.') +
    ' Os mesmos numeros estao nas tabelas a seguir.';

  return (
    <section aria-labelledby="resultado-titulo" className="space-y-6">
      <h2 id="resultado-titulo" className="sr-only">
        Sua posicao
      </h2>

      {/* O achado. Sem cartao em volta: o numero e o grafico sao a pagina. */}
      <div>
        {/* Uma unica corrida de texto, sem `<span>` no meio: o percentil ja
            aparece grande e em ocre na faixa de indicadores logo acima, e
            realca-lo duas vezes gastaria o acento do produto em dobro. Manter a
            frase inteira tambem a preserva como equivalente textual continuo da
            distribuicao (Req 4.4). */}
        <p className="numerico font-display text-[clamp(1.35rem,3.2vw,1.95rem)] leading-[1.2] text-ink">
          Sua nota de {rotuloArea} esta acima de {percentilFormatado}% das notas do
          grupo comparado na edicao {resultado.edicao}.
        </p>

        <p className="prosa mt-3 text-[15px] leading-relaxed text-ink-80">
          {resultado.tamanho_amostral !== null
            ? `O grupo comparado tem ${FORMATO_INTEIRO.format(
                resultado.tamanho_amostral,
              )} pessoas com nota valida em ${rotuloArea}. `
            : ''}
          Metade do grupo ficou abaixo de{' '}
          {FORMATO_UMA_CASA.format(distribuicao.quantis.mediana)} pontos, e o intervalo
          central (do primeiro ao terceiro quartil) vai de{' '}
          {FORMATO_UMA_CASA.format(distribuicao.quantis.q1)} a{' '}
          {FORMATO_UMA_CASA.format(distribuicao.quantis.q3)} pontos.
        </p>
      </div>

      {faixas.length > 0 && total > 0 ? (
        <div>
          <Histograma faixas={faixas} posicao={posicao} descricao={descricaoGrafico} />
          <p className="prosa mt-2 text-xs text-ink-60">
            Cada barra e uma faixa de nota; a altura e quantas pessoas do grupo caem
            nela. A linha vertical marca, de forma aproximada, onde sua nota entra
            (percentil {percentilFormatado}).
          </p>
        </div>
      ) : (
        <p className="prosa text-sm text-ink-60">
          O histograma nao esta disponivel para este recorte; os quantis abaixo
          descrevem a distribuicao.
        </p>
      )}

      {/* `items-start`: sem isto o cartao de quantis esticaria ate a altura da
          tabela de faixas, deixando um vazio grande sob cinco linhas. */}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <div className="overflow-hidden rounded-[4px] border border-line bg-surface pt-4">
          <TabelaQuantis
            distribuicao={distribuicao}
            rotuloArea={rotuloArea}
            edicao={resultado.edicao}
          />
        </div>

        {faixas.length > 0 && (
          <details
            open
            className="group overflow-hidden rounded-[4px] border border-line bg-surface"
          >
            <summary className="cursor-pointer list-none px-5 py-4 text-[13px] font-medium text-ink transition-colors hover:bg-paper">
              Numeros de cada faixa do grafico
            </summary>
            <TabelaFaixas
              faixas={faixas}
              total={total}
              posicao={posicao}
              rotuloArea={rotuloArea}
              edicao={resultado.edicao}
            />
          </details>
        )}
      </div>
    </section>
  );
}
