"""Memória de cálculo em PDF: demonstrativo + fórmula e fundamento de cada rubrica."""

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from tolaris.dinheiro import formatar_brl
from tolaris.motor.modelos import Grupo, ResultadoRescisao

AZUL = (0, 43, 91)
CINZA = (90, 90, 90)
FUNDO = (235, 240, 245)
AVISO_LEGAL = (
    "Cálculo estimativo elaborado com base nas informações fornecidas pelo usuário. "
    "Confira os dados e os critérios antes de utilizá-lo em juízo."
)
TITULOS_GRUPO = {
    Grupo.PROVENTO: "Proventos",
    Grupo.DESCONTO: "Descontos",
    Grupo.FGTS: "FGTS (depositado na conta vinculada)",
}
TROCAS = {"–": "-", "—": "-", "−": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-"}


def _texto(valor) -> str:
    """As fontes padrão do PDF usam latin-1: troca os poucos símbolos fora dele."""
    texto = str(valor)
    for original, troca in TROCAS.items():
        texto = texto.replace(original, troca)
    return texto.encode("latin-1", "replace").decode("latin-1")


class _Documento(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*CINZA)
        self.cell(0, 4, _texto(AVISO_LEGAL), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, f"Página {self.page_no()}/{{nb}}", align="C")


def _secao(pdf: FPDF, titulo: str):
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 8, _texto(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)


def _linha_valor(pdf: FPDF, rotulo: str, valor, negrito=False, preenchido=False):
    pdf.set_font("Helvetica", "B" if negrito else "", 10)
    pdf.set_fill_color(*FUNDO)
    pdf.cell(140, 7, _texto(rotulo), border="B", fill=preenchido)
    pdf.cell(
        0, 7, _texto(formatar_brl(valor)), border="B", align="R", fill=preenchido, new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )


def gerar_pdf(resultado: ResultadoRescisao) -> bytes:
    pdf = _Documento()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, "TOLARIS TRABALHISTA", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _texto("Memória de cálculo de verbas rescisórias"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 5, f"Emitido em {datetime.now():%d/%m/%Y %H:%M}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    _secao(pdf, "1. Dados do contrato")
    pdf.set_font("Helvetica", "", 9)
    for chave, valor in resultado.resumo.items():
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(55, 5.5, _texto(chave))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5.5, _texto(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    _secao(pdf, "2. Demonstrativo")
    for grupo in Grupo:
        itens = resultado.do_grupo(grupo)
        if not itens:
            continue
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 7, _texto(TITULOS_GRUPO[grupo]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        for item in itens:
            _linha_valor(pdf, item.descricao, item.valor)
    pdf.ln(2)
    _linha_valor(pdf, "Total de proventos", resultado.total_proventos, negrito=True)
    _linha_valor(pdf, "Total de descontos", resultado.total_descontos, negrito=True)
    _linha_valor(pdf, "LÍQUIDO RESCISÓRIO", resultado.liquido, negrito=True, preenchido=True)
    _linha_valor(pdf, "FGTS a depositar (depósito + multa)", resultado.total_fgts, negrito=True)
    _linha_valor(pdf, "TOTAL GERAL", resultado.total_geral, negrito=True, preenchido=True)

    _secao(pdf, "3. Memória de cálculo")
    for item in resultado.lancamentos:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(140, 5.5, _texto(item.descricao))
        pdf.cell(0, 5.5, _texto(formatar_brl(item.valor)), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(0, 4.5, _texto(f"Cálculo: {item.formula}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 4.5, _texto(f"Fundamento: {item.fundamento}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1.5)

    if resultado.alertas:
        _secao(pdf, "4. Alertas")
        pdf.set_font("Helvetica", "", 9)
        for alerta in resultado.alertas:
            pdf.multi_cell(0, 5, _texto(f"- {alerta}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
