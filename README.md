# Tolaris Trabalhista

Calculadora trabalhista para advogados: telas simples, cálculo rigoroso e uma memória de cálculo
que explica cada valor com a fórmula e o fundamento legal.

**Versão atual (0.2)**:

- **Verbas rescisórias** em todas as modalidades de extinção, com INSS, IRRF, FGTS + multa e
  multas dos arts. 467 e 477.
- **Horas extras, adicional noturno, insalubridade e periculosidade**, calculados mês a mês, com
  DSR, reflexos em 13º, férias + 1/3 e aviso prévio, FGTS + multa, prescrição quinquenal e valor
  por pedido para a petição inicial.
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
    tributos.py         INSS e IRRF
  tabelas/              INSS, IRRF e salário mínimo por data de vigência (JSON)
  relatorios/           PDF e Excel
  interface/            telas Streamlit (só coletam dados e mostram o resultado)
                        e salvar/abrir caso em JSON
  datas.py, dinheiro.py regras de calendário e de valores (Decimal, arredondamento, R$)
regras/                 livro de regras (rescisao.md, horas_extras.md), com fundamento
                        e os pontos para validação pelos advogados
tests/                  testes com cenários calculados à mão
```

Princípio: **a interface nunca calcula**. Toda regra fica em `tolaris/motor`, documentada em
`regras/` e coberta por teste.

## Atualizar tabelas

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
