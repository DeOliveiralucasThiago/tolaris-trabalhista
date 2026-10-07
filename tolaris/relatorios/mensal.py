"""Colunas do demonstrativo mês a mês, compartilhadas por tela, PDF e Excel."""

from dataclasses import dataclass
from decimal import Decimal

from tolaris.dinheiro import formatar_brl, formatar_numero
from tolaris.motor.modelos import LinhaMensal


@dataclass(frozen=True)
class Coluna:
    titulo: str
    tipo: str  # "mes", "fracao", "moeda", "horas", "repousos"
    obter: callable
    opcional: bool = True  # some quando todos os valores são zero


COLUNAS = (
    Coluna("Competência", "mes", lambda m: m.competencia, opcional=False),
    Coluna("Parte do mês", "fracao", lambda m: m.fracao, opcional=False),
    Coluna("Salário", "moeda", lambda m: m.salario, opcional=False),
    Coluna("Insal./Peric.", "moeda", lambda m: m.adicional_ocupacional),
    Coluna("Valor-hora", "moeda", lambda m: m.valor_hora, opcional=False),
    Coluna("HE 1º adic. (h)", "horas", lambda m: m.horas_extras_1),
    Coluna("HE 2º adic. (h)", "horas", lambda m: m.horas_extras_2),
    Coluna("Noturnas (h)", "horas", lambda m: m.horas_noturnas),
    Coluna("HE 1º adic.", "moeda", lambda m: m.valor_he_1),
    Coluna("HE 2º adic.", "moeda", lambda m: m.valor_he_2),
    Coluna("Adic. noturno", "moeda", lambda m: m.valor_noturno),
    Coluna("Adic. devido", "moeda", lambda m: m.valor_adicional),
    Coluna("Úteis/repousos", "repousos", lambda m: f"{m.dias_uteis} / {m.repousos}"),
    Coluna("DSR s/ HE", "moeda", lambda m: m.dsr_he),
    Coluna("DSR s/ noturno", "moeda", lambda m: m.dsr_noturno),
)


def colunas_ativas(linhas: list[LinhaMensal]) -> list[Coluna]:
    ativas = []
    for coluna in COLUNAS:
        if coluna.opcional and coluna.tipo != "repousos" and not any(coluna.obter(m) for m in linhas):
            continue
        ativas.append(coluna)
    # Úteis/repousos só interessa quando há DSR
    if not any(m.dsr_he or m.dsr_noturno for m in linhas):
        ativas = [c for c in ativas if c.tipo != "repousos"]
    return ativas


def formatar(coluna: Coluna, linha: LinhaMensal) -> str:
    valor = coluna.obter(linha)
    if coluna.tipo == "mes":
        return f"{valor:%m/%Y}"
    if coluna.tipo == "fracao":
        return "integral" if valor == 1 else f"{formatar_numero(valor * 30, 0)}/30"
    if coluna.tipo == "moeda":
        return formatar_brl(valor)
    if coluna.tipo == "horas":
        return formatar_numero(valor)
    return str(valor)


def numero(coluna: Coluna, linha: LinhaMensal):
    """Valor para planilha: números como float, datas como data, texto como texto."""
    valor = coluna.obter(linha)
    if isinstance(valor, Decimal):
        return float(round(valor, 4 if coluna.tipo == "fracao" else 2))
    return valor
