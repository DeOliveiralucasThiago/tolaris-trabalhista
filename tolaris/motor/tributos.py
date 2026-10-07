"""INSS do empregado e IRRF mensal, com a memória de cada cálculo em texto."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tolaris.dinheiro import ZERO, arredondar, formatar_brl, formatar_percentual
from tolaris.tabelas import TabelaINSS, TabelaIRRF, inss_vigente, irrf_vigente


@dataclass(frozen=True)
class ResultadoINSS:
    valor: Decimal
    base: Decimal
    tabela: TabelaINSS
    memoria: str


@dataclass(frozen=True)
class ResultadoIRRF:
    valor: Decimal
    rendimento: Decimal
    base: Decimal
    tabela: TabelaIRRF
    memoria: str


def calcular_inss(base, data: date) -> ResultadoINSS:
    """Contribuição do empregado sobre `base`, pela tabela vigente em `data`."""
    base = arredondar(base)
    tabela = inss_vigente(data)
    if base <= 0:
        return ResultadoINSS(ZERO, base, tabela, "Sem base de cálculo.")

    limitada = min(base, tabela.teto)
    partes = []
    if base > tabela.teto:
        partes.append(f"Base limitada ao teto de {formatar_brl(tabela.teto)}.")

    if tabela.tipo == "aliquota_unica":
        faixa = next(f for f in tabela.faixas if limitada <= f.ate)
        valor = arredondar(limitada * faixa.aliquota)
        partes.append(
            f"{formatar_brl(limitada)} × {formatar_percentual(faixa.aliquota)} = {formatar_brl(valor)} "
            f"(alíquota única da faixa)."
        )
    else:
        total = Decimal(0)
        anterior = Decimal(0)
        detalhes = []
        for faixa in tabela.faixas:
            if limitada <= anterior:
                break
            parcela = min(limitada, faixa.ate) - anterior
            total += parcela * faixa.aliquota
            detalhes.append(f"{formatar_brl(parcela)} × {formatar_percentual(faixa.aliquota)}")
            anterior = faixa.ate
        valor = arredondar(total)
        partes.append(f"Cálculo progressivo por faixa: {' + '.join(detalhes)} = {formatar_brl(valor)}.")

    partes.append(f"Tabela vigente desde {tabela.vigencia:%d/%m/%Y} ({tabela.fonte}).")
    return ResultadoINSS(valor, base, tabela, " ".join(partes))


def calcular_irrf(
    rendimento,
    inss,
    dependentes: int,
    data: date,
    permitir_simplificado: bool = True,
) -> ResultadoIRRF:
    """IRRF pela tabela mensal vigente em `data`.

    Deduções legais = INSS + dependentes. Quando a tabela prevê desconto simplificado
    e ele for maior que as deduções legais, ele as substitui. Depois aplica a redução
    da Lei nº 15.270/2025 (a partir de 2026), calculada sobre o rendimento tributável.
    """
    rendimento = arredondar(rendimento)
    inss = arredondar(inss)
    tabela = irrf_vigente(data)
    if rendimento <= 0:
        return ResultadoIRRF(ZERO, rendimento, ZERO, tabela, "Sem rendimento tributável.")

    deducao_dependentes = arredondar(tabela.deducao_dependente * dependentes)
    deducoes_legais = inss + deducao_dependentes
    partes = [f"Rendimento tributável: {formatar_brl(rendimento)}."]

    simplificado = tabela.desconto_simplificado
    if permitir_simplificado and simplificado is not None and simplificado > deducoes_legais:
        deducao = simplificado
        partes.append(
            f"Desconto simplificado de {formatar_brl(simplificado)} (maior que as deduções legais "
            f"de {formatar_brl(deducoes_legais)})."
        )
    else:
        deducao = deducoes_legais
        texto = f"Deduções: INSS {formatar_brl(inss)}"
        if dependentes:
            texto += f" + {dependentes} dependente(s) {formatar_brl(deducao_dependentes)}"
        partes.append(texto + ".")

    base = max(rendimento - deducao, ZERO)
    faixa = next(f for f in tabela.faixas if f.ate is None or base <= f.ate)
    imposto = max(arredondar(base * faixa.aliquota - faixa.parcela), ZERO)
    if faixa.aliquota == 0:
        partes.append(f"Base de {formatar_brl(base)} na faixa de isenção.")
    else:
        partes.append(
            f"Base {formatar_brl(base)} × {formatar_percentual(faixa.aliquota)} − parcela a deduzir "
            f"{formatar_brl(faixa.parcela)} = {formatar_brl(imposto)}."
        )

    redutor = tabela.redutor
    if redutor and imposto > 0:
        if rendimento <= redutor.isencao_ate:
            reducao = min(imposto, redutor.reducao_maxima)
        elif rendimento <= redutor.decrescente_ate:
            reducao = min(imposto, max(arredondar(redutor.constante - redutor.coeficiente * rendimento), ZERO))
        else:
            reducao = ZERO
        if reducao:
            imposto -= reducao
            partes.append(f"Redução da Lei nº 15.270/2025: −{formatar_brl(reducao)}.")

    partes.append(f"IRRF devido: {formatar_brl(imposto)}. Tabela vigente desde {tabela.vigencia:%d/%m/%Y}.")
    return ResultadoIRRF(imposto, rendimento, base, tabela, " ".join(partes))
