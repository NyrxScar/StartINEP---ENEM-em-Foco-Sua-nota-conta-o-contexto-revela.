// Rotulos legiveis para os codigos do INEP. As faixas de renda do questionario
// socioeconomico (Q006) sao definidas em multiplos do salario minimo do ano da
// edicao, entao os rotulos falam em salarios minimos em vez de valores em reais --
// um valor fixo em reais estaria errado para pelo menos uma das edicoes.
export const AREAS = [
  { chave: "mt", nome: "Matemática" },
  { chave: "lc", nome: "Linguagens" },
  { chave: "ch", nome: "Humanas" },
  { chave: "cn", nome: "Natureza" },
  { chave: "redacao", nome: "Redação" },
] as const;

export const REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];

export const RENDAS: Array<[string, string]> = [
  ["A", "Nenhuma renda"],
  ["B", "Até 1 salário mínimo"],
  ["C", "1 a 1,5 salário"],
  ["D", "1,5 a 2 salários"],
  ["E", "2 a 2,5 salários"],
  ["F", "2,5 a 3 salários"],
  ["G", "3 a 4 salários"],
  ["H", "4 a 5 salários"],
  ["I", "5 a 6 salários"],
  ["J", "6 a 7 salários"],
  ["K", "7 a 8 salários"],
  ["L", "8 a 9 salários"],
  ["M", "9 a 10 salários"],
  ["N", "10 a 12 salários"],
  ["O", "12 a 15 salários"],
  ["P", "15 a 20 salários"],
  ["Q", "Mais de 20 salários"],
];

export const ESCOLAS: Array<[string, string]> = [
  ["2", "Escola pública"],
  ["3", "Escola privada"],
];
