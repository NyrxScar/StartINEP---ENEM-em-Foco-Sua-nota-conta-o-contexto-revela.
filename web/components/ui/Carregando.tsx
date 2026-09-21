/**
 * Estados de carregamento.
 *
 * `Esqueleto` desenha blocos com a forma aproximada do conteudo que vai chegar,
 * para que o layout nao salte quando ele chegar. `LinhaCarregando` e o aviso
 * textual, para acoes em que a espera precisa ser anunciada em vez de apenas
 * desenhada — o ponto pulsante e decorativo e o texto e que e lido.
 */

export function Esqueleto({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-[4px] bg-line/70 motion-reduce:animate-none ${className}`}
    />
  );
}

export function LinhaCarregando({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-60">
      <span
        aria-hidden="true"
        className="size-2 animate-pulse rounded-full bg-coorte motion-reduce:animate-none"
      />
      {children}
    </span>
  );
}
