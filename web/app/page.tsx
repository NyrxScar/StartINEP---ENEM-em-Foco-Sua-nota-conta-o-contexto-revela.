"use client";

import { useState } from "react";
import { AREAS, ESCOLAS, REGIOES, RENDAS } from "./rotulos";

const API = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";
const EDICAO = 2023;

type Resultado = {
  nota: number;
  n: number;
  percentil: number | null;
  zscore: number | null;
  media: number | null;
  mediana: number | null;
  desvio_padrao: number | null;
  q1: number | null;
  q3: number | null;
  histograma: [number, number][];
  aviso: string | null;
};

type Resposta = {
  edicao: number;
  recorte_descricao: string;
  resultados: Record<string, Resultado>;
};

const nomeArea = (chave: string) =>
  AREAS.find((a) => a.chave === chave)?.nome ?? chave;

const num = (v: number | null, casas = 1) =>
  v === null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: casas });

/** Curva da população, com você marcado nela. */
function Distribuicao({ dados, nota }: { dados: [number, number][]; nota: number }) {
  if (dados.length === 0) return null;

  const L = 640;
  const A = 150;
  const pico = Math.max(...dados.map(([, n]) => n));
  const x = (valor: number) => (valor / 1000) * L;
  const larguraBarra = Math.max(L / 55, 3);
  const xVoce = x(nota);
  // Mantem o rótulo dentro do quadro nos extremos da escala.
  const ancora = xVoce > L - 90 ? "end" : xVoce < 60 ? "start" : "middle";

  return (
    <svg
      className="grafico"
      viewBox={`0 -18 ${L} ${A + 40}`}
      role="img"
      aria-label={`Distribuição das notas do recorte. Sua nota, ${num(nota)}, está marcada na curva.`}
    >
      {dados.map(([faixa, n]) => {
        const altura = (n / pico) * A;
        return (
          <rect
            key={faixa}
            className={`barra${faixa + 20 <= nota ? " abaixo" : ""}`}
            x={x(faixa)}
            y={A - altura}
            width={larguraBarra}
            height={altura}
          />
        );
      })}

      <line x1={0} y1={A} x2={L} y2={A} stroke="var(--linha)" strokeWidth={1} />

      {[0, 250, 500, 750, 1000].map((v) => (
        <text key={v} className="eixo" x={x(v)} y={A + 16} textAnchor={v === 0 ? "start" : v === 1000 ? "end" : "middle"}>
          {v}
        </text>
      ))}

      <line className="marcador" x1={xVoce} y1={-6} x2={xVoce} y2={A} />
      <text className="rotulo-marcador" x={xVoce} y={-10} textAnchor={ancora}>
        você · {num(nota)}
      </text>
    </svg>
  );
}

function Diagnostico({ area, r }: { area: string; r: Resultado }) {
  if (r.n === 0) {
    return (
      <section className="resultado">
        <p className="area">{nomeArea(area)}</p>
        <p className="frase">
          Não há participantes com esse perfil nesta edição. Tente um recorte mais amplo.
        </p>
      </section>
    );
  }

  return (
    <section className="resultado">
      <p className="area">{nomeArea(area)}</p>
      <p className="percentil">
        {num(r.percentil)}
        <span>%</span>
      </p>
      <p className="frase">
        dos <b>{r.n.toLocaleString("pt-BR")}</b> participantes desse grupo tiraram menos
        que você em {nomeArea(area).toLowerCase()}.
      </p>

      <Distribuicao dados={r.histograma} nota={r.nota} />

      <ul className="medidas">
        <li>média <b>{num(r.media)}</b></li>
        <li>mediana <b>{num(r.mediana)}</b></li>
        <li>desvio-padrão <b>{num(r.desvio_padrao)}</b></li>
        <li>quartis <b>{num(r.q1)}</b> e <b>{num(r.q3)}</b></li>
        <li>Z-score <b>{num(r.zscore, 2)}</b></li>
      </ul>

      {r.aviso && <p className="aviso">{r.aviso}</p>}
    </section>
  );
}

