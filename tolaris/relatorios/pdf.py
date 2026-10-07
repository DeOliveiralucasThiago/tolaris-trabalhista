"""Memória de cálculo em PDF: demonstrativo + fórmula e fundamento de cada rubrica."""

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from tolaris.dinheiro import formatar_brl
from tolaris.motor.atualizacao import ResultadoAtualizacao
from tolaris.motor.modelos import Grupo, ResultadoCalculo
from tolaris.relatorios.mensal import colunas_ativas, formatar

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
NOVA_LINHA = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


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
        self.cell(0, 4, _texto(AVISO_LEGAL), align="C", **NOVA_LINHA)
        self.cell(0, 4, f"Página {self.page_no()}/{{nb}}", align="C")


def _secao(pdf: FPDF, titulo: str):
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 8, _texto(titulo), **NOVA_LINHA)
    pdf.set_text_color(0, 0, 0)


def _linha_valor(pdf: FPDF, rotulo: str, valor, negrito=False, preenchido=False):
    pdf.set_font("Helvetica", "B" if negrito else "", 10)
    pdf.set_fill_color(*FUNDO)
    largura = pdf.epw - 45
    pdf.cell(largura, 7, _texto(rotulo), border="B", fill=preenchido)
    pdf.cell(0, 7, _texto(formatar_brl(valor)), border="B", align="R", fill=preenchido, **NOVA_LINHA)


def _demonstrativo_mensal(pdf: FPDF, resultado: ResultadoCalculo, numero: int) -> int:
    linhas = getattr(resultado, "mensal", None)
    if not linhas:
        return numero
    pdf.add_page(orientation="L")
    _secao(pdf, f"{numero}. Demonstrativo mês a mês")
    colunas = colunas_ativas(linhas)
    largura = pdf.epw / len(colunas)

    def cabecalho():
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_fill_color(*AZUL)
        pdf.set_text_color(255, 255, 255)
        for coluna in colunas:
            pdf.cell(largura, 6, _texto(coluna.titulo), border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 7)

    cabecalho()
    for linha in linhas:
        if pdf.will_page_break(5):
            pdf.add_page(orientation="L")
            cabecalho()
        for coluna in colunas:
            alinhamento = "C" if coluna.tipo in ("mes", "fracao", "repousos") else "R"
            pdf.cell(largura, 5, _texto(formatar(coluna, linha)), border=1, align=alinhamento)
        pdf.ln()
    pdf.add_page(orientation="P")
    return numero + 1


def _atualizacao(pdf: FPDF, atualizado: ResultadoAtualizacao, numero: int) -> int:
    _secao(pdf, f"{numero}. Correção monetária e juros")
    pdf.set_font("Helvetica", "", 8.5)
    for linha in atualizado.criterio:
        pdf.multi_cell(0, 4.5, _texto(f"- {linha}"), **NOVA_LINHA)
    pdf.ln(2)
    larguras = (70, 24, 24, 24, 24, 24)
    titulos = ("Rubrica", "Original", "Correção", "SELIC", "Juros", "Atualizado")
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_fill_color(*AZUL)
    pdf.set_text_color(255, 255, 255)
    for largura, titulo in zip(larguras, titulos, strict=True):
        pdf.cell(largura, 6, _texto(titulo), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    def linha(rotulo, valores, negrito=False):
        pdf.set_font("Helvetica", "B" if negrito else "", 7.5)
        celulas = (rotulo, valores.original, valores.correcao, valores.selic, valores.juros, valores.total)
        for indice, (largura, valor) in enumerate(zip(larguras, celulas, strict=True)):
            texto = valor if indice == 0 else formatar_brl(valor)
            pdf.cell(largura, 5, _texto(texto)[:48], border=1, align="L" if indice == 0 else "R")
        pdf.ln()

    for item in atualizado.linhas:
        linha(item.descricao, item.valores)
    linha("Total (proventos e FGTS)", atualizado.soma(), negrito=True)
    pdf.ln(2)
    if atualizado.descontos:
        _linha_valor(pdf, "Descontos (não atualizados)", atualizado.descontos)
    _linha_valor(pdf, "TOTAL ATUALIZADO", atualizado.total, negrito=True, preenchido=True)
    return numero + 1


def gerar_pdf(resultado: ResultadoCalculo, atualizado: ResultadoAtualizacao | None = None) -> bytes:
    pdf = _Documento()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, "TOLARIS TRABALHISTA", align="C", **NOVA_LINHA)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _texto(resultado.titulo), align="C", **NOVA_LINHA)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 5, f"Emitido em {datetime.now():%d/%m/%Y %H:%M}", align="C", **NOVA_LINHA)
    pdf.set_text_color(0, 0, 0)

    _secao(pdf, "1. Dados do contrato")
    for chave, valor in resultado.resumo.items():
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(55, 5.5, _texto(chave))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5.5, _texto(valor), **NOVA_LINHA)

    _secao(pdf, "2. Demonstrativo")
    for grupo in Grupo:
        itens = resultado.do_grupo(grupo)
        if not itens:
            continue
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 7, _texto(TITULOS_GRUPO[grupo]), **NOVA_LINHA)
        pdf.set_text_color(0, 0, 0)
        for item in itens:
            _linha_valor(pdf, item.descricao, item.valor)
    pdf.ln(2)
    for rotulo, valor, destaque in resultado.totais():
        _linha_valor(pdf, rotulo.upper() if destaque else rotulo, valor, negrito=True, preenchido=destaque)

    numero = _demonstrativo_mensal(pdf, resultado, 3)
    if atualizado:
        numero = _atualizacao(pdf, atualizado, numero)

    _secao(pdf, f"{numero}. Memória de cálculo")
    for item in resultado.lancamentos:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.epw - 45, 5.5, _texto(item.descricao))
        pdf.cell(0, 5.5, _texto(formatar_brl(item.valor)), align="R", **NOVA_LINHA)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(0, 4.5, _texto(f"Cálculo: {item.formula}"), **NOVA_LINHA)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 4.5, _texto(f"Fundamento: {item.fundamento}"), **NOVA_LINHA)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1.5)

    if resultado.alertas:
        _secao(pdf, f"{numero + 1}. Alertas")
        pdf.set_font("Helvetica", "", 9)
        for alerta in resultado.alertas:
            pdf.multi_cell(0, 5, _texto(f"- {alerta}"), **NOVA_LINHA)

    return bytes(pdf.output())
