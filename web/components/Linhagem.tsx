/**
 * `Linhagem` — de onde vieram os numeros exibidos (task 12.4; Req 5.3).
 *
 * Decisoes de projeto:
 *
 * 1. **Sempre presente, nunca no caminho.** Auditabilidade e o proposito deste
 *    bloco: quem le um percentil precisa poder responder "com base em qual
 *    edicao, carregada quando?". Fica logo abaixo do resultado, com tipografia
 *    reduzida e um cabecalho proprio — visivel sem competir com o achado.
 * 2. **Ausencia e exibida como ausencia.** `Linhagem.manifestos` e
 *    `Linhagem.datas_carga` sao anulaveis por contrato (a silver e seus
 *    Manifestos sao entrada externa e podem nao existir neste ambiente).
 *    Valores nulos, ausentes ou nao parseaveis viram texto explicito — "data de
 *    carga nao disponivel" — e nunca `null`, `undefined` ou `Invalid Date` na
 *    tela.
 * 3. **Datas formatadas em pt-BR a partir do ISO 8601**
 *    (`Intl.DateTimeFormat`), com guarda de `Number.isNaN` antes de formatar.
 *    O timestamp vem do Manifesto do ETL e pode nao trazer fuso; nesse caso o
 *    navegador o interpreta como hora local, que e a leitura mais util para
 *    quem opera a base. Este componente so renderiza no cliente (o painel que o
 *    usa e um Client Component e a linhagem so existe apos uma resposta),
 *    portanto nao ha divergencia de hidratacao por locale/fuso.
 * 4. **Chaves de objeto JSON sao strings.** `datas_carga`/`manifestos` sao
 *    `dict[int, ...]` no backend, logo a busca aqui e por `String(edicao)`.
 */

import { FileClock } from 'lucide-react';

import { FORMATO_DATA_HORA, FORMATO_EDICAO } from '@/lib/formato';
import type { Linhagem as LinhagemDados } from '@/lib/tipos';

export interface LinhagemProps {
  linhagem: LinhagemDados;
}

/**
 * Formata um timestamp ISO 8601 em pt-BR; `null` quando o valor esta ausente,
 * vazio ou nao e uma data interpretavel (nunca "Invalid Date").
 */
export function formatarDataCarga(iso: string | null | undefined): string | null {
  if (typeof iso !== 'string') return null;
  const texto = iso.trim();
  if (texto.length === 0) return null;
  const data = new Date(texto);
  if (Number.isNaN(data.getTime())) return null;
  return FORMATO_DATA_HORA.format(data);
}

/** Uma linha da linhagem, ja resolvida para texto exibivel. */
interface ItemLinhagem {
  edicao: number;
  /** Data de carga formatada, ou `null` quando indisponivel. */
  dataCarga: string | null;
  /** Identificador do Manifesto, ou `null` quando indisponivel. */
  manifesto: string | null;
}

/** Resolve os itens exibiveis a partir da linhagem crua da API. */
export function itensDaLinhagem(linhagem: LinhagemDados): ItemLinhagem[] {
  return [...linhagem.edicoes]
    .sort((a, b) => a - b)
    .map((edicao) => {
      const chave = String(edicao);
      const manifesto = linhagem.manifestos[chave] ?? null;
      return {
        edicao,
        dataCarga: formatarDataCarga(linhagem.datas_carga[chave]),
        manifesto: manifesto !== null && manifesto.trim().length > 0 ? manifesto : null,
      };
    });
}

export default function Linhagem({ linhagem }: LinhagemProps) {
  const itens = itensDaLinhagem(linhagem);

  return (
    <section
      aria-labelledby="linhagem-titulo"
      className="rounded-[4px] border border-line bg-paper px-5 py-4"
    >
      <h3
        id="linhagem-titulo"
        className="flex items-center gap-2 font-sans text-[13px] font-semibold tracking-normal text-ink-80"
      >
        <FileClock size={15} aria-hidden="true" strokeWidth={1.75} className="text-ink-40" />
        Origem dos dados
      </h3>

      {itens.length === 0 ? (
        <p className="mt-2 text-xs text-ink-60">
          A resposta nao informou quais edicoes fundamentam este resultado.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {itens.map((item) => (
            <li key={item.edicao} className="text-xs leading-relaxed text-ink-60">
              <strong className="font-semibold text-ink-80">
                Edicao {FORMATO_EDICAO.format(item.edicao)}
              </strong>{' '}
              &mdash;{' '}
              {item.dataCarga !== null
                ? `dados carregados em ${item.dataCarga}`
                : 'data de carga nao disponivel'}
              .{' '}
              {item.manifesto !== null ? (
                <>
                  Manifesto:{' '}
                  <code className="rounded-sm bg-surface px-1 py-0.5 text-[11px] text-ink-80">
                    {item.manifesto}
                  </code>
                </>
              ) : (
                <>Manifesto nao disponivel nesta instalacao.</>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="prosa mt-3 border-t border-line pt-3 text-xs text-ink-40">
        A data de carga indica quando os microdados desta edicao entraram na base; o
        Manifesto identifica a versao exata do arquivo de origem que sustenta os numeros
        acima.
      </p>
    </section>
  );
}