export default function Pagina() {
  const [notas, setNotas] = useState<Record<string, string>>({});
  const [recorte, setRecorte] = useState<Record<string, string>>({});
  const [resposta, setResposta] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const preenchidas = Object.entries(notas).filter(([, v]) => v.trim() !== "");

  async function consultar(evento: React.FormEvent) {
    evento.preventDefault();
    setCarregando(true);
    setErro(null);
    try {
      const r = await fetch(`${API}/diagnostico`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          edicao: EDICAO,
          notas: Object.fromEntries(preenchidas.map(([k, v]) => [k, Number(v)])),
          recorte: Object.fromEntries(
            Object.entries(recorte)
              .filter(([, v]) => v !== "")
              .map(([k, v]) => [k, k === "tipo_escola" ? Number(v) : v]),
          ),
        }),
      });
      if (!r.ok) throw new Error(`A consulta falhou (${r.status}). Confira as notas e tente de novo.`);
      setResposta(await r.json());
    } catch (e) {
      setResposta(null);
      setErro(e instanceof Error ? e.message : "Não foi possível falar com o servidor.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <main>
      <p className="marca-produto">Radar ENEM</p>
      <h1>Sua nota conta. O contexto revela.</h1>
      <p className="subtitulo">
        Uma nota isolada não diz muito. Informe a sua e escolha com quem comparar — a
        mesma nota muda de significado conforme o grupo.
      </p>

      <form onSubmit={consultar}>
        <fieldset>
          <legend>Suas notas no ENEM {EDICAO}</legend>
          <div className="notas">
            {AREAS.map(({ chave, nome }) => (
              <div key={chave}>
                <label htmlFor={chave}>{nome}</label>
                <input
                  id={chave}
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={1000}
                  step="0.1"
                  placeholder="0–1000"
                  value={notas[chave] ?? ""}
                  onChange={(e) => setNotas({ ...notas, [chave]: e.target.value })}
                />
              </div>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>Comparar com quem</legend>
          <div className="recortes">
            <div>
              <label htmlFor="regiao">Região</label>
              <select
                id="regiao"
                value={recorte.regiao ?? ""}
                onChange={(e) => setRecorte({ ...recorte, regiao: e.target.value })}
              >
                <option value="">Brasil inteiro</option>
                {REGIOES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="renda">Renda familiar</label>
              <select
                id="renda"
                value={recorte.renda_familiar ?? ""}
                onChange={(e) => setRecorte({ ...recorte, renda_familiar: e.target.value })}
              >
                <option value="">Qualquer renda</option>
                {RENDAS.map(([codigo, rotulo]) => (
                  <option key={codigo} value={codigo}>{rotulo}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="escola">Tipo de escola</label>
              <select
                id="escola"
                value={recorte.tipo_escola ?? ""}
                onChange={(e) => setRecorte({ ...recorte, tipo_escola: e.target.value })}
              >
                <option value="">Qualquer escola</option>
                {ESCOLAS.map(([codigo, rotulo]) => (
                  <option key={codigo} value={codigo}>{rotulo}</option>
                ))}
              </select>
            </div>
          </div>
        </fieldset>

        <button type="submit" disabled={carregando || preenchidas.length === 0}>
          {carregando ? "Calculando…" : "Ver meu diagnóstico"}
        </button>
      </form>

      {erro && <p className="erro">{erro}</p>}

      {resposta &&
        Object.entries(resposta.resultados).map(([area, r]) => (
          <Diagnostico key={area} area={area} r={r} />
        ))}

      <footer>
        <p>
          Percentil calculado sobre a distribuição real dos microdados do ENEM {EDICAO},
          publicados pelo INEP. Nada do que você digita é armazenado.
        </p>
        <p>
          O Z-score aparece como medida descritiva: as notas do ENEM vêm da TRI e não
          seguem distribuição normal, então ele não deve ser convertido em percentil.
        </p>
      </footer>
    </main>
  );
}
