# Livro de regras – Correção monetária e juros

Regras aplicadas por `tolaris/motor/atualizacao.py`. Toda mudança deve atualizar este documento
e `tests/test_atualizacao.py`.

## 1. Critério padrão

ADC 58 e 59 do STF (com os embargos de declaração de 2021) e Lei nº 14.905/2024, na forma fixada
pela SDI-1 do TST no E-ED-RR-713-03.2010.5.04.0029 (julgado em 17/10/2024):

| Período | Fase pré-judicial (antes do ajuizamento) | Fase judicial (do ajuizamento em diante) |
|---|---|---|
| Até 29/08/2024 | IPCA-E + juros do art. 39, caput, da Lei nº 8.177/1991 (TR) | SELIC (correção + juros) |
| A partir de 30/08/2024 | IPCA + juros pela taxa legal | IPCA + juros pela taxa legal |

- **Taxa legal** (art. 406 do CC; Resolução CMN nº 5.171/2024): SELIC − IPCA, com piso zero,
  divulgada pelo Banco Central (série SGS 29543).
- **Correção** (IPCA-E e IPCA): composta mês a mês.
- **SELIC, TR e taxa legal**: somadas mês a mês (juros simples, sem anatocismo, Súmula 121 do STF;
  art. 6º da Resolução CMN nº 5.171/2024).

## 2. Época própria

Os índices começam no **mês seguinte à competência** de cada parcela (Súmula 381 do TST). As
competências de cada parcela são:

| Parcela | Competência |
|---|---|
| Horas extras, adicionais e DSR | o próprio mês trabalhado |
| Reflexo no 13º | dezembro do ano (no último ano, o mês do desligamento) |
| Reflexo em férias + 1/3 | mês seguinte ao fim do período aquisitivo (limitado ao desligamento) |
| Reflexo no aviso, multa do FGTS e verbas rescisórias | mês do desligamento |
| FGTS | a mesma da parcela sobre a qual incide (OJ 302 da SDI-1: mesmos índices dos débitos trabalhistas) |

## 3. Passagem por 30/08/2024

Para cada parcela, o valor é corrigido pelo regime antigo até agosto/2024. Nesse ponto, principal
corrigido + juros (TR) + SELIC formam a base, que passa a ser corrigida pelo IPCA. A taxa legal
incide sobre essa base corrigida.

## 4. Granularidade mensal (simplificações)

- O mês do ajuizamento já é tratado como fase judicial (SELIC no regime antigo).
- O regime da Lei nº 14.905/2024 é aplicado a partir da competência setembro/2024 (agosto/2024
  inteiro fica no regime antigo; a lei vale desde 30/08).
- A atualização vai até o 1º dia do mês da data escolhida.
- Se a tabela do Banco Central ainda não tiver os índices do último mês, a atualização para no
  último mês disponível e o sistema avisa.

## 5. Petição inicial

Para a inicial, informe como ajuizamento a **data prevista de distribuição**. Assim, todo o
período é tratado como fase pré-judicial.

## 6. O que não é atualizado

Descontos (INSS, IR, adiantamentos e outros) são mostrados pelo valor histórico. Não há cálculo
de contribuição previdenciária nem de IR sobre os valores atualizados nesta versão.

## 7. Fonte dos índices

`tolaris/tabelas/indices.json`, baixado do Banco Central (SGS) por `scripts/atualizar_indices.py`:
IPCA-E (10764), IPCA (433), SELIC mensal (4390), taxa legal (29543) e TR (226, período iniciado
no dia 1º de cada mês). Os índices começam em 2000 (a taxa legal, em 08/2024). A mesma rotina
baixa a série do salário mínimo (1619), usada para conferir `salario_minimo.json` mês a mês nos
testes. A rotina **Atualizar índices** do GitHub roda todo dia 12 e grava o arquivo novo depois
de rodar os testes.

---

## Pontos para validação pelos advogados

1. **Juros na fase pré-judicial após 30/08/2024.** A tese da SDI-1 não distingue as fases a partir
   de 30/08/2024. Por isso o sistema aplica a taxa legal também antes do ajuizamento. Há juízes
   que aplicam juros só a partir do ajuizamento (art. 883 da CLT). O formulário tem a opção
   "Juros antes do ajuizamento" para esse caso.
2. **Base a partir de 30/08/2024**: principal + SELIC acumulada até 29/08/2024, corrigidos pelo
   IPCA, com a taxa legal sobre esse total. Alguns calculistas separam os juros já vencidos
   para não incidir taxa legal sobre eles.
3. **Granularidade mensal** (mês do ajuizamento e agosto/2024 inteiros num só regime), em vez de
   pro rata por dias.
4. **Época própria** das férias: mês seguinte ao fim do período aquisitivo.
