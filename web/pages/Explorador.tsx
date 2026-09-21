/**
 * Explorador de dados — secao sem fonte de dados.
 *
 * Um explorador precisa de linhas para percorrer, e a API nao devolve linha
 * nenhuma: `POST /v1/analise` responde com histograma, quantis e percentil de
 * um recorte, e nada em todo o contrato retorna registros de participantes. Isso
 * nao e uma lacuna a preencher depois — e a decisao de projeto que mantem a base
 * anonimizada, junto com o limiar que suprime grupos pequenos.
 *
 * A tela diz isso e aponta para as consultas que existem de fato.
 */

import { Database, FileJson } from 'lucide-react';
import { Link } from 'react-router-dom';

import CabecalhoPagina from '@/components/CabecalhoPagina';
import Botao from '@/components/ui/Botao';
import Cartao from '@/components/ui/Cartao';
import EstadoVazio from '@/components/ui/EstadoVazio';

/** As consultas que a API realmente oferece. */
const CONSULTAS = [
  {
    rota: 'POST /v1/analise',
    o_que: 'Distribuicao, quantis e percentil de uma nota dentro de um recorte.',
    onde: { para: '/', rotulo: 'Diagnostico' },
  },
  {
    rota: 'POST /v1/comparacao',
    o_que: 'O mesmo calculo em varias edicoes, com o motivo de cada omissao.',
    onde: { para: '/comparativo', rotulo: 'Comparar edicoes' },
  },
  {
    rota: 'GET /v1/edicoes',
    o_que: 'Edicoes carregadas, data de carga e capacidade de cada uma.',
    onde: { para: '/panorama', rotulo: 'Panorama ENEM' },
  },
];

export default function Explorador() {
  return (
    <>
      <CabecalhoPagina
        titulo="Explorador de dados"
        descricao="Consulta livre sobre a base de microdados."
      />

      <div className="space-y-6">
        <EstadoVazio
          icone={Database}
          titulo="Nao ha linhas para explorar"
          fonteAusente="endpoint de consulta tabular ou de registros; o contrato da API devolve apenas agregados."
          descricao={
            <>
              <p>
                Um explorador percorre registros, e esta API nao devolve nenhum. Toda
                resposta e um agregado — histograma, quantis, percentil, tamanho de
                grupo — calculado no servidor sobre os microdados.
              </p>
              <p className="mt-3">
                A restricao e deliberada e trabalha junto com o limiar de divulgacao,
                que suprime resultados de grupos pequenos: sem linhas e sem grupos
                minusculos, nao ha como reconstruir um participante a partir de
                consultas sucessivas.
              </p>
            </>
          }
          acao={
            <Link to="/">
              <Botao>Ir para o diagnostico</Botao>
            </Link>
          }
        />

        <Cartao
          titulo="Consultas disponiveis"
          descricao="O que a API responde hoje, e onde cada uma esta na interface."
        >
          <ul className="space-y-4">
            {CONSULTAS.map((consulta) => (
              <li
                key={consulta.rota}
                className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium text-ink">
                    <FileJson
                      size={15}
                      aria-hidden="true"
                      strokeWidth={1.75}
                      className="shrink-0 text-ink-40"
                    />
                    <code className="text-[13px]">{consulta.rota}</code>
                  </p>
                  <p className="prosa mt-1 pl-6 text-sm text-ink-60">{consulta.o_que}</p>
                </div>
                <Link to={consulta.onde.para} className="shrink-0">
                  <Botao variante="discreto">{consulta.onde.rotulo}</Botao>
                </Link>
              </li>
            ))}
          </ul>
        </Cartao>
      </div>
    </>
  );
}
