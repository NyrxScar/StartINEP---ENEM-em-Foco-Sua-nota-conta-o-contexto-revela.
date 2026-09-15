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

import type { Linhagem as LinhagemDados } from '@/lib/tipos';

/** Data e hora da carga em pt-BR ("12 de marco de 2025 as 14:32"). */
const FORMATO_DATA_HORA = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'long',
  timeStyle: 'short',
});

/** Edicoes sem separador de milhar ("2023", nunca "2.023"). */
const FORMATO_EDICAO = new Intl.NumberFormat('pt-BR', { useGrouping: false });

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
    <section className="linhagem" aria-labelledby="linhagem-titulo">
      <h3 id="linhagem-titulo">Origem dos dados</h3>

      {itens.length === 0 ? (
        <p className="ajuda">
          A resposta nao informou quais edicoes fundamentam este resultado.
        </p>
      ) : (
        <ul className="linhagem-lista">
          {itens.map((item) => (
            <li key={item.edicao}>
              <strong>Edicao {FORMATO_EDICAO.format(item.edicao)}</strong> —{' '}
              {item.dataCarga !== null
                ? `dados carregados em ${item.dataCarga}`
                : 'data de carga nao disponivel'}
              .{' '}
              {item.manifesto !== null ? (
                <>
                  Manifesto: <code>{item.manifesto}</code>
                </>
              ) : (
                <>Manifesto nao disponivel nesta instalacao.</>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="ajuda">
        A data de carga indica quando os microdados desta edicao entraram na base; o
        Manifesto identifica a versao exata do arquivo de origem que sustenta os numeros
        acima.
      </p>
    </section>
  );
}
