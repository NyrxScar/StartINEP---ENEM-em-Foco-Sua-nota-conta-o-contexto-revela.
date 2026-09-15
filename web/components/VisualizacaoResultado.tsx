/**
 * `VisualizacaoResultado` — grafico da Distribuicao com a posicao do usuario e
 * o **equivalente textual acessivel** (task 12.3; Req 4.2 e 4.4).
 *
 * Decisoes de projeto:
 *
 * 1. **Grafico em SVG inline, sem biblioteca.** O histograma vem pronto da API
 *    (`distribuicao.faixas`, faixas de largura uniforme com `contagem`), logo o
 *    trabalho restante e so escalar retangulos. Uma dependencia de charting
 *    (recharts/chart.js/d3) adicionaria centenas de KB ao bundle, obrigaria a
 *    tornar a arvore inteira client-side e ainda exigiria o mesmo esforco de
 *    acessibilidade — o SVG e desenhado a mao e o componente permanece um
 *    Server Component (nao ha `'use client'` aqui: nenhum estado, nenhum efeito).
 * 2. **O grafico nunca e o unico portador de significado** (Req 4.4). O SVG e
 *    `role="img"` com `<title>` + `aria-label` resumindo o achado, e todo o seu
 *    interior e `aria-hidden` (barras, eixo e rotulos sao decorativos). O
 *    conteudo real vive fora dele: um paragrafo em prosa com o percentil e o
 *    tamanho amostral, uma tabela de quantis e uma tabela de faixas — todas
 *    renderizadas de verdade, com `<caption>` e `<th scope>`. Nada e escondido
 *    com `display: none`; a tabela de faixas fica em um `<details open>`, ou
 *    seja, expandida (e exposta a tecnologia assistiva) por padrao, e recolher
 *    e uma escolha da pessoa.
 * 3. **Posicao do usuario derivada do percentil.** O `ResultadoAnalise` carrega
 *    o percentil, nao a nota informada (a API responde apenas agregados), por
 *    isso o marcador e localizado invertendo a distribuicao cumulativa das
 *    faixas: e uma posicao *aproximada*, e os rotulos dizem isso.
 * 4. **Amostra insuficiente = nenhum numero inventado** (Req 4.4 / 9.3). Quando
 *    `estatisticamente_insuficiente` e verdadeiro — ou quando a guarda de
 *    privacidade anulou `distribuicao`/`percentil` — nao ha grafico, nao ha
 *    tabela e nenhuma contagem e exposta, apenas a explicacao. O polimento
 *    completo dos estados de UI e da task 12.4.
 * 5. **Formatacao pt-BR explicita** (`Intl.NumberFormat('pt-BR', ...)`), com
 *    numero de casas decimais fixo, para nao depender do locale do ambiente.
 */

import {
  ROTULOS_AREA,
  type Distribuicao,
  type FaixaHistograma,
  type ResultadoAnalise,
} from '@/lib/tipos';

/** Contagens e tamanho amostral: inteiros com separador de milhar pt-BR. */
const FORMATO_INTEIRO = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

/** Notas e percentil: uma casa decimal, sempre presente (determinismo). */
const FORMATO_UMA_CASA = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Participacao de uma faixa no grupo, em pontos percentuais. */
const FORMATO_PARTICIPACAO = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Geometria do SVG (unidades de `viewBox`; o tamanho real e fluido via CSS). */
const LARGURA = 640;
const ALTURA = 260;
const MARGEM = { topo: 16, direita: 16, base: 44, esquerda: 16 } as const;
const LARGURA_PLOT = LARGURA - MARGEM.esquerda - MARGEM.direita;
const ALTURA_PLOT = ALTURA - MARGEM.topo - MARGEM.base;

export interface VisualizacaoResultadoProps {
  resultado: ResultadoAnalise;
}

