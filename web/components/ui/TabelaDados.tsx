/**
 * `TabelaDados` — tabela com paginacao no cliente.
 *
 * Decisoes:
 *
 * 1. **Sempre uma tabela real.** `<caption>`, `<th scope>` em linha e coluna,
 *    nada de `<div>` fingindo grade. As tabelas deste produto sao o equivalente
 *    textual dos graficos (a mesma informacao, sem depender de enxergar cor ou
 *    forma), entao a semantica aqui nao e detalhe: e o plano B inteiro.
 * 2. **A paginacao e opcional e some sozinha.** Com `paginaTamanho` ausente, ou
 *    com menos linhas do que uma pagina, nenhum controle e renderizado — uma
 *    barra de paginacao sob tres linhas e ruido.
 * 3. **A troca de pagina e anunciada.** O intervalo exibido vive em uma regiao
 *    `aria-live`, porque quem navega por teclado ou leitor de tela precisa saber
 *    que o conteudo abaixo mudou sem que o foco tenha se movido.
 * 4. **A primeira coluna e cabecalho de linha.** Em uma tabela de faixas ou de
 *    edicoes, a celula que identifica a linha nao e um dado como os outros.
 */

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

export interface ColunaTabela<T> {
  /** Chave estavel da coluna; tambem usada como `key` do React. */
  chave: string;
  cabecalho: string;
  celula: (linha: T) => ReactNode;
  /** Alinhamento do conteudo; numeros ficam melhor a direita. */
  alinhamento?: 'inicio' | 'fim';
  /** Largura CSS fixa, quando a coluna nao deve competir por espaco. */
  largura?: string;
}

export interface TabelaDadosProps<T> {
  /** Resumo da tabela, obrigatorio: e o titulo lido por tecnologia assistiva. */
  legenda: string;
  /** `true` esconde a legenda visualmente, mantendo-a no DOM. */
  legendaOculta?: boolean;
  colunas: ColunaTabela<T>[];
  linhas: T[];
  chaveLinha: (linha: T, indice: number) => string;
  /** Linhas por pagina; ausente = sem paginacao. */
  paginaTamanho?: number;
  /** Marca uma linha como a da pessoa (destaque ocre discreto). */
  destacar?: (linha: T) => boolean;
  vazio?: ReactNode;
}

export default function TabelaDados<T>({
  legenda,
  legendaOculta = false,
  colunas,
  linhas,
  chaveLinha,
  paginaTamanho,
  destacar,
  vazio = 'Nenhum dado para exibir.',
}: TabelaDadosProps<T>) {
  const [pagina, setPagina] = useState(0);

  const totalPaginas =
    paginaTamanho === undefined ? 1 : Math.max(1, Math.ceil(linhas.length / paginaTamanho));

  // Um conjunto de linhas menor (filtro aplicado, outro recorte) pode deixar a
  // pagina atual fora do intervalo; sem isto a tabela ficaria em branco.
  useEffect(() => {
    setPagina((atual) => Math.min(atual, totalPaginas - 1));
  }, [totalPaginas]);

  const visiveis = useMemo(() => {
    if (paginaTamanho === undefined) return linhas;
    const inicio = pagina * paginaTamanho;
    return linhas.slice(inicio, inicio + paginaTamanho);
  }, [linhas, pagina, paginaTamanho]);

  const mostrarPaginacao = paginaTamanho !== undefined && linhas.length > paginaTamanho;
  const primeira = pagina * (paginaTamanho ?? 0) + 1;
  const ultima = Math.min((pagina + 1) * (paginaTamanho ?? 0), linhas.length);

  if (linhas.length === 0) {
    return <p className="px-5 py-6 text-sm text-ink-60">{vazio}</p>;
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption
            className={
              legendaOculta
                ? 'sr-only'
                : 'px-5 pb-3 text-left text-xs text-ink-60 caption-top'
            }
          >
            {legenda}
          </caption>
          <thead>
            <tr className="border-y border-line bg-paper">
              {colunas.map((coluna) => (
                <th
                  key={coluna.chave}
                  scope="col"
                  style={coluna.largura !== undefined ? { width: coluna.largura } : undefined}
                  className={`px-4 py-2.5 text-[12px] font-semibold text-ink-80 ${
                    coluna.alinhamento === 'fim' ? 'text-right' : 'text-left'
                  }`}
                >
                  {coluna.cabecalho}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visiveis.map((linha, indice) => {
              const marcada = destacar?.(linha) ?? false;
              return (
                <tr
                  key={chaveLinha(linha, indice)}
                  className={`border-b border-line/70 transition-colors ${
                    marcada ? 'bg-voce-fraco/60' : 'hover:bg-paper/70'
                  }`}
                >
                  {colunas.map((coluna, posicao) => {
                    const conteudo = coluna.celula(linha);
                    const alinhar = coluna.alinhamento === 'fim' ? 'text-right' : 'text-left';
                    return posicao === 0 ? (
                      <th
                        key={coluna.chave}
                        scope="row"
                        className={`px-4 py-2.5 font-medium text-ink ${alinhar} ${
                          marcada ? 'border-l-2 border-voce' : 'border-l-2 border-transparent'
                        }`}
                      >
                        {conteudo}
                      </th>
                    ) : (
                      <td key={coluna.chave} className={`px-4 py-2.5 text-ink-80 ${alinhar}`}>
                        {conteudo}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {mostrarPaginacao && (
        <nav
          aria-label="Paginacao da tabela"
          className="flex items-center justify-between gap-3 border-t border-line px-5 py-3"
        >
          <p className="text-xs text-ink-60" aria-live="polite">
            {primeira}–{ultima} de {linhas.length}
          </p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPagina((n) => Math.max(0, n - 1))}
              disabled={pagina === 0}
              aria-label="Pagina anterior"
              className="rounded-[4px] border border-line-forte p-1.5 text-ink-80 transition-colors hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft size={15} aria-hidden="true" />
            </button>
            <span className="px-2 text-xs text-ink-60">
              {pagina + 1} / {totalPaginas}
            </span>
            <button
              type="button"
              onClick={() => setPagina((n) => Math.min(totalPaginas - 1, n + 1))}
              disabled={pagina >= totalPaginas - 1}
              aria-label="Proxima pagina"
              className="rounded-[4px] border border-line-forte p-1.5 text-ink-80 transition-colors hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        </nav>
      )}
    </div>
  );
}
