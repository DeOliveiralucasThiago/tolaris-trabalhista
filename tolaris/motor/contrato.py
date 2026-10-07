"""Regras do contrato usadas por mais de um cálculo (rescisão e pedidos)."""

from datetime import date
from decimal import Decimal

from tolaris.datas import anos_completos
from tolaris.motor.modelos import AlteracaoSalarial, Aviso, Modalidade

ALIQUOTA_FGTS = Decimal("0.08")
METADE = Decimal("0.5")
MULTA_FGTS = {
    Modalidade.SEM_JUSTA_CAUSA: Decimal("0.40"),
    Modalidade.RESCISAO_INDIRETA: Decimal("0.40"),
    Modalidade.ACORDO: Decimal("0.20"),
    Modalidade.CULPA_RECIPROCA: Decimal("0.20"),
}
AVISO_PELO_EMPREGADOR = {
    Modalidade.SEM_JUSTA_CAUSA,
    Modalidade.RESCISAO_INDIRETA,
    Modalidade.ACORDO,
    Modalidade.CULPA_RECIPROCA,
}
AVISO_PELA_METADE = {Modalidade.ACORDO, Modalidade.CULPA_RECIPROCA}


def dias_de_aviso(admissao: date, desligamento: date) -> int:
    """Lei nº 12.506/2011: 30 dias + 3 por ano completo de serviço, até 90 dias."""
    return min(30 + 3 * anos_completos(admissao, desligamento), 90)


def dias_aviso_indenizados(modalidade: Modalidade, aviso: Aviso, dias_aviso: int) -> int:
    """Dias de aviso pagos como indenização (e projetados no tempo de serviço)."""
    if modalidade not in AVISO_PELO_EMPREGADOR:
        return 0
    if aviso == Aviso.INDENIZADO:
        return dias_aviso
    # Aviso trabalhado: 30 dias cumpridos; os dias da proporcionalidade são indenizados.
    return dias_aviso - 30


def salario_em(historico: list[AlteracaoSalarial], salario_atual: Decimal, data: date) -> Decimal:
    """Salário vigente em `data` pelo histórico; sem histórico, o salário atual."""
    vigentes = [a for a in historico if a.inicio <= data]
    if not vigentes:
        return salario_atual
    return max(vigentes, key=lambda a: a.inicio).salario
