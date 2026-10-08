# Tolaris Trabalhista

Calculadora trabalhista para advogados: telas simples, cálculo rigoroso e uma memória de cálculo
que explica cada valor com a fórmula e o fundamento legal.

**Versão atual (0.4)**:

- **Verbas rescisórias** em todas as modalidades de extinção, com INSS, IRRF, FGTS + multa e
  multas dos arts. 467 e 477.
- **Horas extras, adicional noturno, insalubridade e periculosidade**, calculados mês a mês, com
  DSR, reflexos em 13º, férias + 1/3 e aviso prévio, FGTS + multa, prescrição quinquenal e valor
  por pedido para a petição inicial.
- **Correção monetária e juros** pela ADC 58 e pela Lei nº 14.905/2024 (critério da SDI-1 do TST),
  com índices oficiais do Banco Central atualizados todo mês.
- **Liquidação de sentença**: verbas rescisórias e horas extras/adicionais deferidas, dedução de
  valores pagos, atualização, INSS mês a mês (cota do empregado e da empresa, juros da Súmula
  368), imposto de renda acumulado (RRA), honorários de sucumbência, custas e o resumo com o
  líquido do reclamante e o total devido pela reclamada.
- Exportação em PDF e Excel (com demonstrativo mês a mês) e salvamento do caso em arquivo
  `.json` (nada fica armazenado no servidor).

## Como rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run streamlit_app.py
```

Testes e verificação de estilo:

```bash
pytest
ruff check .
```

## Estrutura

```
streamlit_app.py        ponto de entrada (local e Streamlit Community Cloud)
tolaris/
  motor/                cálculo puro, sem interface — é aqui que ficam as regras
    modelos.py          dados de entrada, lançamentos e resultado
    contrato.py         regras comuns (aviso proporcional, salário da época, FGTS)
    rescisao.py         verbas rescisórias
    horas_extras.py     horas extras, adicional noturno, insalubridade/periculosidade e reflexos
    atualizacao.py      correção monetária e juros (IPCA-E, SELIC, IPCA, taxa legal, TR)
    liquidacao.py       liquidação de sentença (verbas, deduções, INSS, IR, honorários, custas)
    tributos.py         INSS e IRRF (mensal e acumulado)
  tabelas/              INSS, IRRF, salário mínimo (por vigência) e índices do Banco Central (JSON)
  relatorios/           PDF e Excel
  interface/            telas Streamlit (só coletam dados e mostram o resultado)
                        e salvar/abrir caso em JSON
  datas.py, dinheiro.py regras de calendário e de valores (Decimal, arredondamento, R$)
scripts/                atualizar_indices.py: baixa os índices do Banco Central
regras/                 livro de regras (rescisao.md, horas_extras.md, atualizacao.md, liquidacao.md), com fundamento
                        e os pontos para validação pelos advogados
tests/                  testes com cenários calculados à mão
```

Princípio: **a interface nunca calcula**. Toda regra fica em `tolaris/motor`, documentada em
`regras/` e coberta por teste.

## Atualizar tabelas

**Índices de correção (IPCA-E, IPCA, SELIC, taxa legal, TR):** a rotina *Atualizar índices* do
GitHub Actions roda todo dia 12, baixa os índices do Banco Central, roda os testes e grava
`tolaris/tabelas/indices.json`. Para rodar na hora: aba *Actions* → *Atualizar índices* →
*Run workflow*. Localmente: `python scripts/atualizar_indices.py`.

**INSS, IRRF e salário mínimo** (cobertura: salário mínimo desde 1999; INSS desde 2008; IRRF desde 2015):
Quando sair tabela nova de INSS, IRRF ou salário mínimo, acrescente um item ao JSON
correspondente em `tolaris/tabelas/` com a data de `vigencia` e a `fonte`, e um teste em
`tests/test_tributos.py` com um valor oficial divulgado.

## Publicar no Streamlit Community Cloud

1. Acesse <https://share.streamlit.io> e entre com a conta do GitHub.
2. **Create app** → escolha este repositório, a branch `main` e o arquivo `streamlit_app.py`.
3. Em **Advanced settings**, escolha Python 3.12.
4. Como o repositório é privado, o app fica privado: em **Share**, convide os advogados pelo
   e-mail. Eles entram com Google ou com um link enviado por e-mail.

## Aviso

Ferramenta em fase de testes. Os resultados são estimativas baseadas nas informações fornecidas
e devem ser conferidos antes do uso em juízo.
