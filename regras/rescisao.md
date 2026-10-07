# Livro de regras – Verbas rescisórias

Este documento descreve, em linguagem jurídica, **todas** as regras que o motor de cálculo
(`tolaris/motor/rescisao.py`) aplica. Ele é a referência para a validação pelos advogados:
cada regra tem fórmula, fundamento e, quando houver, a decisão adotada em ponto controvertido.

Qualquer mudança de regra deve atualizar este documento **e** os testes (`tests/test_rescisao.py`).

---

## 1. Conceitos gerais

| Conceito | Regra adotada |
|---|---|
| **Desligamento** | Último dia efetivamente trabalhado. Se o aviso foi trabalhado, é o último dia do aviso. |
| **Remuneração para cálculo** | Salário do mês do desligamento + média mensal de variáveis (horas extras, comissões, adicionais habituais) informada pelo usuário. Usada no aviso, 13º e férias. |
| **Saldo de salário** | Usa só o salário (as variáveis do próprio mês devem ser lançadas à parte, em versão futura). |
| **Mês comercial** | Valores diários = mensal ÷ 30. |
| **Arredondamento** | Cada rubrica é arredondada ao centavo (meio para cima). Totais somam os valores já arredondados. |
| **Tempo de serviço** | Anos completos da admissão ao desligamento. Admissão em 29/02 faz aniversário em 28/02 nos anos não bissextos. |

## 2. Aviso prévio

- **Duração** (Lei nº 12.506/2011): 30 dias + 3 dias por ano completo de serviço, até 90 dias.
  O acréscimo só beneficia o empregado; no pedido de demissão o aviso é de 30 dias.
- **Contagem** (Súmula 380 do TST): exclui o dia do começo e inclui o do vencimento.
  A data projetada é `desligamento + dias de aviso indenizados`.
- **Projeção** (art. 487, § 1º, CLT; OJ 82 da SDI-1): o período do aviso indenizado conta como
  tempo de serviço para 13º e férias.

| Modalidade | Aviso devido | Valor |
|---|---|---|
| Sem justa causa / rescisão indireta | Indenizado: todos os dias. Trabalhado: 30 dias cumpridos e os dias excedentes indenizados. | remuneração ÷ 30 × dias |
| Acordo (art. 484-A) | Metade do aviso indenizado (art. 484-A, I, a) | remuneração ÷ 30 × dias × 50% |
| Culpa recíproca | Metade (Súmula 14 do TST) | remuneração ÷ 30 × dias × 50% |
| Pedido de demissão | Não cumprido: desconto de 30 dias de salário (art. 487, § 2º). Trabalhado ou dispensado pelo empregador: nada a pagar ou descontar. | salário |
| Justa causa | Não há aviso. | – |

## 3. Saldo de salário

`salário ÷ 30 × dias`, em que dias = do 1º dia do mês (ou da admissão, se no mesmo mês) até o
desligamento, limitado a 30, menos as faltas injustificadas do mês. Se o empregado trabalhou o
mês inteiro (do dia 1º ao último dia do mês), conta 30 dias, inclusive em fevereiro.

## 4. 13º salário proporcional

- **Avos** (Lei nº 4.090/1962, art. 1º, § 2º): cada mês do calendário em que o vínculo durou
  15 dias ou mais conta 1/12. A contagem começa em 1º de janeiro **ou na admissão**, se posterior.
- Vai até a **data projetada** do aviso. Se a projeção atravessar o ano, gera uma rubrica para
  cada ano.
- Valor: `remuneração ÷ 12 × avos`.
- Devido no pedido de demissão (Súmula 157 do TST). Não devido na justa causa. Metade na culpa
  recíproca (Súmula 14 do TST).
- O adiantamento (1ª parcela) já pago é descontado (campo "13º já pago").

## 5. Férias

**Período aquisitivo**: 12 meses contados da admissão. **Período concessivo**: os 12 meses seguintes.

- **Vencidas** (art. 146, caput): o usuário informa quantos períodos completos não foram gozados.
  O sistema considera os mais recentes. São devidas em qualquer modalidade, inclusive justa causa.
- **Em dobro** (art. 137): quando o período concessivo terminou antes do desligamento.
- **Integrais pela projeção**: se a projeção do aviso completar um período aquisitivo, ele é pago
  como férias integrais simples.
- **Proporcionais** (art. 146, parágrafo único): avos do período aquisitivo em curso até a data
  projetada, contando como mês a fração de 15 dias ou mais. Valor:
  `remuneração ÷ 12 × avos × (dias de direito ÷ 30)`.
  - Dias de direito pelas faltas injustificadas do período (art. 130): até 5 → 30 dias; 6 a 14 → 24;
    15 a 23 → 18; 24 a 32 → 12; mais de 32 → perde o direito.
  - Devidas no pedido de demissão mesmo com menos de 1 ano (Súmula 261 do TST).
  - Não devidas na justa causa (Súmula 171 do TST). Metade na culpa recíproca (Súmula 14).
