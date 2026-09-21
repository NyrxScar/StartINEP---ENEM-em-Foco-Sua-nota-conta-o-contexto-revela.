/**
 * Relatorios por escola — secao sem fonte de dados.
 *
 * A API do Radar ENEM nao expoe nada por instituicao: nao ha endpoint de
 * escolas, nao ha codigo de escola nas respostas e o recorte mais proximo que
 * existe e `tipo_escola` (publica/privada) combinado com
 * `dependencia_adm_escola` (federal/estadual/municipal/privada) — categorias,
 * nao instituicoes.
 *
 * A secao continua no menu, com esta tela, porque a alternativa seria esconder
 * a limitacao. Quem chega aqui procurando "a nota da minha escola" precisa
 * saber que o dado nao existe nesta base e para onde ir com a pergunta que
 * realmente tem.
 */

import { ExternalLink, School } from 'lucide-react';
import { Link } from 'react-router-dom';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import Botao from '@/components/ui/Botao';
import Cartao from '@/components/ui/Cartao';
import EstadoVazio from '@/components/ui/EstadoVazio';

export default function RelatoriosEscolares() {
  return (
    <>
      <CabecalhoPagina
        titulo="Relatorios por escola"
        descricao="Desempenho agregado por instituicao de ensino."
      />

      <div className="space-y-6">
        <EstadoVazio
          icone={School}
          titulo="Esta base nao tem dados por escola"
          fonteAusente="identificador de instituicao nas respostas de /v1/analise e /v1/comparacao; nao existe endpoint de escolas."
          descricao={
            <>
              <p>
                O Radar ENEM consulta os microdados do ENEM em nivel agregado e
                anonimizado. As respostas trazem distribuicoes de grupos, nunca o
                recorte de uma instituicao — o que impede tanto o ranking de escolas
                quanto a reidentificacao de participantes a partir de turmas pequenas.
              </p>
              <p className="mt-3">
                O mais proximo disponivel e comparar sua nota dentro de uma{' '}
                <strong className="font-semibold text-ink">categoria</strong> de escola:
                publica ou privada, e a dependencia administrativa (federal, estadual,
                municipal ou privada).
              </p>
            </>
          }
          acao={
            <>
              <Link to="/">
                <Botao>Comparar por tipo de escola</Botao>
              </Link>
              <Link to="/panorama">
                <Botao variante="secundario">Ver o que cada edicao publica</Botao>
              </Link>
            </>
          }
        />

        <Cartao
          titulo="Onde encontrar dados por escola"
          descricao="Fora desta ferramenta, o proprio INEP publica indicadores em nivel de instituicao."
        >
          <ul className="prosa space-y-3 text-sm text-ink-80">
            <li>
              <span className="font-medium text-ink">Censo Escolar</span> — matriculas,
              infraestrutura e docentes por escola, com codigo INEP.
            </li>
            <li>
              <span className="font-medium text-ink">IDEB</span> — indicador de
              qualidade por escola e por rede, a partir do SAEB e do fluxo escolar.
            </li>
            <li>
              <span className="font-medium text-ink">Indicadores educacionais</span> —
              adequacao da formacao docente, esforco docente e complexidade de gestao.
            </li>
          </ul>
          <p className="mt-4">
            <a
              href="https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos"
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-coorte underline-offset-4 hover:underline"
            >
              Dados abertos do INEP
              <ExternalLink size={14} aria-hidden="true" strokeWidth={2} />
              <span className="sr-only">(abre em nova aba)</span>
            </a>
          </p>
        </Cartao>
      </div>
    </>
  );
}
