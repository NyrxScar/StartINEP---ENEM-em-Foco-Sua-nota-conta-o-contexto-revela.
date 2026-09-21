/**
 * Comparar edicoes — a mesma nota, o mesmo recorte, anos diferentes.
 *
 * Decisoes:
 *
 * 1. **A omissao e conteudo, nao erro.** `POST /v1/comparacao` devolve
 *    `resultados` e `omissoes`: edicoes que nao entraram e o motivo. A interface
 *    mostra as duas listas com o mesmo peso, porque "2025 ficou de fora porque
 *    ainda nao publicou notas" e uma resposta legitima e frequentemente a mais
 *    informativa da tela.
 * 2. **O recorte fica em um seletor de UF apenas.** Comparar edicoes exige que o
 *    recorte exista em todas elas; UF e a unica dimensao presente em toda edicao
 *    com notas, entao oferecer as oito dimensoes aqui produziria sobretudo
 *    omissoes. Recortes finos tem lugar no Diagnostico, sobre uma edicao so.
 * 3. **Sem edicao selecionada, nada e enviado.** O botao explica o que falta em
 *    vez de deixar a pessoa descobrir por uma resposta vazia.
 */

import { GitCompareArrows, TriangleAlert } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import BarrasComparacao, { type ItemComparacao } from '@/components/BarrasComparacao';
import CabecalhoPagina from '@/components/CabecalhoPagina';
import EstadoErro from '@/components/EstadoErro';
import Linhagem from '@/components/Linhagem';
import Botao from '@/components/ui/Botao';
import { Campo, Entrada, Selecao } from '@/components/ui/Campo';
import Cartao from '@/components/ui/Cartao';
import { LinhaCarregando } from '@/components/ui/Carregando';
import Distintivo from '@/components/ui/Distintivo';
import TabelaDados from '@/components/ui/TabelaDados';
import {
  CODIGO_RESPOSTA_INVALIDA,
  comparar,
  ehErroApi,
  ErroApi,
  listarEdicoes,
} from '@/lib/api';
import { OPCOES_DIMENSAO } from '@/lib/dominios';
import { FORMATO_EDICAO, FORMATO_INTEIRO, FORMATO_UMA_CASA } from '@/lib/formato';
import {
  ROTULOS_AREA,
  type Area,
  type InfoEdicao,
  type ResultadoComparacao,
} from '@/lib/tipos';
import { validarNota } from '@/components/FormularioAnalise';

const TODAS_AREAS = Object.keys(ROTULOS_AREA) as Area[];

/** Traducao dos codigos de omissao de `POST /v1/comparacao` (Req 3.2). */
const MOTIVOS_OMISSAO: Record<string, string> = {
  EDICAO_SEM_NOTAS: 'nao publicou as notas das provas',
  EDICAO_AUSENTE: 'nao esta carregada nesta instalacao',
  RECORTE_INDISPONIVEL: 'nao publica o recorte escolhido',
  PERFIL_NOTA_NAO_COMBINAVEL: 'nao permite cruzar perfil com nota',
};

function comoErroApi(causa: unknown): ErroApi {
  if (ehErroApi(causa)) return causa;
  return new ErroApi({
    codigo: CODIGO_RESPOSTA_INVALIDA,
    mensagem: 'Ocorreu uma falha inesperada ao comparar as edicoes.',
    causa,
  });
}