- **1/3 constitucional** (art. 7º, XVII, CF; Súmula 328 do TST) sobre cada rubrica de férias,
  inclusive sobre a dobra.

## 6. FGTS

- **Depósito rescisório** (art. 15 da Lei nº 8.036/1990): 8% sobre saldo de salário + 13º + aviso
  prévio indenizado (Súmula 305 do TST). Não incide sobre férias indenizadas (OJ 195 da SDI-1).
- **Multa**: 40% na dispensa sem justa causa e na rescisão indireta (art. 18, § 1º); 20% no acordo
  (art. 484-A, I, b) e na culpa recíproca (art. 18, § 2º; Súmula 14).
- **Base da multa**: saldo para fins rescisórios + depósito rescisório.
  - Se o usuário informar o saldo do extrato, ele é usado.
  - Se não, o sistema **estima**: 8% do salário de cada mês (do mês da admissão ao mês anterior ao
    desligamento, proporcional no mês da admissão) + 8% do 13º de cada ano anterior ao desligamento.
    A estimativa não inclui juros e atualização (JAM) nem variáveis, e é sinalizada com um alerta.
- O FGTS é exibido separado do líquido, porque é depositado na conta vinculada.

## 7. Multas

- **Art. 477, § 8º**: um salário quando as verbas forem pagas fora do prazo de 10 dias (§ 6º).
  Aplicada quando o usuário marca a opção.
- **Art. 467**: 50% sobre saldo de salário, aviso, 13º, férias + 1/3 e multa do FGTS.
  Aplicada quando o usuário marca a opção.

## 8. Descontos

- **INSS** (Lei nº 8.212/1991): tabela vigente no mês do desligamento.
  - Sobre o saldo de salário, e em separado sobre o 13º (art. 28, § 7º).
  - Não incide sobre aviso indenizado, férias indenizadas + 1/3 e multas.
  - Até 02/2020, alíquota única sobre o total; desde 03/2020, progressiva por faixa (EC nº 103/2019).
- **IRRF** (Lei nº 7.713/1988): tabela vigente no mês do desligamento.
  - **Saldo de salário**: deduz INSS + dependentes, ou o desconto simplificado quando for maior
    (a partir de 05/2023).
  - **13º**: tributação exclusiva (art. 26), deduz o INSS do 13º + dependentes.
  - A partir de 2026, aplica a redução da Lei nº 15.270/2025, calculada sobre o rendimento
    tributável: até R$ 5.000,00 reduz até R$ 312,89; de R$ 5.000,01 a R$ 7.350,00 reduz
    R$ 978,62 − 0,133145 × rendimento; limitada ao imposto calculado. Vale também para o 13º.
  - Férias indenizadas + 1/3 e aviso indenizado não são tributados.
- **Outros**: 13º já pago, outros descontos informados.
- Se os descontos superarem os proventos, o sistema alerta sobre o limite do art. 477, § 5º.

## 9. Tabelas

Ficam em `tolaris/tabelas/*.json`, organizadas por **data de vigência**, com a fonte normativa.
Cobertura atual: INSS e salário mínimo desde 01/2019; IRRF desde 04/2015 (o cálculo exige datas a
partir de 2019). Se a data for de um ano sem tabela cadastrada, o sistema avisa.

---

## Pontos para validação pelos advogados

Estes são os pontos em que há divergência na prática ou na jurisprudência, ou em que adotamos uma
simplificação. A opinião de vocês define se mantemos a regra.

1. **Acordo (484-A) e culpa recíproca**: a projeção do aviso para 13º e férias usa os dias
   **integrais** do aviso, embora só metade seja paga. Está correto?
2. **Aviso trabalhado com mais de 30 dias**: o sistema considera 30 dias trabalhados e indeniza os
   dias da proporcionalidade, projetando só esses dias. É a prática de vocês?
3. **Desconto do aviso não cumprido** no pedido de demissão: usa o salário-base, sem variáveis.
4. **Multa do art. 467**: incluímos a multa de 40% do FGTS na base. Mantemos?
5. **IRRF do 13º**: não aplicamos o desconto simplificado no 13º (só deduções legais). Confere?
6. **INSS sobre o 13º indenizado** (avos da projeção do aviso): o sistema faz incidir. Mantemos?
7. **Férias vencidas**: sempre 30 dias (não consideramos faltas de períodos anteriores).
8. **Saldo de salário em mês completo**: 30 dias, inclusive em fevereiro e em meses de 31 dias.
9. **Faltas** não reduzem os avos de 13º (só o critério dos 15 dias por mês).
10. **Estimativa do FGTS**: suficiente para a fase de petição inicial, ou devemos exigir o extrato?

## Fora do escopo desta versão

Contrato por prazo determinado (arts. 479 e 480), aprendiz (FGTS 2%), estabilidades, horas extras
e adicionais com reflexos, prescrição, correção monetária e juros (ADC 58 / Lei nº 14.905/2024),
honorários, contribuição patronal e IRRF pelo regime de rendimentos recebidos acumuladamente (RRA).
Estão previstos nas próximas etapas.
