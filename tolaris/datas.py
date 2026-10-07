"""Regras de calendário usadas no cálculo trabalhista."""

import calendar
from datetime import date, timedelta

UM_DIA = timedelta(days=1)


def formatar_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def ultimo_dia_do_mes(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def somar_meses(d: date, meses: int) -> date:
    """Soma meses mantendo o dia; se o dia não existe no mês de destino, usa o último dia.

    Ex.: 31/01 + 1 mês = 28/02 (ou 29/02); 29/02/2024 + 12 meses = 28/02/2025.
    """
    indice = d.year * 12 + (d.month - 1) + meses
    ano, mes = divmod(indice, 12)
    mes += 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def dias_corridos(inicio: date, fim: date) -> int:
    """Quantidade de dias entre as datas, contando as duas pontas. Zero se fim < inicio."""
    return max((fim - inicio).days + 1, 0)


def anos_completos(inicio: date, fim: date) -> int:
    """Anos completos de inicio até fim (inclusive). 01/03/2023 a 28/02/2024 = 1 ano."""
    anos = 0
    while somar_meses(inicio, 12 * (anos + 1)) <= fim + UM_DIA:
        anos += 1
    return anos


def meses_com_fracao(inicio: date, fim: date, minimo_dias: int = 15) -> int:
    """Meses contados a partir de `inicio` até `fim` (inclusive), contando a fração de
    `minimo_dias` ou mais como mês inteiro. Usado nas férias proporcionais (art. 146,
    parágrafo único, CLT: fração superior a 14 dias)."""
    if fim < inicio:
        return 0
    limite = fim + UM_DIA
    meses = 0
    while somar_meses(inicio, meses + 1) <= limite:
        meses += 1
    restante = (limite - somar_meses(inicio, meses)).days
    return meses + (1 if restante >= minimo_dias else 0)


def avos_no_ano(inicio: date, fim: date, ano: int, minimo_dias: int = 15) -> int:
    """Avos de 13º no ano civil: conta cada mês do calendário em que houve `minimo_dias`
    ou mais dias de vínculo entre `inicio` e `fim` (Lei nº 4.090/1962, art. 1º, § 2º)."""
    avos = 0
    for mes in range(1, 13):
        primeiro = date(ano, mes, 1)
        ultimo = ultimo_dia_do_mes(ano, mes)
        dias = dias_corridos(max(inicio, primeiro), min(fim, ultimo))
        if dias >= minimo_dias:
            avos += 1
    return avos


def primeiro_dia_do_mes(d: date) -> date:
    return d.replace(day=1)


def meses_entre(inicio: date, fim: date):
    """Gera o primeiro dia de cada mês de `inicio` até `fim` (inclusive)."""
    atual = primeiro_dia_do_mes(inicio)
    while atual <= fim:
        yield atual
        atual = somar_meses(atual, 1)
