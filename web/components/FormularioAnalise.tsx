/**
 * `FormularioAnalise` — entrada de Nota, Area, Edicao e Recorte (task 12.2).
 *
 * Responsabilidade unica: **coletar entrada valida, submeter e devolver o
 * desfecho ao pai**. A renderizacao do resultado e da task 12.3
 * (`VisualizacaoResultado`) e os estados de UI/linhagem sao da 12.4; por isso
 * este componente nao renderiza distribuicao nem linhagem, apenas notifica via
 * `onResultado` / `onErro` / `onCarregando`.
 *
 * Decisoes de projeto:
 *
 * 1. **A capacidade da edicao guia a UI** (Req 4.6 / Req 2). O formulario
 *    carrega `GET /v1/edicoes` (que ja traz a capacidade de cada edicao) e
 *    reconfirma a da edicao selecionada em
 *    `GET /v1/edicoes/{edicao}/capacidade`. Somente as dimensoes de
 *    `dimensoes_suportadas` viram controle; quando
 *    `perfil_combinavel_com_notas` e falso, as dimensoes de perfil saem de cena
 *    (nao ha analise de nota com perfil em 2024); quando `possui_notas` e falso
 *    (2025), a submissao e desabilitada com a razao exibida. A pessoa e
 *    afastada das combinacoes impossiveis em vez de descobri-las por um 409.
 * 2. **Nota validada no cliente** (Req 4.2/1.8): 0–1000 inclusive, antes de
 *    qualquer requisicao, com mensagem inline associada por `aria-describedby` e
 *    `aria-invalid`. A validacao da API continua sendo a autoridade final.
 * 3. **Degradacao sem API** (design, "API inacessivel"): se `/v1/edicoes` falha,
 *    o formulario exibe o erro (`ERRO_REDE`, `TIMEOUT`, ...), oferece "Tentar
 *    novamente" e mantem a submissao desabilitada — nada quebra, nada trava.
 * 4. **Acessibilidade** (Req 4.4): `<form>` com `<fieldset>`/`<legend>` para o
 *    recorte, todo controle com `<label htmlFor>`, erros anunciados
 *    (`role="alert"`), mudancas de capacidade anunciadas (`aria-live="polite"`),
 *    e botao de envio com nome acessivel.
 * 5. **A barra de filtros e derivada da capacidade, nao fixa.** Cada edicao
 *    publica um conjunto diferente de dimensoes, entao os controles nascem de
 *    `capacidade.dimensoes_suportadas` — nenhum filtro e escrito a mao aqui. O
 *    resumo acima da barra nomeia o que ficou de fora e por que, para que a
 *    ausencia de um controle seja informacao e nao um buraco silencioso.
 */

import { Search, SlidersHorizontal } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import Botao from '@/components/ui/Botao';
import { Campo, Entrada, Selecao } from '@/components/ui/Campo';
import {
  analisar,
  CODIGO_RESPOSTA_INVALIDA,
  ehErroApi,
  ErroApi,
  listarEdicoes,
  obterCapacidade,
} from '@/lib/api';
import { DIMENSOES_PERFIL, OPCOES_DIMENSAO } from '@/lib/dominios';
import { enumerar } from '@/lib/formato';
import {
  ROTULOS_AREA,
  ROTULOS_DIMENSAO,
  type Area,
  type Capacidade,
  type Dimensao,
  type InfoEdicao,
  type Recorte,
  type ResultadoAnalise,
} from '@/lib/tipos';

/** Contrato com o pai (`PainelAnalise`), que detem o estado compartilhado. */
export interface FormularioAnaliseProps {
  /** Chamado com o resultado de `POST /v1/analise` bem-sucedido. */
  onResultado: (resultado: ResultadoAnalise) => void;
  /** Chamado com o erro tipado da API (ramificar por `erro.codigo`). */
  onErro: (erro: ErroApi) => void;
  /** Sinaliza inicio/fim da requisicao, para o indicador de carregamento (Req 4.5). */
  onCarregando?: (carregando: boolean) => void;
}

/** Todas as dimensoes na ordem canonica dos rotulos. */
const TODAS_DIMENSOES = Object.keys(ROTULOS_DIMENSAO) as Dimensao[];

/** Todas as areas na ordem canonica dos rotulos. */
const TODAS_AREAS = Object.keys(ROTULOS_AREA) as Area[];

