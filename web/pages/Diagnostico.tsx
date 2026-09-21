/**
 * Diagnostico — a rota de entrada e o coracao do produto.
 *
 * Toda a maquinaria de estado vive em `PainelAnalise`; esta pagina so a
 * emoldura e oferece o dialogo que explica o que e um recorte. A explicacao
 * fica em um modal, e nao no corpo da pagina, porque e leitura opcional: quem
 * ja entendeu o conceito nao deve ter que passar por ele a cada visita.
 */

import { CircleHelp } from 'lucide-react';
import { useState } from 'react';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import PainelAnalise from '@/components/PainelAnalise';
import Botao from '@/components/ui/Botao';
import Modal from '@/components/ui/Modal';
import { ROTULOS_DIMENSAO } from '@/lib/tipos';

export default function Diagnostico() {
  const [explicando, setExplicando] = useState(false);

  return (
    <>
      <CabecalhoPagina
        titulo="Sua nota conta, o contexto revela"
        descricao="Informe sua nota do ENEM, escolha a area e um recorte comparavel para ver sua posicao na distribuicao. Os resultados sao sempre agregados: nenhuma resposta individual e exibida."
        acoes={
          <Botao
            variante="secundario"
            icone={<CircleHelp size={15} strokeWidth={1.75} />}
            onClick={() => setExplicando(true)}
          >
            O que e um recorte?
          </Botao>
        }
      />

      <PainelAnalise />

      <Modal
        aberto={explicando}
        aoFechar={() => setExplicando(false)}
        titulo="O que e um recorte"
        descricao="O grupo de pessoas com quem sua nota e comparada."
        rodape={
          <Botao onClick={() => setExplicando(false)}>Entendi</Botao>
        }
      >
        <div className="prosa space-y-3 text-ink-80">
          <p>
            Um percentil so significa alguma coisa quando voce sabe percentil{' '}
            <em>de quem</em>. Estar acima de 80% de todos os participantes do pais e
            estar acima de 80% de quem fez a prova nas mesmas condicoes que voce sao
            leituras diferentes — e a segunda costuma ser a util.
          </p>
          <p>
            O recorte e como voce monta esse grupo. Cada filtro aplicado estreita a
            comparacao, e todos valem ao mesmo tempo: escolher Nordeste e escola
            publica compara sua nota apenas com quem atende as duas condicoes.
          </p>
          <p>Os recortes disponiveis dependem do que cada edicao publicou:</p>
          <ul className="list-disc space-y-1 pl-5">
            {Object.values(ROTULOS_DIMENSAO).map((rotulo) => (
              <li key={rotulo}>{rotulo}</li>
            ))}
          </ul>
          <p>
            Duas regras que a ferramenta nao abre mao: nada e estimado quando a
            edicao nao publicou o dado, e grupos pequenos demais nao tem
            distribuicao divulgada, para que ninguem possa ser identificado a
            partir dos agregados.
          </p>
        </div>
      </Modal>
    </>
  );
}
