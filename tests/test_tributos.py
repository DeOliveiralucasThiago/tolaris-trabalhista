from datetime import date
from decimal import Decimal

import pytest

from tolaris.motor.tributos import calcular_inss, calcular_irrf
from tolaris.tabelas import TabelaIndisponivel, aviso_tabela_desatualizada, inss_vigente, irrf_vigente


def test_inss_progressivo_2024():
    # 1.412,00×7,5% + 1.254,68×9% + 333,32×12% = 258,82 (confere com 3.000×12% − 101,18)
    assert calcular_inss(Decimal("3000"), date(2024, 6, 1)).valor == Decimal("258.82")


def test_inss_teto_2026():
    # Contribuição máxima divulgada para 2026: R$ 988,09
    assert calcular_inss(Decimal("20000"), date(2026, 3, 1)).valor == Decimal("988.09")


def test_inss_aliquota_unica_2019():
    assert calcular_inss(Decimal("2000"), date(2019, 7, 1)).valor == Decimal("180.00")


def test_inss_muda_de_tabela_na_vigencia():
    assert inss_vigente(date(2020, 2, 29)).tipo == "aliquota_unica"
    assert inss_vigente(date(2020, 3, 1)).tipo == "progressiva"
    assert inss_vigente(date(2023, 4, 30)).faixas[0].ate == Decimal("1302.00")
    assert inss_vigente(date(2023, 5, 1)).faixas[0].ate == Decimal("1320.00")


def test_irrf_muda_de_tabela_na_vigencia():
    assert irrf_vigente(date(2025, 4, 30)).faixas[0].ate == Decimal("2259.20")
    assert irrf_vigente(date(2025, 5, 1)).faixas[0].ate == Decimal("2428.80")


def test_sem_tabela_para_data_antiga():
    with pytest.raises(TabelaIndisponivel):
        inss_vigente(date(2018, 12, 31))


def test_irrf_usa_desconto_simplificado_quando_maior():
    # 2024: INSS 258,82 < simplificado 564,80. Base 2.435,20 × 7,5% − 169,44 = 13,20
    resultado = calcular_irrf(Decimal("3000"), Decimal("258.82"), 0, date(2024, 6, 1))
    assert resultado.valor == Decimal("13.20")


def test_irrf_2026_isento_ate_5000():
    # 4.500 − 607,20 = 3.892,80 → 200,39 de imposto pela tabela, zerado pela redução
    assert calcular_irrf(Decimal("4500"), Decimal("0"), 0, date(2026, 2, 1)).valor == Decimal("0.00")


def test_irrf_2026_reducao_decrescente():
    # Rendimento 6.000, INSS 641,51: base 5.358,49 × 27,5% − 908,73 = 564,85
    # Redução: 978,62 − 0,133145 × 6.000 = 179,75 → imposto 385,10
    inss = calcular_inss(Decimal("6000"), date(2026, 2, 1)).valor
    assert inss == Decimal("641.51")
    assert calcular_irrf(Decimal("6000"), inss, 0, date(2026, 2, 1)).valor == Decimal("385.10")


def test_irrf_sem_simplificado_no_13():
    # 13º de 3.000 em 2024 sem simplificado: base 3.000 − 258,82 = 2.741,18 → 7,5% − 169,44 = 36,15
    resultado = calcular_irrf(Decimal("3000"), Decimal("258.82"), 0, date(2024, 12, 1), permitir_simplificado=False)
    assert resultado.valor == Decimal("36.15")


def test_alerta_quando_ano_nao_tem_tabela_nova():
    assert aviso_tabela_desatualizada(date(2026, 12, 31)) is None
    assert "2027" in aviso_tabela_desatualizada(date(2027, 1, 15))
