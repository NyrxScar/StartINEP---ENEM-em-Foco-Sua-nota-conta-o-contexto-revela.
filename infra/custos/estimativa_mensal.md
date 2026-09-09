# Incremento 1 — Arquitetura, dimensionamento e custos

Entrega da disciplina de Computação em Nuvem (Aula 4). Todos os números abaixo foram
**medidos**, não estimados.

## Consumo medido do contêiner

```
docker build -f api/Dockerfile -t radar-enem-api .
docker run -d --rm -p 7860:7860 --name radar-teste radar-enem-api
docker stats radar-teste --no-stream
```

| Métrica | Medido |
|---|---|
| Tamanho da imagem | 460 MB |
| RAM em repouso, após servir requisição | 69,1 MiB |
| CPU em repouso | 0,24% |
| Latência do diagnóstico (recorte com N≈33 mil) | ~26 ms |
| Latência do diagnóstico (Brasil inteiro, N≈2,7 mi) | ~308 ms |
| Dado embarcado na imagem | 52,3 MB de Parquet, 13.077.671 linhas |

O consumo é baixo porque o trabalho pesado já aconteceu offline: a aplicação só lê
Parquet colunar e agrega. **Nada é carregado em memória na partida** — 69 MiB de RAM
para uma base de 13 milhões de linhas é a evidência disso.

## Modelo de implantação e de serviço

| Componente | Implantação | Serviço | Justificativa |
|---|---|---|---|
| Pipeline de ingestão | Privado / on-premises | — | Roda ~3× por edição. Provisionar computação elástica para um job esporádico é desperdício de OPEX. |
| API estatística | Nuvem pública | **PaaS/CaaS** | Entregamos a imagem Docker; a plataforma administra SO, runtime e disponibilidade. |
| Interface web | Nuvem pública | **PaaS** | Build e CDN gerenciados. |

O conjunto é uma **nuvem híbrida**: processamento pesado em ambiente privado
controlado, entrega em nuvem pública.

## Comparação de arquiteturas

Orçamento didático da Aula 4: R$ 300/mês.

| Opção | Configuração | Custo/mês | Veredito |
|---|---|---|---|
| **A — PaaS gratuito** (escolhida) | HF Spaces (2 vCPU, 16 GB) + Vercel Hobby | **R$ 0,00** | Cabe no orçamento com folga integral. Hiberna por inatividade. |
| B — IaaS VM pequena | 2 vCPU, 4 GB, R$ 0,20/h × 24h × 30d | R$ 144,00 | Cabe, mas paga por capacidade 60× maior que a medida (69 MiB). |
| C — IaaS VM maior | 4 vCPU, 8 GB, R$ 0,40/h × 24h × 30d | R$ 288,00 | Consome 96% do orçamento sem nenhuma justificativa de carga. |

**Decisão: opção A.** O dimensionamento medido (69 MiB de RAM, 0,24% de CPU) não
justifica nada além do tier gratuito. As opções B e C pagariam por ociosidade — o erro
que a Aula 4 chama de "recurso superdimensionado".

## Riscos da arquitetura escolhida

**Principal: hibernação por inatividade.** O tier gratuito do HF Spaces dorme e o
primeiro acesso leva 30–60 s. Diante da banca isso parece aplicação quebrada.
Mitigação: aquecer o serviço com no mínimo 15 minutos de antecedência antes de AV2 e
AV7, com responsável nomeado, e manter vídeo gravado + instância local como plano B.

**Secundário: dependência de plataforma.** Mitigado por a aplicação ser uma imagem
Docker reprodutível a partir do repositório — migrar para Render ou Fly.io é questão de
horas, não de reescrita.

## Responsabilidade compartilhada

| Segurança **DA** nuvem (provedor) | Segurança **NA** nuvem (equipe) |
|---|---|
| Data center, hardware, energia | Nenhum segredo versionado |
| Hipervisor e isolamento entre contêineres | CORS restrito por variável de ambiente |
| Disponibilidade do runtime gerenciado | Validação de entrada (nota 0–1000, recorte por whitelist) |
| Patches da plataforma | Conformidade do uso com o RIPD do INEP |

A aplicação **não coleta nem persiste dados pessoais**: notas e perfil são processados
na requisição e descartados. É a decisão que mais reduz a superfície de exposição.