/** Limites do intervalo valido de Nota (Req 1.8/4.2). */
const NOTA_MINIMA = 0;
const NOTA_MAXIMA = 1000;

/** Resultado da validacao client-side da nota. */
type ValidacaoNota = { ok: true; nota: number } | { ok: false; mensagem: string };

/**
 * Valida o texto digitado como Nota: obrigatorio, numerico e em 0..1000.
 * Aceita virgula como separador decimal (uso comum em pt-BR).
 */
export function validarNota(texto: string): ValidacaoNota {
  const limpo = texto.trim().replace(',', '.');
  if (limpo.length === 0) {
    return { ok: false, mensagem: 'Informe sua nota para calcular a posicao.' };
  }
  const nota = Number(limpo);
  if (!Number.isFinite(nota)) {
    return { ok: false, mensagem: 'A nota deve ser um numero, como 623.5.' };
  }
  if (nota < NOTA_MINIMA || nota > NOTA_MAXIMA) {
    return {
      ok: false,
      mensagem: `A nota deve estar entre ${NOTA_MINIMA} e ${NOTA_MAXIMA}.`,
    };
  }
  return { ok: true, nota };
}

/** Normaliza qualquer falha para o tipo unico de erro do cliente. */
function comoErroApi(causa: unknown): ErroApi {
  if (ehErroApi(causa)) return causa;
  return new ErroApi({
    codigo: CODIGO_RESPOSTA_INVALIDA,
    mensagem: 'Ocorreu uma falha inesperada ao consultar a API.',
    causa,
  });
}

/** Edicao inicial: a mais recente que possui notas; sem nenhuma, a mais recente. */
function edicaoPadrao(lista: InfoEdicao[]): number | null {
  if (lista.length === 0) return null;
  const ordenadas = [...lista].sort((a, b) => b.edicao - a.edicao);
  const comNotas = ordenadas.find((info) => info.capacidade.possui_notas);
  const escolhida = comNotas ?? ordenadas[0];
  return escolhida ? escolhida.edicao : null;
}

