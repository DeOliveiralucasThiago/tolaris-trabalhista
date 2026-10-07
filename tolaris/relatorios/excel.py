"""Planilha com valores numéricos (não texto), para o advogado conferir e somar."""

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from tolaris.motor.modelos import Grupo, ResultadoRescisao

FORMATO_MOEDA = '"R$" #,##0.00'
AZUL = "002B5B"


def gerar_excel(resultado: ResultadoRescisao) -> bytes:
    livro = Workbook()
    planilha = livro.active
    planilha.title = "Rescisão"

    planilha.append(["TOLARIS TRABALHISTA – Cálculo de verbas rescisórias"])
    planilha["A1"].font = Font(bold=True, size=14, color=AZUL)
    planilha.append([f"Emitido em {datetime.now():%d/%m/%Y %H:%M}"])
    planilha.append([])

    for chave, valor in resultado.resumo.items():
        planilha.append([chave, valor])
    planilha.append([])

    cabecalho = ["Grupo", "Rubrica", "Natureza", "Valor (R$)", "Memória de cálculo", "Fundamento"]
    planilha.append(cabecalho)
    for celula in planilha[planilha.max_row]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=AZUL)

    for grupo in Grupo:
        for item in resultado.do_grupo(grupo):
            planilha.append(
                [item.grupo.value, item.descricao, item.natureza, item.valor, item.formula, item.fundamento]
            )
            planilha.cell(planilha.max_row, 4).number_format = FORMATO_MOEDA

    planilha.append([])
    for rotulo, valor in (
        ("Total de proventos", resultado.total_proventos),
        ("Total de descontos", resultado.total_descontos),
        ("Líquido rescisório", resultado.liquido),
        ("FGTS a depositar (depósito + multa)", resultado.total_fgts),
        ("Total geral", resultado.total_geral),
    ):
        planilha.append(["", rotulo, "", valor])
        planilha.cell(planilha.max_row, 2).font = Font(bold=True)
        planilha.cell(planilha.max_row, 4).number_format = FORMATO_MOEDA
        planilha.cell(planilha.max_row, 4).font = Font(bold=True)

    if resultado.alertas:
        planilha.append([])
        planilha.append(["Alertas"])
        planilha.cell(planilha.max_row, 1).font = Font(bold=True)
        for alerta in resultado.alertas:
            planilha.append(["", alerta])

    for coluna, largura in zip("ABCDEF", (14, 55, 15, 15, 80, 70), strict=True):
        planilha.column_dimensions[coluna].width = largura
    for linha in planilha.iter_rows(min_col=5, max_col=6):
        for celula in linha:
            celula.alignment = Alignment(wrap_text=True, vertical="top")

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
