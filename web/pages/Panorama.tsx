/**
 * Panorama ENEM — o que cada edicao efetivamente publica.
 *
 * Esta secao responde a pergunta que causa quase toda a frustracao com dados do
 * ENEM: "por que esse recorte funciona em um ano e nao no outro?". As edicoes
 * nao sao homogeneas — uma traz notas e perfil ligaveis por participante, outra
 * traz os dois em arquivos que nao podem ser cruzados, outra ainda nao publicou
 * notas. A matriz de capacidade torna isso consultavel em vez de descoberto por
 * tentativa e erro.
 *
 * Todos os numeros vem de `GET /v1/edicoes`, que ja traz a capacidade embutida:
 * uma requisicao, nenhuma derivacao local.
 */

import { CircleCheck, CircleMinus, RefreshCw, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import { Esqueleto } from '@/components/ui/Carregando';
import Botao from '@/components/ui/Botao';
import Cartao from '@/components/ui/Cartao';
import Distintivo from '@/components/ui/Distintivo';
import TabelaDados from '@/components/ui/TabelaDados';
import { ehErroApi, listarEdicoes, type ErroApi } from '@/lib/api';
import { FORMATO_DATA_HORA, FORMATO_EDICAO } from '@/lib/formato';
import { ROTULOS_DIMENSAO, type Dimensao, type InfoEdicao } from '@/lib/tipos';

const TODAS_DIMENSOES = Object.keys(ROTULOS_DIMENSAO) as Dimensao[];

/** Marca de suporte: icone e texto juntos, nunca cor sozinha. */
function Suporte({ suportada }: { suportada: boolean }) {
  return suportada ? (
    <span className="inline-flex items-center gap-1.5 text-coorte">
      <CircleCheck size={15} aria-hidden="true" strokeWidth={2} />
      <span className="text-xs text-ink-80">disponivel</span>
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-ink-40">
      <CircleMinus size={15} aria-hidden="true" strokeWidth={2} />
      <span className="text-xs text-ink-60">nao publicado</span>
    </span>
  );
}

function CartaoEdicao({ info }: { info: InfoEdicao }) {
  const { capacidade } = info;
  const dataCarga =
    info.data_carga !== null && !Number.isNaN(new Date(info.data_carga).getTime())
      ? FORMATO_DATA_HORA.format(new Date(info.data_carga))
      : null;

  return (
    <div className="rounded-[4px] border border-line bg-surface p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="numerico font-display text-[28px] leading-none text-ink">
          {FORMATO_EDICAO.format(info.edicao)}
        </p>
        {capacidade.possui_notas ? (
          <Distintivo tom="ativo" ponto>
            Notas publicadas
          </Distintivo>
        ) : (
          <Distintivo tom="recusa" ponto>
            Sem notas
          </Distintivo>
        )}
      </div>

      <dl className="mt-4 space-y-2 text-xs">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-60">Recortes disponiveis</dt>
          <dd className="numerico font-medium text-ink">
            {capacidade.dimensoes_suportadas.length} de {TODAS_DIMENSOES.length}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-60">Perfil cruzavel com nota</dt>
          <dd className="font-medium text-ink">
            {capacidade.perfil_combinavel_com_notas ? 'sim' : 'nao'}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-60">Carga</dt>
          <dd className="text-right text-ink-80">{dataCarga ?? 'nao informada'}</dd>
        </div>
      </dl>

      {!capacidade.perfil_combinavel_com_notas && (
        <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-ink-60">
          Perfil socioeconomico e notas foram publicados em arquivos que nao podem ser
          ligados pessoa por pessoa, entao recortes de renda, cor/raca e escolaridade
          ficam fora da analise de nota nesta edicao.
        </p>
      )}
    </div>
  );
}

export default function Panorama() {
  const [edicoes, setEdicoes] = useState<InfoEdicao[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [tentativa, setTentativa] = useState(0);

  const recarregar = useCallback(() => setTentativa((n) => n + 1), []);

  useEffect(() => {
    const controlador = new AbortController();
    let ativo = true;
    setCarregando(true);
    setErro(null);

    listarEdicoes({ signal: controlador.signal })
      .then((lista) => {
        if (ativo) setEdicoes([...lista].sort((a, b) => b.edicao - a.edicao));
      })
      .catch((causa: unknown) => {
        if (!ativo || controlador.signal.aborted) return;
        setEdicoes([]);
        setErro(ehErroApi(causa) ? causa : null);
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });

    return () => {
      ativo = false;
      controlador.abort();
    };
  }, [tentativa]);

  return (
    <>
      <CabecalhoPagina
        titulo="Panorama ENEM"
        descricao="Cada edicao do ENEM publica um conjunto diferente de variaveis. Esta e a matriz do que existe em cada uma — e, portanto, de quais comparacoes sao possiveis."
        acoes={
          <Botao
            variante="secundario"
            icone={<RefreshCw size={15} strokeWidth={1.75} />}
            onClick={recarregar}
            disabled={carregando}
          >
            Atualizar
          </Botao>
        }
      />

      {carregando && (
        <div className="space-y-6" role="status" aria-label="Carregando edicoes">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Esqueleto className="h-44" />
            <Esqueleto className="h-44" />
            <Esqueleto className="h-44" />
          </div>
          <Esqueleto className="h-64 w-full" />
        </div>
      )}

      {!carregando && erro !== null && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-[4px] border border-[#e0b9c6] bg-vinho-fraco/60 px-5 py-4"
        >
          <TriangleAlert
            size={18}
            aria-hidden="true"
            strokeWidth={1.75}
            className="mt-0.5 shrink-0 text-vinho"
          />
          <div>
            <h2 className="text-[16px] text-ink">Nao foi possivel listar as edicoes</h2>
            <p className="prosa mt-1 text-sm text-ink-80">{erro.mensagem}</p>
            <div className="mt-3">
              <Botao variante="secundario" onClick={recarregar}>
                Tentar novamente
              </Botao>
            </div>
          </div>
        </div>
      )}

      {!carregando && erro === null && edicoes.length === 0 && (
        <p className="rounded-[4px] border border-dashed border-line-forte bg-surface px-6 py-10 text-center text-sm text-ink-60">
          Nenhuma edicao esta carregada nesta instalacao.
        </p>
      )}

      {!carregando && edicoes.length > 0 && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {edicoes.map((info) => (
              <CartaoEdicao key={info.edicao} info={info} />
            ))}
          </div>

          <Cartao
            titulo="Recortes por edicao"
            descricao="Uma linha por dimensao de recorte; uma coluna por edicao carregada."
            semPadding
          >
            <TabelaDados
              legenda="Dimensoes de recorte disponiveis em cada edicao do ENEM"
              legendaOculta
              linhas={TODAS_DIMENSOES}
              chaveLinha={(dimensao) => dimensao}
              colunas={[
                {
                  chave: 'dimensao',
                  cabecalho: 'Recorte',
                  celula: (dimensao) => ROTULOS_DIMENSAO[dimensao],
                },
                ...edicoes.map((info) => ({
                  chave: String(info.edicao),
                  cabecalho: FORMATO_EDICAO.format(info.edicao),
                  celula: (dimensao: Dimensao) => (
                    <Suporte
                      suportada={info.capacidade.dimensoes_suportadas.includes(dimensao)}
                    />
                  ),
                })),
              ]}
            />
          </Cartao>
        </div>
      )}
    </>
  );
}
