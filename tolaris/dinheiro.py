"""Valores monetários: sempre Decimal, arredondados ao centavo (meio para cima)."""

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


def dec(valor) -> Decimal:
    """Converte int, float, str ou Decimal em Decimal sem herdar erro binário do float."""
    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        return ZERO
    return Decimal(str(valor))


def arredondar(valor) -> Decimal:
    return dec(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatar_numero(valor, casas: int = 2) -> str:
    """1234.5 -> '1.234,50'."""
    quantum = Decimal(1).scaleb(-casas)
    texto = f"{dec(valor).quantize(quantum, rounding=ROUND_HALF_UP):,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def formatar_brl(valor) -> str:
    """1234.5 -> 'R$ 1.234,50'; -10 -> '-R$ 10,00'."""
    valor = dec(valor)
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {formatar_numero(abs(valor))}"


def formatar_percentual(fracao, casas: int = 2) -> str:
    """Decimal('0.075') -> '7,5%'; mantém só as casas necessárias."""
    texto = formatar_numero(dec(fracao) * 100, casas)
    if "," in texto:
        texto = texto.rstrip("0").rstrip(",")
    return f"{texto}%"
