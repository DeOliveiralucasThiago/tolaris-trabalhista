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
        inss_vigente(date(2007, 12, 31))


def test_inss_tabelas_antigas_de_aliquota_unica():
    # 2010: 1.024,97 até maio (PI 350/2009) e 1.040,22 a partir de junho (PI 333/2010)
    assert inss_vigente(date(2010, 5, 1)).faixas[0].ate == Decimal("1024.97")
    assert inss_vigente(date(2010, 6, 1)).faixas[0].ate == Decimal("1040.22")
    assert inss_vigente(date(2011, 3, 1)).teto == Decimal("3691.74")  # PI 407/2011, desde a competência 01/2011
    assert calcular_inss(Decimal("2000"), date(2015, 6, 1)).valor == Decimal("180.00")  # 9%
    assert calcular_inss(Decimal("10000"), date(2018, 6, 1)).valor == Decimal("621.04")  # 11% × teto 5.645,80


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


def test_salario_minimo_historico():
    from tolaris.tabelas import salario_minimo_vigente

    assert salario_minimo_vigente(date(2000, 4, 2)).valor == Decimal("136.00")
    assert salario_minimo_vigente(date(2000, 4, 3)).valor == Decimal("151.00")
    assert salario_minimo_vigente(date(2011, 2, 28)).valor == Decimal("540.00")  # MP 516/2010
    assert salario_minimo_vigente(date(2011, 3, 1)).valor == Decimal("545.00")  # Lei 12.382/2011


def test_salario_minimo_confere_mes_a_mes_com_o_banco_central():
    """Compara cada mês desde 2000 com a série 1619 do SGS, baixada pela rotina de índices."""
    import json
    from pathlib import Path

    from tolaris.tabelas import salario_minimo_vigente

    caminho = Path(__file__).parent.parent / "tolaris" / "tabelas" / "indices.json"
    conferencia = json.loads(caminho.read_text(encoding="utf-8")).get("conferencia") if caminho.exists() else None
    if not conferencia:
        pytest.skip("série 1619 do Banco Central ainda não foi baixada")
    divergencias = []
    for mes, valor in conferencia["salario_minimo"].items():
        ano, numero = (int(x) for x in mes.split("-"))
        if ano < 2000:
            continue
        # dia 15: evita a mudança de 03/04/2000 no meio de abril
        nosso = salario_minimo_vigente(date(ano, numero, 15)).valor
        if nosso != Decimal(valor):
            divergencias.append(f"{mes}: tabela {nosso}, Banco Central {valor}")
    assert not divergencias, divergencias


def test_irrf_acumulado_multiplica_faixas_pelo_numero_de_meses():
    from tolaris.motor.tributos import calcular_irrf_rra

    # 2024: base 20.000 − 1.000 = 19.000 > 4.664,68 × 3 → 19.000 × 27,5% − 896,00 × 3 = 2.537,00
    assert calcular_irrf_rra(Decimal("20000"), Decimal("1000"), 3, date(2024, 6, 1)).valor == Decimal("2537.00")
    # Isento: 6.000 em 3 meses (até 2.259,20 × 3 = 6.777,60)
    assert calcular_irrf_rra(Decimal("6000"), Decimal("0"), 3, date(2024, 6, 1)).valor == 0


def test_irrf_acumulado_2026_com_reducao_multiplicada_pelo_numero_de_meses():
    from tolaris.motor.tributos import calcular_irrf_rra

    # 18.000 em 3 meses: 18.000 × 27,5% − 908,73 × 3 = 2.223,81
    # Redução: 978,62 × 3 − 0,133145 × 18.000 = 539,25 → 1.684,56
    assert calcular_irrf_rra(Decimal("18000"), Decimal("0"), 3, date(2026, 6, 1)).valor == Decimal("1684.56")
