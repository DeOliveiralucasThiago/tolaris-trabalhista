from datetime import date

from tolaris.datas import anos_completos, avos_no_ano, meses_com_fracao, somar_meses


def test_somar_meses_ajusta_para_ultimo_dia_do_mes():
    assert somar_meses(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert somar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert somar_meses(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert somar_meses(date(2025, 11, 15), 3) == date(2026, 2, 15)


def test_anos_completos():
    assert anos_completos(date(2023, 3, 1), date(2024, 2, 28)) == 0
    assert anos_completos(date(2023, 3, 1), date(2024, 2, 29)) == 1  # 01/03/2023 a 29/02/2024 = 1 ano
    assert anos_completos(date(2023, 3, 1), date(2026, 5, 15)) == 3


def test_meses_com_fracao_conta_15_dias_ou_mais():
    # 01/03 a 23/06: 3 meses completos + 23 dias -> 4
    assert meses_com_fracao(date(2026, 3, 1), date(2026, 6, 23)) == 4
    # 10/08 a 20/02: 6 meses completos + 11 dias -> 6
    assert meses_com_fracao(date(2025, 8, 10), date(2026, 2, 20)) == 6
    # 14 dias não contam, 15 contam
    assert meses_com_fracao(date(2026, 1, 1), date(2026, 1, 14)) == 0
    assert meses_com_fracao(date(2026, 1, 1), date(2026, 1, 15)) == 1


def test_avos_de_13_respeitam_admissao_no_mesmo_ano():
    # Admitido em 01/10/2024, contrato até 15/12/2024: out, nov e dez (15 dias) = 3 avos
    assert avos_no_ano(date(2024, 10, 1), date(2024, 12, 15), 2024) == 3
    # Admitido em 20/03: março tem só 12 dias, não conta
    assert avos_no_ano(date(2025, 3, 20), date(2025, 12, 31), 2025) == 9
    assert avos_no_ano(date(2025, 3, 17), date(2025, 12, 31), 2025) == 10
