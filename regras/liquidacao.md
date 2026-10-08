# Livro de regras – Liquidação de sentença

Regras aplicadas por `tolaris/motor/liquidacao.py`. Toda mudança deve atualizar este documento e
`tests/test_liquidacao.py`.

A liquidação segue o título executivo (art. 879, § 1º, CLT): o sistema usa os critérios padrão
descritos aqui e nos outros livros de regras, e o formulário permite trocar os que a sentença
fixou de outro modo.

---

## Etapa 1

### 1. Verbas deferidas

- **Verbas rescisórias** (regras em `rescisao.md`): o advogado marca só os grupos deferidos
  (saldo de salário, aviso prévio, 13º, férias + 1/3, multas dos arts. 477 e 467, FGTS e multa).
  INSS e IR da rescisão são descartados e apurados de novo pelas regras da liquidação. O 13º já
  pago e os outros descontos da rescisão entram como deduções.
- **Horas extras, adicional noturno, insalubridade e periculosidade** (regras em
  `horas_extras.md`), com reflexos e FGTS.
- As duas partes podem entrar no mesmo cálculo. O contrato (datas, salário, modalidade) é um só.

### 2. Parâmetros da sentença

Além dos parâmetros de cada cálculo (divisor, adicionais, prescrição, juros antes do
ajuizamento), a sentença pode fixar:

| Parâmetro | Opções | Padrão |
|---|---|---|
| DSR majorado nos reflexos (OJ 394 da SDI-1) | a partir de 04/2023 (IRR de 2023) / nunca / todo o período | a partir de 04/2023 |
| Base da insalubridade | salário mínimo ou valor fixado (sentença ou norma coletiva) | salário mínimo |
| Prescrição quinquenal | aplicada ou não, com interrupção | aplicada |

### 3. Dedução dos valores pagos

- Valores já pagos sob o mesmo título são informados com competência, valor e natureza
  (salarial, 13º ou indenizatória).
- **Critério global** (OJ 415 da SDI-1 do TST): a dedução não fica limitada ao mês em que o valor
  foi pago.
- A dedução é atualizada pelos mesmos índices das verbas, a partir da sua competência.
- Dedução salarial ou de 13º reduz a base do INSS e do IR daquela competência.
- Se o FGTS do valor pago já foi depositado, o sistema também deduz 8% (e a multa, conforme a
  modalidade).

### 4. Correção monetária e juros

Pelas regras de `atualizacao.md`, até a **data da liquidação**. A data do ajuizamento é
obrigatória (início da fase judicial).

### 5. INSS (Súmula 368, IV e V, do TST)

**Regime de competência.** A contribuição de cada mês é calculada pela tabela vigente naquele
mês. O 13º é calculado em separado (art. 28, § 7º, Lei nº 8.212/1991).

| | Incide |
|---|---|
| Horas extras, DSR, adicionais, saldo de salário, 13º | Sim |
| Aviso prévio indenizado, férias indenizadas + 1/3, multas, FGTS | Não |

**Tabelas**: do INSS, de 2008 em diante (`tolaris/tabelas/inss.json`). Em 2010, a tabela da Portaria
nº 333/2010 é aplicada a partir da competência 06/2010 (como na tabela auxiliar do Sefip); em 2011,
a da Portaria nº 407/2011 desde a competência 01/2011 (art. 7º).

**Cota do empregado.** Por padrão, o salário já pago no mês entra na base, para respeitar as
faixas e o teto:

`INSS devido = INSS(salário pago + verbas deferidas) − INSS(salário pago)`

- Salário pago = salário do histórico × parte do mês trabalhada.
- 13º pago = salário de dezembro (ou do desligamento) × avos ÷ 12.
- Se a sentença deferiu o saldo de salário ou o 13º rescisório, o salário pago daquele mês (ou
  daquele 13º) é zero.
- O formulário permite desligar essa soma: aí o INSS é calculado só sobre as verbas deferidas.

**Cota da empresa.** 20% (art. 22, I) + RAT ajustado pelo FAP (art. 22, II) + terceiros, sobre as
verbas deferidas, sem teto. Empresa do Simples Nacional: sem cota patronal (LC nº 123/2006, art.
13). Anexo IV: a empresa paga os 20% e o RAT, mas não terceiros (art. 18, § 5º-C); informe como
empresa comum com terceiros = 0%.

**Acréscimos.**
- Competências a partir de 03/2009 (trabalho a partir de 05/03/2009, Súmula 368, V): juros SELIC
  desde o mês seguinte ao vencimento (dia 20 do mês seguinte à competência) até o mês anterior à
  liquidação, mais 1% no mês da liquidação (art. 35 da Lei nº 8.212/1991; art. 61, § 3º, da Lei nº
  9.430/1996).
- Competências anteriores (Súmula 368, IV: o fato gerador é o pagamento): sem juros até a
  liquidação. *Simplificação*: o valor histórico é atualizado pelos mesmos índices trabalhistas das
  verbas e esse acréscimo fica com a reclamada.