export default function FormularioAnalise({
  onResultado,
  onErro,
  onCarregando,
}: FormularioAnaliseProps) {
  const base = useId();
  const idNota = `${base}-nota`;
  const idArea = `${base}-area`;
  const idEdicao = `${base}-edicao`;

  const [edicoes, setEdicoes] = useState<InfoEdicao[]>([]);
  const [carregandoEdicoes, setCarregandoEdicoes] = useState(true);
  const [erroEdicoes, setErroEdicoes] = useState<ErroApi | null>(null);
  const [tentativaEdicoes, setTentativaEdicoes] = useState(0);

  const [edicaoSelecionada, setEdicaoSelecionada] = useState<number | null>(null);
  const [capacidadeApi, setCapacidadeApi] = useState<Capacidade | null>(null);
  const [avisoCapacidade, setAvisoCapacidade] = useState<ErroApi | null>(null);

  const [area, setArea] = useState<Area>('cn');
  const [notaTexto, setNotaTexto] = useState('');
  const [erroNota, setErroNota] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<Partial<Record<Dimensao, string>>>({});
  const [enviando, setEnviando] = useState(false);

  const refNota = useRef<HTMLInputElement>(null);
  const refEnvio = useRef<AbortController | null>(null);

  // Catalogo de edicoes (com capacidade embutida). Falha aqui e recuperavel:
  // o botao "Tentar novamente" incrementa `tentativaEdicoes` e refaz a busca.
  useEffect(() => {
    const controlador = new AbortController();
    let ativo = true;
    setCarregandoEdicoes(true);
    setErroEdicoes(null);

    listarEdicoes({ signal: controlador.signal })
      .then((lista) => {
        if (!ativo) return;
        setEdicoes(lista);
        setEdicaoSelecionada(edicaoPadrao(lista));
      })
      .catch((causa: unknown) => {
        if (!ativo || controlador.signal.aborted) return;
        setEdicoes([]);
        setEdicaoSelecionada(null);
        setErroEdicoes(comoErroApi(causa));
      })
      .finally(() => {
        if (ativo) setCarregandoEdicoes(false);
      });

    return () => {
      ativo = false;
      controlador.abort();
    };
  }, [tentativaEdicoes]);

  // Reconfirma a capacidade da edicao escolhida (fonte da task 12.2 no plano:
  // `GET /v1/edicoes/{edicao}/capacidade`). Se falhar, cai para a capacidade que
  // veio na listagem — a UI segue guiada, apenas com um aviso.
  useEffect(() => {
    if (edicaoSelecionada === null) {
      setCapacidadeApi(null);
      setAvisoCapacidade(null);
      return;
    }
    const controlador = new AbortController();
    let ativo = true;
    setAvisoCapacidade(null);

    obterCapacidade(edicaoSelecionada, { signal: controlador.signal })
      .then((capacidade) => {
        if (ativo) setCapacidadeApi(capacidade);
      })
      .catch((causa: unknown) => {
        if (!ativo || controlador.signal.aborted) return;
        setCapacidadeApi(null);
        setAvisoCapacidade(comoErroApi(causa));
      });

    return () => {
      ativo = false;
      controlador.abort();
    };
  }, [edicaoSelecionada]);

  const infoSelecionada = useMemo(
    () => edicoes.find((info) => info.edicao === edicaoSelecionada) ?? null,
    [edicoes, edicaoSelecionada],
  );

  /** Capacidade vigente: a do endpoint dedicado, com fallback para a listagem. */
  const capacidade: Capacidade | null =
    capacidadeApi !== null && capacidadeApi.edicao === edicaoSelecionada
      ? capacidadeApi
      : (infoSelecionada?.capacidade ?? null);

  /**
   * Dimensoes efetivamente oferecidas: suportadas pela edicao **e** combinaveis
   * com nota. `dimensoes_suportadas` e filtrado pela ordem canonica para manter
   * a UI estavel independentemente da ordem que a API serializar.
   */
  const dimensoesDisponiveis = useMemo<Dimensao[]>(() => {
    if (capacidade === null) return [];
    const suportadas = new Set(capacidade.dimensoes_suportadas);
    return TODAS_DIMENSOES.filter((dimensao) => {
      if (!suportadas.has(dimensao)) return false;
      if (!capacidade.perfil_combinavel_com_notas && DIMENSOES_PERFIL.includes(dimensao)) {
        return false;
      }
      return true;
    });
  }, [capacidade]);

  const dimensoesBloqueadas = useMemo<Dimensao[]>(() => {
    if (capacidade === null) return [];
    const disponiveis = new Set(dimensoesDisponiveis);
    return TODAS_DIMENSOES.filter((dimensao) => !disponiveis.has(dimensao));
  }, [capacidade, dimensoesDisponiveis]);

  // Um filtro nunca sobrevive a uma troca de edicao que o torne indisponivel:
  // impede submeter um recorte que a API recusaria com RECORTE_INDISPONIVEL.
  useEffect(() => {
    const permitidas = new Set(dimensoesDisponiveis);
    setFiltros((atuais) => {
      const chaves = Object.keys(atuais) as Dimensao[];
      if (chaves.every((chave) => permitidas.has(chave))) return atuais;
      const proximos: Partial<Record<Dimensao, string>> = {};
      for (const chave of chaves) {
        const valor = atuais[chave];
        if (permitidas.has(chave) && valor !== undefined) proximos[chave] = valor;
      }
      return proximos;
    });
  }, [dimensoesDisponiveis]);

  // Cancela requisicao em voo ao desmontar.
  useEffect(() => () => refEnvio.current?.abort(), []);

  const semNotas = capacidade !== null && !capacidade.possui_notas;
  const podeSubmeter =
    edicaoSelecionada !== null && capacidade !== null && capacidade.possui_notas && !enviando;

  /** Razao textual quando a submissao esta bloqueada (Req 4.6). */
  const razaoBloqueio: string | null = (() => {
    if (enviando) return null;
    if (carregandoEdicoes) return 'Carregando as edicoes disponiveis...';
    if (erroEdicoes !== null) {
      return `Nao foi possivel carregar as edicoes: ${erroEdicoes.mensagem}`;
    }
    if (edicaoSelecionada === null) return 'Nenhuma edicao esta disponivel na base.';
    if (capacidade === null) {
      return `Nao foi possivel determinar a capacidade da edicao ${edicaoSelecionada}${
        avisoCapacidade !== null ? `: ${avisoCapacidade.mensagem}` : '.'
      }`;
    }
    if (semNotas) {
      return `A edicao ${capacidade.edicao} nao possui notas publicadas, portanto nao e possivel calcular percentil de nota nela. Escolha outra edicao.`;
    }
    return null;
  })();

  /** Resumo do que a edicao permite, anunciado quando a selecao muda. */
  const resumoCapacidade: string = (() => {
    if (capacidade === null) return '';
    const partes: string[] = [];
    if (dimensoesDisponiveis.length > 0) {
      partes.push(
        `Recortes disponiveis nesta edicao: ${enumerar(
          dimensoesDisponiveis.map((dimensao) => ROTULOS_DIMENSAO[dimensao]),
        )}.`,
      );
    } else {
      partes.push('Esta edicao nao oferece nenhum recorte para analise de nota.');
    }
    if (dimensoesBloqueadas.length > 0) {
      partes.push(
        `Indisponiveis: ${enumerar(
          dimensoesBloqueadas.map((dimensao) => ROTULOS_DIMENSAO[dimensao]),
        )}.`,
      );
    }
    if (!capacidade.perfil_combinavel_com_notas) {
      partes.push(
        'Nesta edicao o perfil socioeconomico e as notas estao em arquivos que nao podem ser combinados, por isso recortes de perfil ficam fora da analise de nota.',
      );
    }
    return partes.join(' ');
  })();

  function definirFiltro(dimensao: Dimensao, valor: string) {
    setFiltros((atuais) => {
      const proximos = { ...atuais };
      if (valor.trim().length === 0) {
        delete proximos[dimensao];
      } else {
        proximos[dimensao] = valor;
      }
      return proximos;
    });
  }

  function montarRecorte(): Recorte {
    const filtrosLimpos: Partial<Record<Dimensao, string>> = {};
    for (const dimensao of dimensoesDisponiveis) {
      const valor = filtros[dimensao];
      if (valor !== undefined && valor.trim().length > 0) {
        filtrosLimpos[dimensao] = valor.trim();
      }
    }
    return { filtros: filtrosLimpos };
  }

  async function executar(edicao: number, nota: number, recorte: Recorte) {
    refEnvio.current?.abort();
    const controlador = new AbortController();
    refEnvio.current = controlador;
    setEnviando(true);
    onCarregando?.(true);

    try {
      const resultado = await analisar(
        { edicao, area, nota, recorte },
        { signal: controlador.signal },
      );
      if (!controlador.signal.aborted) onResultado(resultado);
    } catch (causa) {
      if (!controlador.signal.aborted) onErro(comoErroApi(causa));
    } finally {
      if (refEnvio.current === controlador) {
        refEnvio.current = null;
        setEnviando(false);
        onCarregando?.(false);
      }
    }
  }

  function aoSubmeter(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    const validacao = validarNota(notaTexto);
    if (!validacao.ok) {
      setErroNota(validacao.mensagem);
      refNota.current?.focus();
      return;
    }
    setErroNota(null);

    if (!podeSubmeter || edicaoSelecionada === null) return;
    void executar(edicaoSelecionada, validacao.nota, montarRecorte());
  }

  return (
    <section
      aria-labelledby={`${base}-titulo`}
      className="overflow-hidden rounded-[4px] border border-line bg-surface"
    >
      <form onSubmit={aoSubmeter} noValidate>
        <div className="border-b border-line p-5">
          <h2 id={`${base}-titulo`} className="text-[17px] text-ink">
            Informe sua nota
          </h2>
          <p className="prosa mt-1 text-sm text-ink-60">
            A nota fica no seu navegador: ela viaja para a API apenas para ser
            posicionada na distribuicao, e nada e gravado.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <Campo
              id={idNota}
              rotulo="Sua nota (de 0 a 1000)"
              ajuda="Use ponto para o decimal, como 623.5."
              erro={erroNota}
            >
              {(props) => (
                <Entrada
                  {...props}
                  ref={refNota}
                  name="nota"
                  type="number"
                  inputMode="decimal"
                  min={NOTA_MINIMA}
                  max={NOTA_MAXIMA}
                  step={0.1}
                  placeholder="623.5"
                  value={notaTexto}
                  required
                  onChange={(evento) => {
                    setNotaTexto(evento.target.value);
                    if (erroNota !== null) setErroNota(null);
                  }}
                />
              )}
            </Campo>

            <Campo id={idArea} rotulo="Area">
              {(props) => (
                <Selecao
                  {...props}
                  name="area"
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

            <Campo id={idEdicao} rotulo="Edicao">
              {(props) => (
                <Selecao
                  {...props}
                  name="edicao"
                  value={edicaoSelecionada ?? ''}
                  disabled={carregandoEdicoes || edicoes.length === 0}
                  onChange={(evento) => {
                    const valor = Number(evento.target.value);
                    setEdicaoSelecionada(Number.isFinite(valor) ? valor : null);
                  }}
                >
                  {edicoes.length === 0 && (
                    <option value="">
                      {carregandoEdicoes ? 'Carregando...' : 'Nenhuma edicao disponivel'}
                    </option>
                  )}
                  {edicoes
                    .slice()
                    .sort((a, b) => b.edicao - a.edicao)
                    .map((info) => (
                      <option key={info.edicao} value={info.edicao}>
                        {info.capacidade.possui_notas
                          ? String(info.edicao)
                          : `${info.edicao} (sem notas publicadas)`}
                      </option>
                    ))}
                </Selecao>
              )}
            </Campo>
          </div>

          {/* O resumo de capacidade fica fora do `Campo` porque descreve a
              edicao inteira, nao o controle; `aria-live` anuncia a troca. */}
          <p
            id={`${idEdicao}-capacidade`}
            aria-live="polite"
            className="prosa mt-3 text-xs leading-relaxed text-ink-60"
          >
            {resumoCapacidade}
          </p>
        </div>

        {/* Barra de filtros: o recorte comparavel. */}
        <fieldset className="border-b border-line bg-paper/60 p-5">
          <legend className="flex items-center gap-2 px-1 text-[13px] font-semibold text-ink-80">
            <SlidersHorizontal size={14} aria-hidden="true" strokeWidth={1.75} />
            Recorte (opcional)
          </legend>
          <p className="prosa text-xs text-ink-60">
            Deixe em branco para comparar com toda a edicao. Cada filtro aplicado
            estreita o grupo de comparacao.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {dimensoesDisponiveis.map((dimensao) => {
              const idFiltro = `${base}-filtro-${dimensao}`;
              const opcoes = OPCOES_DIMENSAO[dimensao];
              const valor = filtros[dimensao] ?? '';
              return (
                <Campo
                  key={dimensao}
                  id={idFiltro}
                  rotulo={ROTULOS_DIMENSAO[dimensao]}
                  ajuda={
                    opcoes === undefined
                      ? 'Informe o valor exatamente como aparece na base; deixe vazio para nao filtrar.'
                      : undefined
                  }
                >
                  {(props) =>
                    opcoes !== undefined ? (
                      <Selecao
                        {...props}
                        name={dimensao}
                        value={valor}
                        onChange={(evento) => definirFiltro(dimensao, evento.target.value)}
                      >
                        <option value="">Sem filtro</option>
                        {opcoes.map((opcao) => (
                          <option key={opcao.valor} value={opcao.valor}>
                            {opcao.rotulo}
                          </option>
                        ))}
                      </Selecao>
                    ) : (
                      <Entrada
                        {...props}
                        name={dimensao}
                        type="text"
                        value={valor}
                        onChange={(evento) => definirFiltro(dimensao, evento.target.value)}
                      />
                    )
                  }
                </Campo>
              );
            })}

          </div>

          {dimensoesDisponiveis.length === 0 && (
            <p className="prosa mt-3 text-xs text-ink-60">
              {capacidade === null
                ? 'Escolha uma edicao para ver os recortes disponiveis.'
                : 'Nenhum recorte esta disponivel para analise de nota nesta edicao.'}
            </p>
          )}
        </fieldset>

        <div className="flex flex-wrap items-center gap-3 p-5">
          <Botao
            type="submit"
            disabled={!podeSubmeter}
            icone={<Search size={15} strokeWidth={2} />}
            aria-describedby={razaoBloqueio !== null ? `${base}-bloqueio` : undefined}
          >
            {enviando ? 'Consultando...' : 'Ver minha posicao'}
          </Botao>

          {erroEdicoes !== null && (
            <Botao variante="secundario" onClick={() => setTentativaEdicoes((n) => n + 1)}>
              Tentar novamente
            </Botao>
          )}

          {razaoBloqueio !== null && (
            <p
              id={`${base}-bloqueio`}
              role="alert"
              className="prosa flex-1 text-xs leading-relaxed text-vinho"
            >
              {razaoBloqueio}
            </p>
          )}
        </div>
      </form>
    </section>
  );
}
