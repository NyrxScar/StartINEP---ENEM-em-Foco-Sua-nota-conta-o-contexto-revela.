/**
 * `Rodape` — procedencia e limites do produto.
 *
 * Nao e uma faixa de links institucionais: em um produto que publica numeros
 * sobre educacao publica, o rodape e onde cabe dizer de onde vem o dado, o que
 * a ferramenta nao faz e sob que licenca ela existe. As duas primeiras colunas
 * sao conteudo; a terceira e navegacao.
 */

import { Link } from 'react-router-dom';

import { NAVEGACAO } from '@/components/layout/navegacao';

const ANO = new Date().getFullYear();

export default function Rodape() {
  return (
    <footer className="mt-auto border-t border-line bg-surface">
      <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-3">
        <div>
          <p className="font-display text-[15px] font-semibold text-ink">Radar ENEM</p>
          <p className="prosa mt-2 text-sm leading-relaxed text-ink-60">
            Sua nota conta, o contexto revela. Todos os numeros sao agregados a partir
            dos microdados publicos do ENEM; nenhuma resposta individual e exibida ou
            armazenada. A consulta por escola devolve agregados da instituicao, sujeitos
            ao mesmo limiar de divulgacao.
          </p>
        </div>

        <div>
          <h2 className="text-[13px] font-semibold text-ink">O que esta ferramenta nao faz</h2>
          <ul className="prosa mt-2 space-y-1.5 text-sm text-ink-60">
            <li>Nao identifica participantes.</li>
            <li>Nao publica ranking de escolas.</li>
            <li>Nao estima o que uma edicao nao publicou.</li>
            <li>Nao exibe grupos pequenos demais para serem divulgados com seguranca.</li>
          </ul>
        </div>

        <div>
          <h2 className="text-[13px] font-semibold text-ink">Secoes</h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            {NAVEGACAO.map((item) => (
              <li key={item.para}>
                <Link
                  to={item.para}
                  className="text-ink-60 underline-offset-4 transition-colors hover:text-ink hover:underline"
                >
                  {item.rotulo}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-line px-4 py-4 sm:px-6">
        <p className="mx-auto max-w-6xl text-xs text-ink-40">
          StartINEP {ANO}. Fonte dos dados: microdados do ENEM, INEP/MEC, sob Licenca
          Aberta. Projeto academico, sem vinculo institucional com o INEP.
        </p>
      </div>
    </footer>
  );
}
