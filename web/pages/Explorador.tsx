/**
 * Explorador de dados — qualquer area quebrada por qualquer dimensao.
 *
 * A secao existe porque o Diagnostico responde uma pergunta fechada ("onde
 * estou?") e sobra uma classe inteira de perguntas abertas: como a nota varia
 * entre as UFs, entre faixas de renda, entre municipios. Cada uma delas exigiria
 * dezenas de analises individuais; `POST /v1/exploracao` responde em uma.
 *
 * Nao e um explorador de *linhas* — a API nao devolve registro de participante,
 * por desenho. O que se explora aqui sao agregados, com a mesma guarda de
 * privacidade por grupo que vale no resto do produto.
 *
 * As dimensoes oferecidas vem da capacidade da edicao, nunca de uma lista fixa:
 * pedir uma quebra que a edicao nao publica seria um 409 garantido, e a
 * interface prefere nao oferecer o caminho.
 *
 * `codigo_escola` fica de fora mesmo quando a edicao a publica. Agrupar por um
 * **identificador** nao e explorar: sao dezenas de milhares de grupos, e a lista
 * ordenada por tamanho que sairia dai e um ranking de escolas por construcao —
 * justamente o que esta interface nao faz. Consultar uma escola especifica
 * continua possivel, pelo codigo, no Perfil de escola.
 */

