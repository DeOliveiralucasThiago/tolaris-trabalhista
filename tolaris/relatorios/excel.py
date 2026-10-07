"""Planilha com valores numéricos (não texto), para o advogado conferir e somar."""

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from tolaris.motor.modelos import Grupo, ResultadoCalculo
from tolaris.relatorios.mensal import colunas_ativas, numero

FORMATO_MOEDA = '"R$" #,##0.00'
FORMATO_HORAS = "#,##0.00"
AZUL = "002B5B"


def _cabecalho(planilha, titulos):
    planilha.append(titulos)
    for celula in planilha[planilha.max_row]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=AZUL)


def gerar_excel(resultado: ResultadoCalculo) -> bytes:
    livro = Workbook()
    planilha = livro.active
    planilha.title = "Resumo"

    planilha.append([f"TOLARIS TRABALHISTA – {resultado.titulo}"])
    planilha["A1"].font = Font(bold=True, size=14, color=AZUL)
    planilha.append([f"Emitido em {datetime.now():%d/%m/%Y %H:%M}"])
    planilha.append([])

    for chave, valor in resultado.resumo.items():
        planilha.append([chave, valor])
    planilha.append([])

    _cabecalho(planilha, ["Grupo", "Rubrica", "Natureza", "Valor (R$)", "Memória de cálculo", "Fundamento"])
    for grupo in Grupo:
        for item in resultado.do_grupo(grupo):
            planilha.append(
                [item.grupo.value, item.descricao, item.natureza, item.valor, item.formula, item.fundamento]
            )
            planilha.cell(planilha.max_row, 4).number_format = FORMATO_MOEDA

    planilha.append([])
    for rotulo, valor, _destaque in resultado.totais():
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

    linhas = getattr(resultado, "mensal", None)
    if linhas:
        mensal = livro.create_sheet("Mês a mês")
        colunas = colunas_ativas(linhas)
        _cabecalho(mensal, [c.titulo for c in colunas])
        for linha in linhas:
            mensal.append([numero(c, linha) for c in colunas])
            for indice, coluna in enumerate(colunas, start=1):
                celula = mensal.cell(mensal.max_row, indice)
                if coluna.tipo == "moeda":
                    celula.number_format = FORMATO_MOEDA
                elif coluna.tipo == "horas":
                    celula.number_format = FORMATO_HORAS
                elif coluna.tipo == "mes":
                    celula.number_format = "mm/yyyy"
                elif coluna.tipo == "fracao":
                    celula.number_format = "0.00%"
        for indice in range(1, len(colunas) + 1):
            mensal.column_dimensions[mensal.cell(1, indice).column_letter].width = 16

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
