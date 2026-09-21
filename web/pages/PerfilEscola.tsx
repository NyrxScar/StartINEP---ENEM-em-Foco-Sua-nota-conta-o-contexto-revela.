/**
 * Perfil de escola — a nota por tipo de rede, dependencia e localizacao.
 *
 * O que esta secao **nao** e, e por que:
 *
 * Nao e um ranking de escolas. Os microdados do ENEM publicam o codigo INEP da
 * instituicao apenas na edicao 2024, e nunca o nome dela. Mesmo em 2024, cerca
 * de metade das escolas fica abaixo do limiar de divulgacao e some da resposta.
 * Uma lista ordenada por nota, alem de incompleta, premiaria escola que
 * seleciona aluno na entrada — exatamente o efeito que levou o INEP a parar de
 * publicar medias por escola.
 *
 * O que ela e: a distribuicao da nota entre *categorias* de escola, que toda
 * edicao com vinculo escolar sustenta, mais uma consulta pontual por codigo
 * INEP para quem ja sabe qual escola procura.
 *
 * Um aviso permanece na tela: estes recortes cobrem apenas quem declara vinculo
 * escolar — entre um quinto e um terco dos participantes, conforme a edicao. Ler
 * "escola publica tem mediana X" como retrato da rede publica inteira seria
 * errado, e a tela diz isso.
 */

