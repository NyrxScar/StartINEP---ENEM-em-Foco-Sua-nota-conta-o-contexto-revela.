/**
 * Hooks compartilhados entre as secoes do painel.
 *
 * Existem porque a mesma sequencia — buscar, cancelar ao desmontar, normalizar
 * a falha para `ErroApi`, expor carregando/erro — ja estava escrita tres vezes
 * com pequenas divergencias de comportamento entre elas. Uma so implementacao
 * significa que uma correcao de cancelamento vale para todas as telas.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  CODIGO_RESPOSTA_INVALIDA,
  ehErroApi,
  ErroApi,
  explorar,
  listarEdicoes,
} from '@/lib/api';
import type { Dimensao, InfoEdicao, Recorte, ResultadoExploracao } from '@/lib/tipos';
import type { Area } from '@/lib/tipos';

/** Normaliza qualquer falha para o tipo unico de erro do cliente. */
export function comoErroApi(causa: unknown): ErroApi {
  if (ehErroApi(causa)) return causa;
  return new ErroApi({
    codigo: CODIGO_RESPOSTA_INVALIDA,
    mensagem: 'Ocorreu uma falha inesperada ao consultar a API.',
    causa,
  });
}

export interface EstadoEdicoes {
  edicoes: InfoEdicao[];
  carregando: boolean;
  erro: ErroApi | null;
  /** Refaz a busca; util depois de uma falha de rede. */
  recarregar: () => void;
}

/**
 * Carrega `GET /v1/edicoes`, ja ordenado da mais recente para a mais antiga.
 *
 * A ordenacao vive aqui e nao em cada tela porque a API nao promete ordem e
 * todas as telas querem a mesma: a edicao mais recente primeiro.
 */
export function useEdicoes(): EstadoEdicoes {
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
        setErro(comoErroApi(causa));
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });

    return () => {
      ativo = false;
      controlador.abort();
    };
  }, [tentativa]);

  return { edicoes, carregando, erro, recarregar };
}

export interface PedidoExploracao {
  edicao: number;
  area: Area;
  dimensao: Dimensao;
  recorte?: Recorte;
}

export interface EstadoExploracao {
  resultado: ResultadoExploracao | null;
  carregando: boolean;
  erro: ErroApi | null;
  /** Dispara a consulta; a anterior em voo e abortada. */
  consultar: (pedido: PedidoExploracao) => void;
  limpar: () => void;
}

/**
 * Executa `POST /v1/exploracao` mantendo apenas a consulta mais recente.
 *
 * Trocar de dimensao rapidamente dispara varias requisicoes, e as respostas
 * podem chegar fora de ordem — uma consulta antiga sobrescreveria a nova na
 * tela. Abortar a anterior a cada disparo elimina a corrida na origem, em vez
 * de tentar reconhecer respostas obsoletas na chegada.
 */
export function useExploracao(): EstadoExploracao {
  const [resultado, setResultado] = useState<ResultadoExploracao | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const emVoo = useRef<AbortController | null>(null);

  useEffect(() => () => emVoo.current?.abort(), []);

  const consultar = useCallback((pedido: PedidoExploracao) => {
    emVoo.current?.abort();
    const controlador = new AbortController();
    emVoo.current = controlador;
    setCarregando(true);
    setErro(null);

    explorar(
      {
        edicao: pedido.edicao,
        area: pedido.area,
        dimensao: pedido.dimensao,
        recorte: pedido.recorte ?? { filtros: {} },
      },
      { signal: controlador.signal },
    )
      .then((resposta) => {
        if (!controlador.signal.aborted) setResultado(resposta);
      })
      .catch((causa: unknown) => {
        if (controlador.signal.aborted) return;
        setResultado(null);
        setErro(comoErroApi(causa));
      })
      .finally(() => {
        if (emVoo.current === controlador) {
          emVoo.current = null;
          setCarregando(false);
        }
      });
  }, []);

  const limpar = useCallback(() => {
    emVoo.current?.abort();
    setResultado(null);
    setErro(null);
    setCarregando(false);
  }, []);

  return useMemo(
    () => ({ resultado, carregando, erro, consultar, limpar }),
    [resultado, carregando, erro, consultar, limpar],
  );
}