/** Posicao aproximada do usuario, em coordenadas de faixa. */
interface PosicaoUsuario {
  /** Indice da faixa que contem a posicao. */
  indice: number;
  /** Fracao (0..1) percorrida dentro dessa faixa. */
  fracao: number;
  /** Nota estimada correspondente, interpolada dentro da faixa. */
  nota: number;
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

/** Ancora do rotulo do marcador, para nao vazar das bordas do SVG. */
function ancora(x: number): 'start' | 'middle' | 'end' {
  if (x < MARGEM.esquerda + LARGURA_PLOT * 0.15) return 'start';
  if (x > MARGEM.esquerda + LARGURA_PLOT * 0.85) return 'end';
  return 'middle';
}

/** Rotulo textual de uma faixa ("500,0 a 550,0"). */
function rotuloFaixa(faixa: FaixaHistograma): string {
  return `${FORMATO_UMA_CASA.format(faixa.limite_inferior)} a ${FORMATO_UMA_CASA.format(
    faixa.limite_superior,
  )}`;
}

/**
 * Histograma em SVG. `role="img"` + `aria-label` entregam o resumo; o interior e
 * `aria-hidden` porque o conteudo equivalente esta nas tabelas ao lado.
 */
function Histograma({
  faixas,
  posicao,
  descricao,
}: {
  faixas: FaixaHistograma[];
  posicao: PosicaoUsuario | null;
  descricao: string;
}) {
  const maiorContagem = faixas.reduce((maior, faixa) => Math.max(maior, faixa.contagem), 0);
  const larguraBarra = LARGURA_PLOT / faixas.length;
  const base = MARGEM.topo + ALTURA_PLOT;
  const primeira = faixas[0];
  const ultima = faixas[faixas.length - 1];

  const xMarcador =
    posicao === null
      ? null
      : MARGEM.esquerda + (posicao.indice + posicao.fracao) * larguraBarra;

  return (
    <svg
      className="grafico"
      viewBox={`0 0 ${LARGURA} ${ALTURA}`}
      role="img"
      aria-label={descricao}
    >
      <title>{descricao}</title>
      <g aria-hidden="true">
        {faixas.map((faixa, indice) => {
          const altura =
            maiorContagem > 0 ? (faixa.contagem / maiorContagem) * ALTURA_PLOT : 0;
          const destacada = posicao !== null && posicao.indice === indice;
          return (
            <rect
              key={`${faixa.limite_inferior}-${faixa.limite_superior}`}
              className={destacada ? 'grafico-barra grafico-barra--posicao' : 'grafico-barra'}
              x={MARGEM.esquerda + indice * larguraBarra + larguraBarra * 0.1}
              y={base - altura}
              width={Math.max(larguraBarra * 0.8, 1)}
              height={Math.max(altura, faixa.contagem > 0 ? 1 : 0)}
            />
          );
        })}

        <line
          className="grafico-eixo"
          x1={MARGEM.esquerda}
          y1={base}
          x2={MARGEM.esquerda + LARGURA_PLOT}
          y2={base}
        />

        {xMarcador !== null && (
          <>
            <line
              className="grafico-marcador"
              x1={xMarcador}
              y1={MARGEM.topo}
              x2={xMarcador}
              y2={base}
            />
            <text
              className="grafico-rotulo grafico-rotulo--marcador"
              x={xMarcador}
              y={MARGEM.topo + 12}
              textAnchor={ancora(xMarcador)}
            >
              sua posicao
            </text>
          </>
        )}

        {primeira !== undefined && (
          <text
            className="grafico-rotulo"
            x={MARGEM.esquerda}
            y={base + 20}
            textAnchor="start"
          >
            {FORMATO_UMA_CASA.format(primeira.limite_inferior)}
          </text>
        )}
        {ultima !== undefined && (
          <text
            className="grafico-rotulo"
            x={MARGEM.esquerda + LARGURA_PLOT}
            y={base + 20}
            textAnchor="end"
          >
            {FORMATO_UMA_CASA.format(ultima.limite_superior)}
          </text>
        )}
        <text
          className="grafico-rotulo"
          x={MARGEM.esquerda + LARGURA_PLOT / 2}
          y={base + 36}
          textAnchor="middle"
        >
          nota
        </text>
      </g>
    </svg>
  );
}

/** Tabela de quantis: uma linha por medida, cabecalhos de linha e de coluna. */
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
  const linhas: Array<{ medida: string; valor: number }> = [
    { medida: 'Menor nota (minimo)', valor: quantis.minimo },
    { medida: 'Primeiro quartil (Q1)', valor: quantis.q1 },
    { medida: 'Mediana', valor: quantis.mediana },
    { medida: 'Terceiro quartil (Q3)', valor: quantis.q3 },
    { medida: 'Maior nota (maximo)', valor: quantis.maximo },
  ];

