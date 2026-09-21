/**
 * Formatadores pt-BR compartilhados.
 *
 * Existiam tres copias destes `Intl.NumberFormat` espalhadas pelos componentes,
 * com pequenas divergencias de casas decimais entre elas — o mesmo percentil
 * podia aparecer como "72,4" em um lugar e "72,40" em outro. Centralizar
 * garante que um numero tenha uma unica grafia em toda a interface, e fixa o
 * locale explicitamente para que o resultado nao dependa da maquina que roda.
 */

/** Contagens e tamanhos amostrais: inteiros com separador de milhar. */
export const FORMATO_INTEIRO = new Intl.NumberFormat('pt-BR', {
  maximumFractionDigits: 0,
});

/** Notas e percentis: sempre uma casa decimal, para largura estavel. */
export const FORMATO_UMA_CASA = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Anos de edicao: sem separador de milhar ("2023", nunca "2.023"). */
export const FORMATO_EDICAO = new Intl.NumberFormat('pt-BR', { useGrouping: false });

/** Data e hora de carga ("12 de marco de 2025 as 14:32"). */
export const FORMATO_DATA_HORA = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'long',
  timeStyle: 'short',
});

/** Junta rotulos em uma enumeracao legivel: "A", "A e B", "A, B e C". */
export function enumerar(rotulos: string[]): string {
  if (rotulos.length <= 1) return rotulos.join('');
  return `${rotulos.slice(0, -1).join(', ')} e ${rotulos[rotulos.length - 1] ?? ''}`;
}

/** Enumeracao de edicoes, ja formatadas: "2022, 2023 e 2025". */
export function enumerarEdicoes(edicoes: number[]): string {
  return enumerar(edicoes.map((edicao) => FORMATO_EDICAO.format(edicao)));
}
