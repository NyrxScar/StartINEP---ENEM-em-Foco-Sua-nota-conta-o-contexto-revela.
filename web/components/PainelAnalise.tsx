/**
 * `PainelAnalise` — Client Component que detem o estado compartilhado da
 * analise e conecta o formulario (12.2), a visualizacao (12.3) e os estados de
 * UI/linhagem (12.4).
 *
 * Existe para que a pagina permaneca sem estado: o painel e o unico dono de
 * `resultado`, `erro` e `carregando`.
 *
 * Decisoes de projeto da 12.4:
 *
 * 1. **Um estado nomeado, mutuamente exclusivo.** Os tres sinais brutos
 *    (`carregando`/`erro`/`resultado`) sao reduzidos por {@link estadoDe} a uma
 *    uniao discriminada: `ocioso`, `carregando`, `erro`, `amostra-insuficiente`
 *    ou `resultado`. Assim carregamento, erro e resultado nunca aparecem juntos
 *    na tela (Req 4.5), e a amostra insuficiente (Req 4.4) deixa de ser um
 *    detalhe interno da visualizacao para virar um estado de primeira classe —
 *    inclusive no DOM, via `data-estado`, o que da um ponto de observacao
 *    estavel para os testes da 12.5.
 * 2. **Uma unica voz para cada anuncio.** A regiao `role="status"` existe sempre
 *    no DOM (um `aria-live` inserido junto com o texto costuma nao ser
 *    anunciado) e carrega **apenas** o carregamento. Erros sao anunciados pelo
 *    `role="alert"` de `EstadoErro`, e a amostra insuficiente pelo
 *    `role="status"` que `VisualizacaoResultado` ja renderiza — a mensagem de
 *    supressao continua morando la, para nao dizer a mesma coisa duas vezes.
 * 3. **Linhagem acompanha todo resultado exibido** (Req 5.3), inclusive o
 *    suprimido: saber de qual edicao e de qual carga vem a supressao e parte da
 *    auditabilidade.
 * 4. **A faixa de indicadores so aparece com resultado.** Mostrar os rotulos com
 *    tracos antes da primeira consulta encheria a tela de numeros vazios; ate
 *    la o lugar e ocupado por uma explicacao do que a consulta vai devolver.
 */

import { ChartNoAxesColumn } from 'lucide-react';
import { useState } from 'react';

import EstadoErro from '@/components/EstadoErro';
import FormularioAnalise from '@/components/FormularioAnalise';
import IndicadoresChave from '@/components/IndicadoresChave';
import Linhagem from '@/components/Linhagem';
import VisualizacaoResultado from '@/components/VisualizacaoResultado';
import { Esqueleto, LinhaCarregando } from '@/components/ui/Carregando';
import type { ErroApi } from '@/lib/api';
import type { ResultadoAnalise } from '@/lib/tipos';

/** Estados possiveis do painel, mutuamente exclusivos. */
export type EstadoPainel =
  | { tipo: 'ocioso' }
  | { tipo: 'carregando' }
  | { tipo: 'erro'; erro: ErroApi }
  | { tipo: 'amostra-insuficiente'; resultado: ResultadoAnalise }
  | { tipo: 'resultado'; resultado: ResultadoAnalise };

/**
 * Reduz os sinais brutos ao estado exibido. A precedencia importa: uma
 * requisicao em voo substitui o desfecho anterior (nada de resultado velho ao
 * lado do indicador de carregamento).
 */
export function estadoDe(
  carregando: boolean,
  erro: ErroApi | null,
  resultado: ResultadoAnalise | null,
): EstadoPainel {
  if (carregando) return { tipo: 'carregando' };
  if (erro !== null) return { tipo: 'erro', erro };
  if (resultado === null) return { tipo: 'ocioso' };
  // A guarda de privacidade pode marcar a insuficiencia e/ou anular os detalhes;
  // qualquer um dos casos e o mesmo estado para quem le (Req 4.4 / 9.3).
  if (
    resultado.estatisticamente_insuficiente ||
    resultado.distribuicao === null ||
    resultado.percentil === null
  ) {
    return { tipo: 'amostra-insuficiente', resultado };
  }
  return { tipo: 'resultado', resultado };
}

export default function PainelAnalise() {
  const [resultado, setResultado] = useState<ResultadoAnalise | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [carregando, setCarregando] = useState(false);

  const estado = estadoDe(carregando, erro, resultado);
  const exibindoResultado =
    estado.tipo === 'resultado' || estado.tipo === 'amostra-insuficiente';

  return (
    <div data-estado={estado.tipo} className="space-y-6">
      <FormularioAnalise
        onResultado={(novo) => {
          setErro(null);
          setResultado(novo);
        }}
        onErro={(falha) => {
          setResultado(null);
          setErro(falha);
        }}
        onCarregando={(emAndamento) => {
          setCarregando(emAndamento);
          if (emAndamento) setErro(null);
        }}
      />

      {/* A regiao vive sempre no DOM para que o leitor de tela anuncie a
          mudanca de texto; um `aria-live` inserido junto com o conteudo
          costuma nao ser anunciado. */}
      {/* `sr-only` quando ocioso, em vez de altura reservada: a regiao continua
          no DOM sem interrupcao (condicao para o anuncio funcionar), porem sai
          do fluxo e nao deixa um vao entre o formulario e o resultado. */}
      <p
        role="status"
        aria-live="polite"
        className={estado.tipo === 'carregando' ? '' : 'sr-only'}
      >
        {estado.tipo === 'carregando' ? (
          <LinhaCarregando>Consultando a distribuicao...</LinhaCarregando>
        ) : (
          ''
        )}
      </p>

      {estado.tipo === 'carregando' && (
        <div aria-hidden="true" className="space-y-6">
          <Esqueleto className="h-24 w-full" />
          <Esqueleto className="h-10 w-3/4 max-w-xl" />
          <Esqueleto className="h-56 w-full" />
        </div>
      )}

      {estado.tipo === 'ocioso' && (
        <div className="rounded-[4px] border border-dashed border-line-forte bg-surface px-6 py-10 text-center">
          <ChartNoAxesColumn
            size={22}
            aria-hidden="true"
            strokeWidth={1.75}
            className="mx-auto text-ink-40"
          />
          <p className="prosa mx-auto mt-3 text-sm leading-relaxed text-ink-60">
            Preencha sua nota acima para ver a distribuicao do grupo escolhido, seu
            percentil dentro dele e os quantis que sustentam o numero.
          </p>
        </div>
      )}

      {/* Erro ramificado por `codigo`: recorte indisponivel com as edicoes que o
          suportam, limitacoes da edicao, API inacessivel (Req 4.3). */}
      {estado.tipo === 'erro' && <EstadoErro erro={estado.erro} />}

      {exibindoResultado && (
        <>
          <IndicadoresChave resultado={estado.resultado} />
          <VisualizacaoResultado resultado={estado.resultado} />
          <Linhagem linhagem={estado.resultado.linhagem} />
        </>
      )}
    </div>
  );
}
