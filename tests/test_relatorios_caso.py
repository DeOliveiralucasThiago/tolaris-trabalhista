import io
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from tolaris.dinheiro import formatar_brl, formatar_percentual
from tolaris.interface.caso import formulario_de_json, formulario_para_json
from tolaris.motor.horas_extras import calcular_pedidos
from tolaris.motor.modelos import (
    AdicionalOcupacional,
    AlteracaoSalarial,
    Aviso,
    DadosPedidos,
    DadosRescisao,
    Modalidade,
    PeriodoJornada,
)
from tolaris.motor.rescisao import calcular_rescisao
from tolaris.relatorios.excel import gerar_excel
from tolaris.relatorios.pdf import gerar_pdf

DADOS = DadosRescisao(
    admissao=date(2023, 3, 1),
    desligamento=date(2026, 5, 15),
    modalidade=Modalidade.SEM_JUSTA_CAUSA,
    aviso=Aviso.INDENIZADO,
    salario=Decimal("3000"),
    historico_salarial=[AlteracaoSalarial(date(2023, 3, 1), Decimal("2500"))],
    saldo_fgts=None,
    multa_467=True,
)


def test_formatacao_brasileira():
    assert formatar_brl(Decimal("1234567.891")) == "R$ 1.234.567,89"
    assert formatar_brl(Decimal("-10")) == "-R$ 10,00"
    assert formatar_percentual(Decimal("0.075")) == "7,5%"
    assert formatar_percentual(Decimal("0.14")) == "14%"


PEDIDOS = DadosPedidos(
    admissao=date(2024, 1, 1),
    desligamento=date(2025, 6, 30),
    modalidade=Modalidade.SEM_JUSTA_CAUSA,
    aviso=Aviso.INDENIZADO,
    salario=Decimal("2200"),
    periodos=[PeriodoJornada(date(2024, 1, 1), date(2025, 6, 30), horas_extras_1=Decimal(20))],
    adicional_ocupacional=AdicionalOcupacional.INSALUBRIDADE_MEDIO,
)


def test_caso_ida_e_volta():
    campos = {
        "modo": "Horas extras e adicionais",
        "admissao": date(2024, 1, 1),
        "modalidade": Modalidade.ACORDO,
        "adicional_ocupacional": AdicionalOcupacional.PERICULOSIDADE,
        "salario": 2500.0,
        "campo_desconhecido": "ignorado",
    }
    tabelas = {"periodos": [{"Início": date(2024, 2, 1), "Fim": None, "HE 1º adicional (h/mês)": 20.0}]}
    campos_lidos, tabelas_lidas = formulario_de_json(formulario_para_json(campos, tabelas))
    del campos["campo_desconhecido"]
    assert campos_lidos == campos
    assert tabelas_lidas == tabelas


def test_pdf_e_gerado():
    assert gerar_pdf(calcular_rescisao(DADOS)).startswith(b"%PDF")
    assert gerar_pdf(calcular_pedidos(PEDIDOS)).startswith(b"%PDF")


def test_excel_tem_valores_numericos():
    resultado = calcular_rescisao(DADOS)
    planilha = load_workbook(io.BytesIO(gerar_excel(resultado))).active
    valores = [linha[3] for linha in planilha.iter_rows(values_only=True) if isinstance(linha[3], (int, float))]
    assert float(resultado.liquido) in valores


def test_excel_de_pedidos_tem_aba_mes_a_mes():
    livro = load_workbook(io.BytesIO(gerar_excel(calcular_pedidos(PEDIDOS))))
    assert livro.sheetnames == ["Resumo", "Mês a mês"]
    assert livro["Mês a mês"].max_row == 19  # cabeçalho + 18 competências