  return (
    <table className="tabela-dados">
      <caption>
        Quantis das notas de {rotuloArea} no grupo comparado, edicao {edicao}
      </caption>
      <thead>
        <tr>
          <th scope="col">Medida</th>
          <th scope="col">Nota</th>
        </tr>
      </thead>
      <tbody>
        {linhas.map((linha) => (
          <tr key={linha.medida}>
            <th scope="row">{linha.medida}</th>
            <td>{FORMATO_UMA_CASA.format(linha.valor)}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
  return (
    <table className="tabela-dados">
      <caption>
        Distribuicao das notas de {rotuloArea} por faixa no grupo comparado, edicao{' '}
        {edicao}
      </caption>
      <thead>
        <tr>
          <th scope="col">Faixa de nota</th>
          <th scope="col">Pessoas</th>
          <th scope="col">Participacao</th>
          <th scope="col">Sua posicao</th>
        </tr>
      </thead>
      <tbody>
        {faixas.map((faixa, indice) => (
          <tr key={`${faixa.limite_inferior}-${faixa.limite_superior}`}>
            <th scope="row">{rotuloFaixa(faixa)}</th>
            <td>{FORMATO_INTEIRO.format(faixa.contagem)}</td>
            <td>
              {total > 0
                ? `${FORMATO_PARTICIPACAO.format((faixa.contagem / total) * 100)}%`
                : 'nao aplicavel'}
            </td>
            <td>{posicao !== null && posicao.indice === indice ? 'sua nota esta aqui' : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function VisualizacaoResultado({ resultado }: VisualizacaoResultadoProps) {
  const rotuloArea = ROTULOS_AREA[resultado.area];
  const { distribuicao, percentil } = resultado;

  // Amostra insuficiente ou detalhes anulados pela guarda de privacidade: nenhum
  // grafico, nenhuma contagem, nenhum numero inventado (Req 4.4 / 9.3).
  if (resultado.estatisticamente_insuficiente || distribuicao === null || percentil === null) {
    return (
      <section className="painel visualizacao" aria-labelledby="resultado-titulo">
        <h2 id="resultado-titulo">Sua posicao</h2>
        <p className="aviso" role="status">
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
    <section className="painel visualizacao" aria-labelledby="resultado-titulo">
      <h2 id="resultado-titulo">Sua posicao</h2>

      <p className="destaque">
        Sua nota de {rotuloArea} esta acima de {percentilFormatado}% das notas do grupo
        comparado na edicao {resultado.edicao}.
      </p>

      <p>
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

      {faixas.length > 0 && total > 0 ? (
        <>
          <Histograma faixas={faixas} posicao={posicao} descricao={descricaoGrafico} />
          <p className="ajuda">
            Cada barra e uma faixa de nota; a altura e quantas pessoas do grupo caem
            nela. A linha vertical marca, de forma aproximada, onde sua nota entra
            (percentil {percentilFormatado}).
          </p>
        </>
      ) : (
        <p className="ajuda">
          O histograma nao esta disponivel para este recorte; os quantis abaixo
          descrevem a distribuicao.
        </p>
      )}

      <TabelaQuantis
        distribuicao={distribuicao}
        rotuloArea={rotuloArea}
        edicao={resultado.edicao}
      />

      {faixas.length > 0 && (
        <details className="detalhes-dados" open>
          <summary>Numeros de cada faixa do grafico</summary>
          <TabelaFaixas
            faixas={faixas}
            total={total}
            posicao={posicao}
            rotuloArea={rotuloArea}
            edicao={resultado.edicao}
          />
        </details>
      )}
    </section>
  );
}