import { Database, SlidersHorizontal } from 'lucide-react';
import { useEffect, useId, useMemo, useState } from 'react';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import EstadoErro from '@/components/EstadoErro';
import GruposExploracao from '@/components/GruposExploracao';
import Linhagem from '@/components/Linhagem';
import { Campo, Entrada, Selecao } from '@/components/ui/Campo';
import Cartao from '@/components/ui/Cartao';
import { LinhaCarregando } from '@/components/ui/Carregando';
import Distintivo from '@/components/ui/Distintivo';
import { OPCOES_DIMENSAO } from '@/lib/dominios';
import { FORMATO_EDICAO, FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import { useEdicoes, useExploracao } from '@/lib/hooks';
import {
  ROTULOS_AREA,
  ROTULOS_DIMENSAO,
  type Area,
  type Dimensao,
  type Recorte,
} from '@/lib/tipos';

const TODAS_AREAS = Object.keys(ROTULOS_AREA) as Area[];
/**
 * Dimensoes oferecidas como quebra. `codigo_escola` e excluida por ser
 * identificador de instituicao e nao categoria: ver o cabecalho do modulo.
 */
const DIMENSOES_EXPLORAVEIS: readonly Dimensao[] = (
  Object.keys(ROTULOS_DIMENSAO) as Dimensao[]
).filter((dimensao) => dimensao !== 'codigo_escola');

/** Traduz o codigo cru de uma dimensao para o rotulo do dicionario do INEP. */
function rotuladorDe(dimensao: Dimensao): (valor: string) => string {
  const opcoes = OPCOES_DIMENSAO[dimensao];
  if (opcoes === undefined) return (valor) => valor;
  const mapa = new Map(opcoes.map((o) => [o.valor, o.rotulo]));
  return (valor) => mapa.get(valor) ?? valor;
}

export default function Explorador() {
  const base = useId();
  const { edicoes, carregando: carregandoEdicoes } = useEdicoes();
  const exploracao = useExploracao();

  const [edicao, setEdicao] = useState<number | null>(null);
  const [area, setArea] = useState<Area>('mt');
  const [dimensao, setDimensao] = useState<Dimensao>('uf_prova');
  const [filtroDim, setFiltroDim] = useState<Dimensao | ''>('');
  const [filtroValor, setFiltroValor] = useState('');

  useEffect(() => {
    if (edicao !== null || edicoes.length === 0) return;
    const comNotas = edicoes.find((info) => info.capacidade.possui_notas);
    setEdicao((comNotas ?? edicoes[0])?.edicao ?? null);
  }, [edicoes, edicao]);

  const info = useMemo(() => edicoes.find((e) => e.edicao === edicao) ?? null, [edicoes, edicao]);
  const suportadas = useMemo(
    () => DIMENSOES_EXPLORAVEIS.filter((d) => info?.capacidade.dimensoes_suportadas.includes(d)),
    [info],
  );

  // Uma dimensao escolhida pode deixar de existir ao trocar de edicao.
  useEffect(() => {
    if (suportadas.length > 0 && !suportadas.includes(dimensao)) {
      setDimensao(suportadas[0] as Dimensao);
    }
    if (filtroDim !== '' && !suportadas.includes(filtroDim)) {
      setFiltroDim('');
      setFiltroValor('');
    }
  }, [suportadas, dimensao, filtroDim]);

  const recorte: Recorte = useMemo(() => {
    if (filtroDim === '' || filtroValor.trim().length === 0) return { filtros: {} };
    return { filtros: { [filtroDim]: filtroValor.trim() } };
  }, [filtroDim, filtroValor]);

  useEffect(() => {
    if (edicao === null || !suportadas.includes(dimensao)) {
      exploracao.limpar();
      return;
    }
    exploracao.consultar({ edicao, area, dimensao, recorte });
    // `exploracao` troca de identidade a cada resposta; inclui-la aqui criaria
    // um laco consulta -> resposta -> consulta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edicao, area, dimensao, recorte, suportadas.length]);

  const rotular = useMemo(() => rotuladorDe(dimensao), [dimensao]);
  const opcoesFiltro = filtroDim === '' ? undefined : OPCOES_DIMENSAO[filtroDim];
  const resultado = exploracao.resultado;

  return (
    <>
      <CabecalhoPagina
        titulo="Explorador de dados"
        descricao="Escolha uma area e uma dimensao: a nota e quebrada entre todos os valores dela de uma vez. Os resultados sao agregados, como em todo o resto do produto."
      />

      <div className="space-y-6">
        <Cartao
          titulo="Consulta"
          descricao="As dimensoes oferecidas sao as que a edicao escolhida realmente publica."
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <Campo id={`${base}-edicao`} rotulo="Edicao">
              {(props) => (
                <Selecao
                  {...props}
                  value={edicao ?? ''}
                  disabled={carregandoEdicoes || edicoes.length === 0}
                  onChange={(e) => setEdicao(Number(e.target.value))}
                >
                  {edicoes.length === 0 && (
                    <option value="">{carregandoEdicoes ? 'Carregando...' : 'Nenhuma'}</option>
                  )}
                  {edicoes.map((e) => (
                    <option key={e.edicao} value={e.edicao}>
                      {e.capacidade.possui_notas
                        ? String(e.edicao)
                        : `${e.edicao} (sem notas publicadas)`}
                    </option>
                  ))}
                </Selecao>
              )}
            </Campo>

            <Campo id={`${base}-area`} rotulo="Area">
              {(props) => (
                <Selecao {...props} value={area} onChange={(e) => setArea(e.target.value as Area)}>
                  {TODAS_AREAS.map((v) => (
                    <option key={v} value={v}>
                      {ROTULOS_AREA[v]}
                    </option>
                  ))}
                </Selecao>
              )}
            </Campo>

            <Campo
              id={`${base}-dimensao`}
              rotulo="Quebrar por"
              ajuda={
                suportadas.length === 0
                  ? 'Esta edicao nao sustenta nenhuma quebra de nota.'
                  : undefined
              }
            >
              {(props) => (
                <Selecao
                  {...props}
                  value={dimensao}
                  disabled={suportadas.length === 0}
                  onChange={(e) => setDimensao(e.target.value as Dimensao)}
                >
                  {suportadas.length === 0 && <option value="">Indisponivel</option>}
                  {suportadas.map((d) => (
                    <option key={d} value={d}>
                      {ROTULOS_DIMENSAO[d]}
                    </option>
                  ))}
                </Selecao>
              )}
            </Campo>
          </div>

          <fieldset className="mt-5 border-t border-line pt-4">
            <legend className="sr-only">Filtro opcional</legend>
            <p className="mb-3 flex items-center gap-2 text-[13px] font-medium text-ink-80">
              <SlidersHorizontal size={14} aria-hidden="true" strokeWidth={1.75} />
              Restringir antes de quebrar (opcional)
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo id={`${base}-filtro-dim`} rotulo="Dimensao do filtro">
                {(props) => (
                  <Selecao
                    {...props}
                    value={filtroDim}
                    onChange={(e) => {
                      setFiltroDim(e.target.value as Dimensao | '');
                      setFiltroValor('');
                    }}
                  >
                    <option value="">Sem filtro</option>
                    {suportadas
                      .filter((d) => d !== dimensao)
                      .map((d) => (
                        <option key={d} value={d}>
                          {ROTULOS_DIMENSAO[d]}
                        </option>
                      ))}
                  </Selecao>
                )}
              </Campo>

              <Campo
                id={`${base}-filtro-valor`}
                rotulo="Valor"
                ajuda={
                  filtroDim !== '' && opcoesFiltro === undefined
                    ? 'Informe o valor exatamente como aparece na base.'
                    : undefined
                }
              >
                {(props) =>
                  opcoesFiltro !== undefined ? (
                    <Selecao
                      {...props}
                      value={filtroValor}
                      onChange={(e) => setFiltroValor(e.target.value)}
                    >
                      <option value="">Qualquer valor</option>
                      {opcoesFiltro.map((o) => (
                        <option key={o.valor} value={o.valor}>
                          {o.rotulo}
                        </option>
                      ))}
                    </Selecao>
                  ) : (
                    <Entrada
                      {...props}
                      value={filtroValor}
                      disabled={filtroDim === ''}
                      placeholder={filtroDim === '' ? 'Escolha uma dimensao' : ''}
                      onChange={(e) => setFiltroValor(e.target.value)}
                    />
                  )
                }
              </Campo>
            </div>
          </fieldset>
        </Cartao>

        <p role="status" aria-live="polite" className={exploracao.carregando ? '' : 'sr-only'}>
          {exploracao.carregando ? <LinhaCarregando>Agrupando os dados...</LinhaCarregando> : ''}
        </p>

        {exploracao.erro !== null && <EstadoErro erro={exploracao.erro} />}

        {resultado !== null && !exploracao.carregando && (
          <Cartao
            titulo={`${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[dimensao].toLowerCase()}`}
            descricao={`Edicao ${FORMATO_EDICAO.format(resultado.edicao)}, ${FORMATO_INTEIRO.format(
              resultado.grupos.length,
            )} ${resultado.grupos.length === 1 ? 'grupo' : 'grupos'}.`}
            acoes={
              resultado.grupos_truncados ? (
                <Distintivo tom="atencao">Lista truncada</Distintivo>
              ) : undefined
            }
          >
            {resultado.grupos_truncados && (
              <p className="prosa mb-4 border-l-2 border-[#e3b98c] bg-voce-fraco/40 px-4 py-2.5 text-xs leading-relaxed text-ink-80">
                Esta dimensao tem mais valores do que cabe em uma resposta. Os grupos
                aparecem do maior para o menor, entao o corte caiu nos menores — que a
                guarda de privacidade suprimiria de qualquer forma. Use o filtro acima
                para estreitar a consulta.
              </p>
            )}

            <GruposExploracao
              grupos={resultado.grupos}
              rotularValor={rotular}
              descricao={`Distribuicao das notas de ${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[
                dimensao
              ].toLowerCase()} na edicao ${resultado.edicao}. ${resultado.grupos
                .filter((g) => g.quantis !== null)
                .slice(0, 12)
                .map(
                  (g) =>
                    `${rotular(g.valor)}: mediana ${FORMATO_UMA_CASA.format(
                      g.quantis?.mediana ?? 0,
                    )}`,
                )
                .join('; ')}. Os mesmos numeros estao na tabela a seguir.`}
              legendaTabela={`Quantis de ${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[dimensao].toLowerCase()}, edicao ${resultado.edicao}`}
              vazio={
                <span className="inline-flex items-center gap-2">
                  <Database size={15} aria-hidden="true" strokeWidth={1.75} />
                  Nenhum grupo atende a este recorte nesta edicao.
                </span>
              }
            />
          </Cartao>
        )}

        {resultado !== null && <Linhagem linhagem={resultado.linhagem} />}
      </div>
    </>
  );
}