export default function Comparativo() {
  const base = useId();
  const [edicoesDisponiveis, setEdicoesDisponiveis] = useState<InfoEdicao[]>([]);
  const [selecionadas, setSelecionadas] = useState<number[]>([]);
  const [area, setArea] = useState<Area>('cn');
  const [notaTexto, setNotaTexto] = useState('');
  const [erroNota, setErroNota] = useState<string | null>(null);
  const [uf, setUf] = useState('');

  const [comparacao, setComparacao] = useState<ResultadoComparacao | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [enviando, setEnviando] = useState(false);
  const refEnvio = useRef<AbortController | null>(null);

  useEffect(() => {
    const controlador = new AbortController();
    let ativo = true;
    listarEdicoes({ signal: controlador.signal })
      .then((lista) => {
        if (!ativo) return;
        const ordenadas = [...lista].sort((a, b) => b.edicao - a.edicao);
        setEdicoesDisponiveis(ordenadas);
        // Pre-seleciona tudo que tem nota: e a comparacao que a pessoa quer em
        // quase todos os casos, e ainda assim continua editavel.
        setSelecionadas(
          ordenadas.filter((info) => info.capacidade.possui_notas).map((info) => info.edicao),
        );
      })
      .catch(() => {
        if (ativo) setEdicoesDisponiveis([]);
      });
    return () => {
      ativo = false;
      controlador.abort();
    };
  }, []);

  useEffect(() => () => refEnvio.current?.abort(), []);

  const itens = useMemo<ItemComparacao[]>(() => {
    if (comparacao === null) return [];
    return comparacao.resultados
      .filter((resultado) => resultado.percentil !== null)
      .sort((a, b) => a.edicao - b.edicao)
      .map((resultado) => ({
        edicao: resultado.edicao,
        percentil: resultado.percentil ?? 0,
        detalhe:
          resultado.tamanho_amostral !== null
            ? `${FORMATO_INTEIRO.format(resultado.tamanho_amostral)} pessoas`
            : 'grupo nao divulgado',
      }));
  }, [comparacao]);

  function alternarEdicao(edicao: number) {
    setSelecionadas((atuais) =>
      atuais.includes(edicao)
        ? atuais.filter((valor) => valor !== edicao)
        : [...atuais, edicao].sort((a, b) => a - b),
    );
  }

  async function aoSubmeter(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    const validacao = validarNota(notaTexto);
    if (!validacao.ok) {
      setErroNota(validacao.mensagem);
      return;
    }
    setErroNota(null);
    if (selecionadas.length < 2) return;

    refEnvio.current?.abort();
    const controlador = new AbortController();
    refEnvio.current = controlador;
    setEnviando(true);
    setErro(null);

    try {
      const resposta = await comparar(
        {
          edicoes: selecionadas,
          area,
          nota: validacao.nota,
          recorte: { filtros: uf.length > 0 ? { uf_prova: uf } : {} },
        },
        { signal: controlador.signal },
      );
      if (!controlador.signal.aborted) {
        setComparacao(resposta);
      }
    } catch (causa) {
      if (!controlador.signal.aborted) {
        setComparacao(null);
        setErro(comoErroApi(causa));
      }
    } finally {
      if (refEnvio.current === controlador) {
        refEnvio.current = null;
        setEnviando(false);
      }
    }
  }

  const poucasEdicoes = selecionadas.length < 2;
  const primeiroResultado = comparacao?.resultados[0];

  return (
    <>
      <CabecalhoPagina
        titulo="Comparar edicoes"
        descricao="A mesma nota posicionada em anos diferentes. Uma nota que valia o percentil 70 em uma edicao pode valer outro em outra, porque quem prestou a prova mudou."
      />

      <div className="space-y-6">
        <section
          aria-labelledby={`${base}-titulo`}
          className="overflow-hidden rounded-[4px] border border-line bg-surface"
        >
          <form onSubmit={aoSubmeter} noValidate>
            <div className="border-b border-line p-5">
              <h2 id={`${base}-titulo`} className="text-[17px] text-ink">
                Parametros da comparacao
              </h2>

              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <Campo
                  id={`${base}-nota`}
                  rotulo="Sua nota (de 0 a 1000)"
                  ajuda="A mesma nota e posicionada em cada edicao."
                  erro={erroNota}
                >
                  {(props) => (
                    <Entrada
                      {...props}
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={1000}
                      step={0.1}
                      placeholder="623.5"
                      value={notaTexto}
                      onChange={(evento) => {
                        setNotaTexto(evento.target.value);
                        if (erroNota !== null) setErroNota(null);
                      }}
                    />
                  )}
                </Campo>

                <Campo id={`${base}-area`} rotulo="Area">
                  {(props) => (
                    <Selecao
                      {...props}
                      value={area}
                      onChange={(evento) => setArea(evento.target.value as Area)}
                    >
                      {TODAS_AREAS.map((valor) => (
                        <option key={valor} value={valor}>
                          {ROTULOS_AREA[valor]}
                        </option>
                      ))}
                    </Selecao>
                  )}
                </Campo>

                <Campo
                  id={`${base}-uf`}
                  rotulo="UF da prova"
                  ajuda="Unico recorte presente em todas as edicoes com notas."
                >
                  {(props) => (
                    <Selecao
                      {...props}
                      value={uf}
                      onChange={(evento) => setUf(evento.target.value)}
                    >
                      <option value="">Todo o pais</option>
                      {(OPCOES_DIMENSAO.uf_prova ?? []).map((opcao) => (
                        <option key={opcao.valor} value={opcao.valor}>
                          {opcao.rotulo}
                        </option>
                      ))}
                    </Selecao>
                  )}
                </Campo>
              </div>
            </div>

            <fieldset className="border-b border-line bg-paper/60 p-5">
              <legend className="px-1 text-[13px] font-semibold text-ink-80">
                Edicoes a comparar
              </legend>
              <p className="text-xs text-ink-60">
                Escolha ao menos duas. Edicoes sem notas publicadas podem ser
                selecionadas, e a resposta dira por que ficaram de fora.
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                {edicoesDisponiveis.length === 0 && (
                  <p className="text-xs text-ink-40">Carregando edicoes disponiveis...</p>
                )}
                {edicoesDisponiveis.map((info) => {
                  const marcada = selecionadas.includes(info.edicao);
                  return (
                    <label
                      key={info.edicao}
                      className={`inline-flex cursor-pointer items-center gap-2 rounded-[4px] border px-3 py-1.5 text-sm transition-colors ${
                        marcada
                          ? 'border-coorte bg-coorte-fraco text-ink'
                          : 'border-line-forte bg-surface text-ink-60 hover:border-ink-40'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={marcada}
                        onChange={() => alternarEdicao(info.edicao)}
                        className="size-3.5 accent-[#00899b]"
                      />
                      <span className="numerico font-medium">
                        {FORMATO_EDICAO.format(info.edicao)}
                      </span>
                      {!info.capacidade.possui_notas && (
                        <span className="text-xs text-ink-40">sem notas</span>
                      )}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <div className="flex flex-wrap items-center gap-3 p-5">
              <Botao
                type="submit"
                disabled={enviando || poucasEdicoes}
                icone={<GitCompareArrows size={15} strokeWidth={2} />}
                aria-describedby={poucasEdicoes ? `${base}-bloqueio` : undefined}
              >
                {enviando ? 'Comparando...' : 'Comparar edicoes'}
              </Botao>
              {poucasEdicoes && (
                <p id={`${base}-bloqueio`} className="text-xs text-ink-60">
                  Escolha ao menos duas edicoes para comparar.
                </p>
              )}
            </div>
          </form>
        </section>

        <p role="status" aria-live="polite" className={enviando ? '' : 'sr-only'}>
          {enviando ? <LinhaCarregando>Comparando as edicoes...</LinhaCarregando> : ''}
        </p>

        {erro !== null && <EstadoErro erro={erro} />}

        {comparacao !== null && !enviando && (
          <div className="space-y-6">
            {itens.length > 0 ? (
              <Cartao
                titulo={`Seu percentil em ${ROTULOS_AREA[area]}, por edicao`}
                descricao={
                  uf.length > 0
                    ? `Comparado apenas com quem fez a prova em ${uf}.`
                    : 'Comparado com todo o pais.'
                }
              >
                <BarrasComparacao
                  itens={itens}
                  descricao={`Percentil da sua nota de ${ROTULOS_AREA[area]} em cada edicao comparada: ${itens
                    .map(
                      (item) =>
                        `${FORMATO_EDICAO.format(item.edicao)}, ${FORMATO_UMA_CASA.format(
                          item.percentil,
                        )} por cento`,
                    )
                    .join('; ')}. Os mesmos numeros estao na tabela a seguir.`}
                />
              </Cartao>
            ) : (
              <p className="rounded-[4px] border border-dashed border-line-forte bg-surface px-6 py-8 text-center text-sm text-ink-60">
                Nenhuma das edicoes escolhidas produziu um percentil divulgavel para
                este recorte.
              </p>
            )}

            {comparacao.resultados.length > 0 && (
              <Cartao
                titulo="Numeros por edicao"
                descricao="Os mesmos valores do grafico, com o tamanho do grupo e a mediana."
                semPadding
              >
                <TabelaDados
                  legenda={`Percentil, tamanho do grupo e mediana em ${ROTULOS_AREA[area]}, por edicao`}
                  legendaOculta
                  linhas={[...comparacao.resultados].sort((a, b) => a.edicao - b.edicao)}
                  chaveLinha={(resultado) => String(resultado.edicao)}
                  colunas={[
                    {
                      chave: 'edicao',
                      cabecalho: 'Edicao',
                      largura: '20%',
                      celula: (resultado) => FORMATO_EDICAO.format(resultado.edicao),
                    },
                    {
                      chave: 'percentil',
                      cabecalho: 'Seu percentil',
                      alinhamento: 'fim',
                      celula: (resultado) =>
                        resultado.percentil !== null
                          ? `${FORMATO_UMA_CASA.format(resultado.percentil)}%`
                          : 'suprimido',
                    },
                    {
                      chave: 'amostra',
                      cabecalho: 'Pessoas no grupo',
                      alinhamento: 'fim',
                      celula: (resultado) =>
                        resultado.tamanho_amostral !== null
                          ? FORMATO_INTEIRO.format(resultado.tamanho_amostral)
                          : 'suprimido',
                    },
                    {
                      chave: 'mediana',
                      cabecalho: 'Mediana do grupo',
                      alinhamento: 'fim',
                      celula: (resultado) =>
                        resultado.distribuicao !== null
                          ? FORMATO_UMA_CASA.format(resultado.distribuicao.quantis.mediana)
                          : 'suprimida',
                    },
                  ]}
                />
              </Cartao>
            )}

            {comparacao.omissoes.length > 0 && (
              <Cartao
                titulo="Edicoes fora da comparacao"
                descricao="Nenhuma delas foi estimada. Quando o dado nao existe, a edicao sai da comparacao e o motivo fica registrado."
              >
                <ul className="space-y-2">
                  {comparacao.omissoes.map((omissao) => (
                    <li
                      key={omissao.edicao}
                      className="flex flex-wrap items-center gap-2 text-sm text-ink-80"
                    >
                      <TriangleAlert
                        size={15}
                        aria-hidden="true"
                        strokeWidth={1.75}
                        className="shrink-0 text-vinho"
                      />
                      <span className="numerico font-medium text-ink">
                        {FORMATO_EDICAO.format(omissao.edicao)}
                      </span>
                      <span>
                        {MOTIVOS_OMISSAO[omissao.codigo] ??
                          'ficou de fora por uma limitacao dos dados'}
                        .
                      </span>
                      <Distintivo tom="recusa">{omissao.codigo}</Distintivo>
                    </li>
                  ))}
                </ul>
              </Cartao>
            )}

            {primeiroResultado !== undefined && (
              <Linhagem linhagem={primeiroResultado.linhagem} />
            )}
          </div>
        )}
      </div>
    </>
  );
}