- A **multa de mora** só incide depois de vencido o prazo da citação para pagamento (Súmula 368,
  V) e não entra na liquidação.

**Responsabilidade.** O reclamante paga só a cota-parte histórica, descontada do crédito. Os
juros sobre as duas cotas ficam com a reclamada, que deu causa ao atraso.

### 6. Imposto de renda

Súmula 368, VI, do TST.

- **Rendimentos tributáveis**: verbas salariais (horas extras, DSR, adicionais, saldo de salário,
  13º) mais a correção monetária delas, competência a competência. Férias indenizadas + 1/3, aviso
  indenizado, multas e FGTS não são tributáveis.
- **Juros não são tributáveis** (OJ 400 da SDI-1 do TST; Tema 808 do STF). O sistema trata como
  juros a TR, a taxa legal e **toda a SELIC** da fase judicial (é o que o STF disse na ADC 58 e o
  que os TRTs parametrizam no PJe-Calc).
- **Verbas de anos anteriores ao da liquidação: rendimentos recebidos acumuladamente** (art. 12-A
  da Lei nº 7.713/1988; arts. 36 e 37 da IN RFB nº 1.500/2014):
  - tabela mensal vigente na data da liquidação, com os limites das faixas e a parcela a deduzir
    multiplicados pelo número de meses (NM);
  - NM = meses distintos das verbas tributáveis + 1 mês para o 13º de cada ano (art. 37, § 1º);
  - dedução: só o INSS do reclamante (o art. 12-A não prevê dependentes nem o desconto
    simplificado);
  - a partir de 2026, redução da Lei nº 15.270/2025 com os limites (R$ 5.000 e R$ 7.350) e a
    redução multiplicados por NM (ver ponto de validação).
- **Verbas do próprio ano da liquidação** (art. 12-B): tabela mensal comum sobre o total, com
  dedução do INSS e a redução da Lei nº 15.270/2025, sem desconto simplificado.
- Fora desta versão: dedução de pensão alimentícia e dos honorários contratuais pagos pelo
  reclamante (§§ 2º e 3º do art. 12-A).

### 7. Honorários de sucumbência (art. 791-A, CLT)

- **Devidos pela reclamada**: percentual (5% a 15%) sobre o valor que resultar da liquidação:
  verbas atualizadas + FGTS, sem deduzir INSS e IR (OJ 348 da SDI-1).
- **Devidos pelo reclamante** (sucumbência parcial): percentual sobre o valor informado dos
  pedidos rejeitados. São descontados do crédito, salvo se o reclamante tem justiça gratuita: aí a
  exigibilidade fica suspensa (§ 4º; ADI 5766 do STF) e o valor só aparece como informação.

### 8. Custas (art. 789, CLT)

2% sobre a condenação (verbas atualizadas + FGTS), com mínimo de R$ 10,64 e máximo de 4 vezes o
teto dos benefícios do RGPS. Quando a sentença fixou as custas, informe o valor.

### 9. Resumo da liquidação

| Crédito do reclamante | Recolhimentos e despesas da reclamada |
|---|---|
| Verbas atualizadas (sem FGTS) | FGTS + multa, a depositar na conta vinculada (Tema 68 do TST) |
| (−) INSS do reclamante | INSS do reclamante e da reclamada, com acréscimos |
| (−) IR | IR |
| (−) honorários do reclamante, se exigíveis | Honorários e custas |
| **= Líquido do reclamante** | **Total devido pela reclamada** |

`Total devido pela reclamada = verbas atualizadas + FGTS + INSS da empresa + acréscimos do INSS +
honorários + custas` (o INSS do reclamante, o IR e os honorários do reclamante já estão dentro das
verbas, pois são retidos do crédito).

---

## Pontos para validação pelos advogados

1. **Salário pago na base do INSS**: o sistema soma o salário do histórico para aplicar as faixas
   e o teto. Os advogados conferem assim, ou calculam só sobre as diferenças?
2. **Juros do INSS da cota do empregado** a cargo da reclamada.
3. **SELIC inteira como juros** para o IR (não tributável).
4. **Redução da Lei nº 15.270/2025 no RRA**: a IN RFB nº 2.299/2025 manda observar a tabela de
   redução, mas não deixa claro se os limites são multiplicados por NM. O sistema multiplica.
5. **Verbas do ano da liquidação** (art. 12-B): calculadas em separado pela tabela mensal, sem
   somar outros rendimentos do mês e sem desconto simplificado.
6. **Dedução de valores pagos** atualizada desde a competência do pagamento.
7. **Honorários sobre o FGTS**: incluído na base (o FGTS faz parte da condenação).
8. **Reflexo em férias** sempre como férias indenizadas (sem INSS e IR). Férias gozadas no
   curso do contrato seriam salariais.
