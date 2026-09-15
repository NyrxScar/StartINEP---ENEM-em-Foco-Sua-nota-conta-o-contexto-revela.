/**
 * Pagina inicial — esqueleto.
 *
 * Server Component sem I/O de proposito: a silver e um contrato de entrada
 * externo e pode estar ausente, portanto nada e buscado da API em tempo de
 * build/render aqui. Os componentes da experiencia sao compostos por
 * `PainelAnalise`:
 *
 * - 12.2 `FormularioAnalise` — nota (0–1000), area, edicao e recorte filtrado
 *   pela capacidade da edicao;
 * - 12.3 `VisualizacaoResultado` — grafico da distribuicao + equivalente textual
 *   acessivel (quantis, tamanho amostral, percentil);
 * - 12.4 estados de UI (carregando, erro por codigo, amostra insuficiente) e
 *   exibicao da linhagem (edicoes + data de carga).
 *
 * O estado compartilhado entre formulario e visualizacao (e as chamadas a
 * `analisar()` de `@/lib/api`) vive no Client Component `PainelAnalise`
 * introduzido na 12.2 — esta pagina permanece um Server Component.
 */
import PainelAnalise from '@/components/PainelAnalise';

export default function PaginaInicial() {
  return (
    <>
      <h1>Sua nota conta, o contexto revela</h1>
      <p>
        Informe sua nota do ENEM, escolha a area e um recorte comparavel para ver sua
        posicao na distribuicao. Os resultados sao sempre agregados: nenhuma resposta
        individual e exibida.
      </p>

      {/* PainelAnalise detem o estado compartilhado (resultado/erro/carregando) e
          compoe <FormularioAnalise /> (12.2), <VisualizacaoResultado /> (12.3) e
          os estados de UI + <Linhagem /> (12.4). */}
      <PainelAnalise />
    </>
  );
}