import { School, Search, TriangleAlert } from 'lucide-react';
import { useEffect, useId, useMemo, useState } from 'react';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import EstadoErro from '@/components/EstadoErro';
import GruposExploracao from '@/components/GruposExploracao';
import Linhagem from '@/components/Linhagem';
import Botao from '@/components/ui/Botao';
import { Campo, Entrada, Selecao } from '@/components/ui/Campo';
import Cartao from '@/components/ui/Cartao';
import { LinhaCarregando } from '@/components/ui/Carregando';
import Distintivo from '@/components/ui/Distintivo';
import { OPCOES_DIMENSAO } from '@/lib/dominios';
import { FORMATO_EDICAO, FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import { useEdicoes, useExploracao } from '@/lib/hooks';
import { ROTULOS_AREA, ROTULOS_DIMENSAO, type Area, type Dimensao } from '@/lib/tipos';

const TODAS_AREAS = Object.keys(ROTULOS_AREA) as Area[];

/** Dimensoes que caracterizam a escola sem identifica-la. */
const DIMENSOES_PERFIL_ESCOLA: readonly Dimensao[] = [
  'tipo_escola',
  'dependencia_adm_escola',
  'localizacao_escola',
];

/** Traduz o codigo cru de uma dimensao para o rotulo do dicionario do INEP. */
function rotuladorDe(dimensao: Dimensao): (valor: string) => string {
  const opcoes = OPCOES_DIMENSAO[dimensao];
  if (opcoes === undefined) return (valor) => valor;
  const mapa = new Map(opcoes.map((o) => [o.valor, o.rotulo]));
  return (valor) => mapa.get(valor) ?? valor;
}

export default function PerfilEscola() {
  const base = useId();
  const { edicoes, carregando: carregandoEdicoes } = useEdicoes();
  const perfil = useExploracao();
  const escola = useExploracao();

  const [edicao, setEdicao] = useState<number | null>(null);
  const [area, setArea] = useState<Area>('mt');
  const [dimensao, setDimensao] = useState<Dimensao>('dependencia_adm_escola');
  const [codigo, setCodigo] = useState('');

  // Primeira edicao com notas assim que a lista chega.
  useEffect(() => {
    if (edicao !== null || edicoes.length === 0) return;
    const comNotas = edicoes.find((info) => info.capacidade.possui_notas);
    setEdicao((comNotas ?? edicoes[0])?.edicao ?? null);
  }, [edicoes, edicao]);

  const info = useMemo(
    () => edicoes.find((e) => e.edicao === edicao) ?? null,
    [edicoes, edicao],
  );
  const suportadas = info?.capacidade.dimensoes_suportadas ?? [];
  const disponiveis = DIMENSOES_PERFIL_ESCOLA.filter((d) => suportadas.includes(d));
  const temCodigoEscola = suportadas.includes('codigo_escola');

  // Se a edicao escolhida nao sustenta a dimensao atual, cai para a primeira
  // que ela sustenta — em vez de deixar a tela pedir algo impossivel.
  useEffect(() => {
    if (disponiveis.length > 0 && !disponiveis.includes(dimensao)) {
      setDimensao(disponiveis[0] as Dimensao);
    }
  }, [disponiveis, dimensao]);

  // Consulta o perfil sempre que os parametros mudam.
  useEffect(() => {
    if (edicao === null || !disponiveis.includes(dimensao)) {
      perfil.limpar();
      return;
    }
    perfil.consultar({ edicao, area, dimensao });
    // `perfil` muda de identidade a cada resposta; incluir na lista criaria um
    // laco infinito de consulta -> resposta -> consulta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edicao, area, dimensao, disponiveis.length]);

  const rotular = useMemo(() => rotuladorDe(dimensao), [dimensao]);
  const edicaoComCodigo = edicoes.find((e) =>
    e.capacidade.dimensoes_suportadas.includes('codigo_escola'),
  );

  function consultarEscola(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const limpo = codigo.trim();
    if (edicao === null || limpo.length === 0) return;
    escola.consultar({
      edicao,
      area,
      dimensao: 'codigo_escola',
      recorte: { filtros: { codigo_escola: limpo } },
    });
  }

  const grupoEscola = escola.resultado?.grupos[0] ?? null;

  return (
    <>
      <CabecalhoPagina
        titulo="Perfil de escola"
        descricao="Como a nota se distribui entre os tipos de escola, redes e localizacoes. Nao ha ranking de instituicoes aqui, e a razao esta explicada abaixo."
      />

      <div className="space-y-6">
        {/* O aviso de cobertura vem antes de qualquer numero, de proposito. */}
        <div className="flex items-start gap-3 rounded-[4px] border border-line bg-paper px-5 py-4">
          <TriangleAlert
            size={17}
            aria-hidden="true"
            strokeWidth={1.75}
            className="mt-0.5 shrink-0 text-ink-40"
          />
          <p className="prosa text-sm leading-relaxed text-ink-80">
            Estes recortes so existem para quem declara vinculo escolar, o que cobre
            entre um quinto e um terco dos participantes conforme a edicao. As
            distribuicoes abaixo descrevem esse subconjunto — nao a rede de ensino
            inteira, nem todos os inscritos.
          </p>
        </div>

        <Cartao titulo="Parametros" descricao="A distribuicao e recalculada a cada mudanca.">
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
                disponiveis.length === 0
                  ? 'Esta edicao nao publica atributos de escola.'
                  : undefined
              }
            >
              {(props) => (
                <Selecao
                  {...props}
                  value={dimensao}
                  disabled={disponiveis.length === 0}
                  onChange={(e) => setDimensao(e.target.value as Dimensao)}
                >
                  {disponiveis.length === 0 && <option value="">Indisponivel</option>}
                  {disponiveis.map((d) => (
                    <option key={d} value={d}>
                      {ROTULOS_DIMENSAO[d]}
                    </option>
                  ))}
                </Selecao>
              )}
            </Campo>
          </div>
        </Cartao>

        <p role="status" aria-live="polite" className={perfil.carregando ? '' : 'sr-only'}>
          {perfil.carregando ? <LinhaCarregando>Calculando a distribuicao...</LinhaCarregando> : ''}
        </p>

        {perfil.erro !== null && <EstadoErro erro={perfil.erro} />}

        {perfil.resultado !== null && !perfil.carregando && (
          <Cartao
            titulo={`${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[dimensao].toLowerCase()}`}
            descricao={`Edicao ${FORMATO_EDICAO.format(perfil.resultado.edicao)}.`}
          >
            <GruposExploracao
              grupos={perfil.resultado.grupos}
              rotularValor={rotular}
              descricao={`Distribuicao das notas de ${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[
                dimensao
              ].toLowerCase()} na edicao ${perfil.resultado.edicao}. ${perfil.resultado.grupos
                .filter((g) => g.quantis !== null)
                .map(
                  (g) =>
                    `${rotular(g.valor)}: mediana ${FORMATO_UMA_CASA.format(
                      g.quantis?.mediana ?? 0,
                    )}`,
                )
                .join('; ')}. Os mesmos numeros estao na tabela a seguir.`}
              legendaTabela={`Quantis de ${ROTULOS_AREA[area]} por ${ROTULOS_DIMENSAO[dimensao].toLowerCase()}, edicao ${perfil.resultado.edicao}`}
            />
          </Cartao>
        )}

        {/* Consulta por instituicao: so a edicao com CO_ESCOLA a sustenta. */}
        <Cartao
          titulo="Consultar uma escola pelo codigo INEP"
          descricao="Uma escola por vez, pelo codigo. Os microdados nao publicam o nome da instituicao, apenas o codigo."
          acoes={
            temCodigoEscola ? (
              <Distintivo tom="ativo" ponto>
                Disponivel nesta edicao
              </Distintivo>
            ) : (
              <Distintivo tom="recusa" ponto>
                Indisponivel nesta edicao
              </Distintivo>
            )
          }
        >
          {temCodigoEscola ? (
            <form onSubmit={consultarEscola} className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-56 flex-1">
                  <Campo
                    id={`${base}-codigo`}
                    rotulo="Codigo INEP da escola"
                    ajuda="Oito digitos, como aparece no Censo Escolar."
                  >
                    {(props) => (
                      <Entrada
                        {...props}
                        inputMode="numeric"
                        placeholder="35012345"
                        value={codigo}
                        onChange={(e) => setCodigo(e.target.value)}
                      />
                    )}
                  </Campo>
                </div>
                <Botao
                  type="submit"
                  disabled={escola.carregando || codigo.trim().length === 0}
                  icone={<Search size={15} strokeWidth={2} />}
                >
                  {escola.carregando ? 'Consultando...' : 'Consultar'}
                </Botao>
              </div>

              {escola.erro !== null && <EstadoErro erro={escola.erro} />}

              {escola.resultado !== null && !escola.carregando && (
                <div className="rounded-[4px] border border-line bg-paper px-5 py-4">
                  {grupoEscola == null ? (
                    <p className="prosa text-sm text-ink-80">
                      Nenhum participante com nota de {ROTULOS_AREA[area]} nesta escola na
                      edicao {FORMATO_EDICAO.format(escola.resultado.edicao)}. Confira o
                      codigo, ou experimente outra area.
                    </p>
                  ) : grupoEscola.quantis === null ? (
                    <p className="prosa text-sm text-ink-80">
                      A escola <strong className="text-ink">{grupoEscola.valor}</strong> tem
                      participantes nesta edicao, mas em numero pequeno demais para divulgar
                      a distribuicao com seguranca. Nenhum numero e exibido — e assim que a
                      desidentificacao dos microdados e respeitada.
                    </p>
                  ) : (
                    <dl className="grid gap-4 sm:grid-cols-4">
                      {[
                        {
                          r: 'Escola',
                          v: grupoEscola.valor,
                          n: 'codigo INEP',
                          numerico: false,
                        },
                        {
                          r: 'Participantes',
                          v: FORMATO_INTEIRO.format(grupoEscola.tamanho_amostral ?? 0),
                          n: `com nota em ${ROTULOS_AREA[area]}`,
                          numerico: true,
                        },
                        {
                          r: 'Mediana',
                          v: FORMATO_UMA_CASA.format(grupoEscola.quantis.mediana),
                          n: 'metade ficou abaixo',
                          numerico: true,
                        },
                        {
                          r: 'Intervalo central',
                          v: `${FORMATO_UMA_CASA.format(
                            grupoEscola.quantis.q1,
                          )}–${FORMATO_UMA_CASA.format(grupoEscola.quantis.q3)}`,
                          n: 'do Q1 ao Q3',
                          numerico: true,
                        },
                      ].map((item) => (
                        <div key={item.r}>
                          <dt className="text-[12px] font-medium text-ink-60">{item.r}</dt>
                          <dd>
                            <span
                              className={`font-display text-[19px] text-ink ${
                                item.numerico ? 'numerico' : ''
                              }`}
                            >
                              {item.v}
                            </span>
                            <span className="mt-0.5 block text-xs text-ink-40">{item.n}</span>
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              )}
            </form>
          ) : (
            <div className="flex items-start gap-3">
              <School
                size={18}
                aria-hidden="true"
                strokeWidth={1.75}
                className="mt-0.5 shrink-0 text-ink-40"
              />
              <p className="prosa text-sm leading-relaxed text-ink-80">
                A edicao {edicao !== null ? FORMATO_EDICAO.format(edicao) : 'selecionada'} nao
                publica o codigo da instituicao. O INEP havia retirado essa coluna dos
                microdados do ENEM e{' '}
                {edicaoComCodigo !== undefined ? (
                  <>
                    so voltou a publica-la em{' '}
                    <strong className="font-semibold text-ink">
                      {FORMATO_EDICAO.format(edicaoComCodigo.edicao)}
                    </strong>
                    . Troque a edicao acima para consultar por escola.
                  </>
                ) : (
                  <>nenhuma edicao carregada nesta instalacao a traz de volta.</>
                )}
              </p>
            </div>
          )}
        </Cartao>

        {perfil.resultado !== null && <Linhagem linhagem={perfil.resultado.linhagem} />}
      </div>
    </>
  );
}
