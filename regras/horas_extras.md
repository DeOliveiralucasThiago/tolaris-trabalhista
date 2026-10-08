# Livro de regras – Horas extras, adicional noturno, insalubridade e periculosidade

Regras aplicadas por `tolaris/motor/horas_extras.py`. O cálculo é **mês a mês** (competência):
cada mês tem o seu salário, valor-hora, quantidade de horas, DSR e adicional, e todos aparecem no
demonstrativo mensal do resultado.

Toda mudança de regra deve atualizar este documento **e** `tests/test_horas_extras.py`.

---

## 1. Período calculado e prescrição

- **Prescrição quinquenal** (art. 7º, XXIX, CF; Súmula 308, I, do TST): são excluídas as parcelas
  anteriores a 5 anos da data do ajuizamento (ou da data prevista de distribuição). O primeiro mês
  é proporcional aos dias a partir do marco.
- **Prescrição bienal**: se a ação for ajuizada mais de 2 anos após o fim do contrato, o sistema
  recusa o cálculo.
- **Interrupção da prescrição** (Súmula 268 e OJ 392 da SDI-1 do TST): se houve ação anterior
  arquivada ou protesto judicial, informe a data do ajuizamento deles. Os 5 anos passam a ser
  contados dessa data, e o ajuizamento atual pode estar a mais de 2 anos do fim do contrato. O
  sistema exige que a ação anterior/protesto esteja dentro do biênio e seja anterior a esta ação, e
  alerta que a interrupção vale só para pedidos idênticos e que esta ação deve ter sido ajuizada em
  até 2 anos do fim da anterior (esses dois pontos o sistema não tem como conferir).
- Sem data de ajuizamento, calcula o contrato inteiro e emite um alerta.
- **Mês parcial** (admissão, desligamento, marco prescricional ou período de jornada que começa ou
  termina no meio do mês): fração = dias ÷ 30; mês completo = 1.

## 2. Entrada: média mensal de horas por período

O advogado informa, por período, a **média mensal de horas devidas e não pagas**:
horas extras com o 1º adicional, com o 2º adicional e horas noturnas (de relógio). Períodos em
branco valem para o contrato inteiro; trechos fora do contrato são descartados com alerta.

## 3. Valor-hora

`valor-hora = (salário do mês + adicional de insalubridade/periculosidade do mês) ÷ divisor`

- Divisor: 220 (44 h), 200 (40 h, Súmula 431 do TST), 180 (36 h) ou 150 (30 h).
- O adicional de insalubridade ou periculosidade integra a base (Súmulas 132 e 139 do TST), seja ele
  pedido na ação ou já pago ("já era pago").
- Salário do mês: histórico salarial, se informado; senão, o salário atual.

## 4. Parcelas mensais

| Parcela | Fórmula mensal | Fundamento |
|---|---|---|
| Horas extras | horas × valor-hora × (1 + adicional) | Art. 7º, XVI, CF; art. 59 CLT |
| Adicional noturno | horas noturnas × (60 ÷ 52,5, se hora reduzida) × valor-hora × 20% | Art. 73 CLT |
| Insalubridade | grau (10/20/40%) × salário mínimo vigente no mês (ou base fixada na sentença/norma coletiva) × fração | Art. 192 CLT; SV 4 do STF |
| Periculosidade | 30% × salário do mês × fração | Art. 193, § 1º, CLT; Súmula 191 do TST |

Os adicionais de insalubridade e periculosidade não se acumulam (art. 193, § 2º, CLT): o
formulário só permite escolher um.

## 5. Reflexos

### DSR (Lei nº 605/1949; Súmula 172 do TST)
Em cada mês: `valor das horas ÷ dias úteis × (domingos + feriados)`.
- Feriados: **somente os nacionais** (1/1, 21/4, 1/5, 7/9, 12/10, 2/11, 15/11, 20/11 a partir de
  2024 e 25/12). Sábado conta como dia útil.
- Aplica-se a horas extras e adicional noturno. Insalubridade e periculosidade são mensais e já
  remuneram o repouso (OJ 103 da SDI-1): sem DSR.

### 13º, férias + 1/3 e aviso prévio — Súmula 347 do TST
Os reflexos usam a **quantidade de horas** do período multiplicada pelo **valor-hora da época do
pagamento**:

- **13º salário** de cada ano: `Σ horas do ano × valor-hora de dezembro (ou do desligamento) × (1 + adicional) ÷ 12`.
- **Férias + 1/3** de cada período aquisitivo: `Σ horas do período × valor-hora do fim do período (ou do desligamento) × (1 + adicional) ÷ 12 × 4/3`.
- **Aviso prévio indenizado**: `média das horas dos últimos 12 meses × valor-hora do desligamento × (1 + adicional) × dias de aviso ÷ 30`.
- Insalubridade/periculosidade: mesma lógica, com a quantidade de meses e o valor do adicional na época.

**DSR nos reflexos (OJ 394 da SDI-1, redação dada pelo TST no IRR de 2023):** a partir das horas
extras trabalhadas em 20/03/2023, as horas de DSR também entram no 13º, nas férias e no aviso.
Antes disso, não entram (para evitar o *bis in idem* da redação antiga).
*Simplificação:* o sistema aplica a regra nova a partir da competência **abril/2023**.
Se a sentença fixou outro critério, o formulário permite escolher "não repercute" (redação
anterior) ou "repercute em todo o período".

**Projeção do aviso indenizado** (art. 487, § 1º, CLT): os meses projetados entram no 13º e nas
férias com a média de horas dos últimos 12 meses.

**Modalidade de extinção:**
- Justa causa: sem reflexo no 13º do último ano, nas férias do período incompleto e no aviso.
- Culpa recíproca: metade no 13º do último ano, nas férias do período incompleto e no aviso.
- Acordo (art. 484-A): metade no aviso.

### FGTS
8% sobre parcela + DSR + 13º + aviso (não incide sobre férias indenizadas, OJ 195 da SDI-1;
Súmula 63 do TST). Multa de 40% (dispensa sem justa causa e rescisão indireta) ou 20% (acordo e
culpa recíproca) sobre esse FGTS.

## 6. Valor por pedido

Cada pedido (horas extras, adicional noturno, insalubridade/periculosidade) é apresentado com o
valor principal + reflexos + FGTS, para a liquidação dos pedidos na petição inicial
(art. 840, § 1º, CLT). Os valores são brutos, sem correção monetária, juros, INSS e IR.

---

## Pontos para validação pelos advogados

1. **Feriados**: só os nacionais. Devemos permitir informar feriados estaduais e municipais?
2. **Marco da OJ 394**: aplicamos a partir da competência abril/2023 (e não de 20/03/2023).
3. **Reflexo no 13º e nas férias** pela soma das horas ÷ 12 (média duodecimal), com valor-hora da
   época do pagamento (Súmula 347). Os advogados usam outro critério (por exemplo, média dos
   valores)?
4. **Aviso prévio**: média dos últimos 12 meses (ou do período trabalhado, se menor).
5. **Mês parcial**: horas proporcionais a dias ÷ 30.
6. **Férias**: sempre simples (não há dobra no reflexo, mesmo se as férias do período foram
   pagas em dobro).
7. **FGTS sobre o reflexo em férias gozadas**: não calculamos. Precisa?
8. **Adicional noturno**: só o adicional sobre horas noturnas não pagas; não há "hora extra
   noturna" nem prorrogação da jornada noturna (Súmula 60, II, do TST). É uma lacuna relevante?
9. **Interrupção da prescrição**: o novo prazo bienal corre do arquivamento ou trânsito em julgado da
   ação anterior. O sistema não pede essa data e só alerta. Devemos pedir e conferir?
10. **Insalubridade**: base no salário mínimo. Algumas categorias têm base maior em norma coletiva.

## Fora do escopo desta versão

Prescrição contra menor de 18 anos (art. 440 da CLT), cartão de ponto e cálculo da jornada dia a dia, intervalo intrajornada e interjornada, horas in
itinere, sobreaviso, compensação de horas já pagas, base de cálculo por norma coletiva,
correção monetária e juros (próxima etapa).
