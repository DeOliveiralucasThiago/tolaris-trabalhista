"""Cenários completos de rescisão. Os valores esperados foram calculados à mão e estão
explicados nos comentários; ver também regras/rescisao.md."""

from datetime import date
from decimal import Decimal

import pytest

from tolaris.motor.modelos import AlteracaoSalarial, Aviso, DadosRescisao, ErroDeEntrada, Modalidade
from tolaris.motor.rescisao import calcular_rescisao, dias_de_aviso, dias_de_ferias_por_faltas


def valores(resultado) -> dict[str, Decimal]:
    return {item.codigo: item.valor for item in resultado.lancamentos}


def dados(**kwargs) -> DadosRescisao:
    padrao = dict(
        admissao=date(2023, 3, 1),
        desligamento=date(2026, 5, 15),
        modalidade=Modalidade.SEM_JUSTA_CAUSA,
        aviso=Aviso.INDENIZADO,
        salario=Decimal("3000"),
    )
    padrao.update(kwargs)
    return DadosRescisao(**padrao)


def test_dias_de_aviso_proporcional():
    assert dias_de_aviso(date(2025, 1, 1), date(2025, 12, 31)) == 33  # 1 ano completo
    assert dias_de_aviso(date(2025, 1, 2), date(2025, 12, 31)) == 30
    assert dias_de_aviso(date(2023, 3, 1), date(2026, 5, 15)) == 39
    assert dias_de_aviso(date(1990, 1, 1), date(2026, 1, 1)) == 90  # limite


def test_dias_de_ferias_por_faltas():
    assert [dias_de_ferias_por_faltas(f) for f in (0, 5, 6, 14, 15, 23, 24, 32, 33)] == [
        30,
        30,
        24,
        24,
        18,
        18,
        12,
        12,
        0,
    ]


def test_sem_justa_causa_com_aviso_indenizado():
    # 3 anos completos → aviso de 39 dias; projeção até 23/06/2026
    r = calcular_rescisao(dados())
    v = valores(r)
    assert v["saldo_salario"] == Decimal("1500.00")  # 3.000 ÷ 30 × 15
    assert v["aviso_previo"] == Decimal("3900.00")  # 3.000 ÷ 30 × 39
    assert v["decimo_terceiro_2026"] == Decimal("1500.00")  # jan–jun (23 dias) = 6/12
    assert v["ferias_proporcionais"] == Decimal("1000.00")  # 01/03 a 23/06 = 4/12
    assert v["ferias_proporcionais_terco"] == Decimal("333.33")
    assert v["fgts_rescisorio"] == Decimal("552.00")  # 8% × (1.500 + 1.500 + 3.900)
    # FGTS estimado: 38 meses × 240 + 13º de 2023 (10/12 → 200) + 2024 (240) + 2025 (240) = 9.800
    assert v["multa_fgts"] == Decimal("4140.80")  # 40% × (9.800 + 552)
    assert v["inss_mensal"] == Decimal("112.50")
    assert v["inss_13"] == Decimal("112.50")
    assert "irrf_mensal" not in v and "irrf_13" not in v
    assert r.total_proventos == Decimal("8233.33")
    assert r.liquido == Decimal("8008.33")
    assert r.total_fgts == Decimal("4692.80")


def test_saldo_fgts_informado_substitui_estimativa():
    r = calcular_rescisao(dados(saldo_fgts=Decimal("10000")))
    assert valores(r)["multa_fgts"] == Decimal("4220.80")  # 40% × (10.000 + 552)
    assert not any("estimado" in a for a in r.alertas)


def test_pedido_de_demissao_sem_cumprir_aviso():
    r = calcular_rescisao(
        dados(
            admissao=date(2025, 8, 10),
            desligamento=date(2026, 2, 20),
            modalidade=Modalidade.PEDIDO_DEMISSAO,
            aviso=Aviso.NAO_CUMPRIDO,
            salario=Decimal("2000"),
        )
    )
    v = valores(r)
    assert v["saldo_salario"] == Decimal("1333.33")
    assert "aviso_previo" not in v
    assert v["decimo_terceiro_2026"] == Decimal("333.33")  # jan + fev (20 dias) = 2/12
    assert v["ferias_proporcionais"] == Decimal("1000.00")  # menos de 1 ano: Súmula 261 → 6/12
    assert v["desconto_aviso"] == Decimal("2000.00")
    assert "multa_fgts" not in v
    assert r.liquido == Decimal("874.99")


def test_justa_causa_paga_ferias_vencidas_simples_e_em_dobro():
    r = calcular_rescisao(
        dados(
            admissao=date(2022, 1, 5),
            desligamento=date(2025, 3, 31),
            modalidade=Modalidade.JUSTA_CAUSA,
            aviso=Aviso.NAO_SE_APLICA,
            salario=Decimal("4000"),
            ferias_vencidas=2,
        )
    )
    v = valores(r)
    assert v["saldo_salario"] == Decimal("4000.00")  # mês completo = 30 dias
    # Período 05/01/2023–04/01/2024: concessivo venceu em 04/01/2025 → dobra
    assert v["ferias_vencidas_1"] == Decimal("8000.00")
    assert v["ferias_vencidas_1_terco"] == Decimal("2666.67")
    assert v["ferias_vencidas_2"] == Decimal("4000.00")
    assert not any(c.startswith(("decimo_terceiro", "ferias_proporcionais", "aviso")) for c in v)
    assert v["inss_mensal"] == Decimal("373.41")
    assert v["irrf_mensal"] == Decimal("133.84")  # tabela de fev/2024 ainda vigente em mar/2025
    assert r.liquido == Decimal("19492.75")


def test_13_respeita_admissao_no_mesmo_ano():
    # Admitido 01/10/2024, desligado 15/11/2024, aviso de 30 dias até 15/12/2024 → 3/12
    r = calcular_rescisao(dados(admissao=date(2024, 10, 1), desligamento=date(2024, 11, 15)))
    assert valores(r)["decimo_terceiro_2024"] == Decimal("750.00")


def test_projecao_do_aviso_para_o_ano_seguinte_gera_13_dos_dois_anos():
    # 5 anos completos → 45 dias; projeção de 10/12/2025 até 24/01/2026
    r = calcular_rescisao(dados(admissao=date(2020, 1, 1), desligamento=date(2025, 12, 10)))
    v = valores(r)
    assert v["decimo_terceiro_2025"] == Decimal("3000.00")  # 12/12
    assert v["decimo_terceiro_2026"] == Decimal("250.00")  # janeiro com 24 dias = 1/12
    assert any("dezembro" in a for a in r.alertas)


def test_acordo_paga_metade_do_aviso_e_multa_de_20():
    r = calcular_rescisao(dados(modalidade=Modalidade.ACORDO, saldo_fgts=Decimal("10000")))
    v = valores(r)
    assert v["aviso_previo"] == Decimal("1950.00")  # metade de 3.900
    assert v["decimo_terceiro_2026"] == Decimal("1500.00")  # 13º integral
    # FGTS rescisório: 8% × (1.500 + 1.500 + 1.950) = 396; multa 20% × 10.396
    assert v["fgts_rescisorio"] == Decimal("396.00")
    assert v["multa_fgts"] == Decimal("2079.20")


def test_culpa_reciproca_reduz_aviso_13_e_ferias_proporcionais_pela_metade():
    r = calcular_rescisao(dados(modalidade=Modalidade.CULPA_RECIPROCA, saldo_fgts=Decimal("10000")))
    v = valores(r)
    assert v["aviso_previo"] == Decimal("1950.00")
    assert v["decimo_terceiro_2026"] == Decimal("750.00")
    assert v["ferias_proporcionais"] == Decimal("500.00")


def test_aviso_trabalhado_indeniza_so_os_dias_proporcionais():
    # Aviso de 39 dias: 30 trabalhados (desligamento já é o fim do aviso) + 9 indenizados
    r = calcular_rescisao(dados(aviso=Aviso.TRABALHADO))
    assert valores(r)["aviso_previo"] == Decimal("900.00")
    assert r.resumo["Data projetada (OJ 82 SDI-1)"] == "24/05/2026"


def test_media_de_variaveis_integra_aviso_13_e_ferias_mas_nao_saldo():
    r = calcular_rescisao(dados(media_variaveis=Decimal("600")))
    v = valores(r)
    assert v["saldo_salario"] == Decimal("1500.00")
    assert v["aviso_previo"] == Decimal("4680.00")  # 3.600 ÷ 30 × 39
    assert v["decimo_terceiro_2026"] == Decimal("1800.00")


def test_faltas_reduzem_ferias_proporcionais_e_saldo():
    r = calcular_rescisao(dados(faltas_periodo_aquisitivo=10, faltas_mes_rescisao=2))
    v = valores(r)
    assert v["ferias_proporcionais"] == Decimal("800.00")  # 1.000 × 24/30
    assert v["saldo_salario"] == Decimal("1300.00")  # 13 dias


def test_multas_477_e_467():
    r = calcular_rescisao(dados(pagamento_em_atraso=True, multa_467=True, saldo_fgts=Decimal("10000")))
    v = valores(r)
    assert v["multa_477"] == Decimal("3000.00")
    # 467: 50% × (1.500 + 3.900 + 1.500 + 1.000 + 333,33 + 4.220,80) = 6.227,07 (arredondado)
    assert v["multa_467"] == Decimal("6227.07")


def test_historico_salarial_entra_na_estimativa_do_fgts():
    historico = [
        AlteracaoSalarial(date(2023, 3, 1), Decimal("2000")),
        AlteracaoSalarial(date(2025, 1, 1), Decimal("3000")),
    ]
    r = calcular_rescisao(dados(historico_salarial=historico))
    # 2023-03 a 2024-12: 22 meses × 160 = 3.520; 2025-01 a 2026-04: 16 × 240 = 3.840
    # 13º: 2023 (10/12 de 2.000 → 133,33), 2024 (160), 2025 (240) → total 7.893,33
    # multa: 40% × (7.893,33 + 552) = 3.378,13
    assert valores(r)["multa_fgts"] == Decimal("3378.13")


def test_admissao_em_29_de_fevereiro_nao_quebra():
    r = calcular_rescisao(dados(admissao=date(2024, 2, 29), desligamento=date(2025, 3, 10)))
    assert valores(r)["ferias_proporcionais"] > 0


def test_validacoes():
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_rescisao(dados(desligamento=date(2022, 1, 1)))
    assert "anterior à admissão" in str(erro.value)

    with pytest.raises(ErroDeEntrada) as erro:
        calcular_rescisao(dados(ferias_vencidas=4))
    assert "3 período(s)" in str(erro.value)

    with pytest.raises(ErroDeEntrada):
        calcular_rescisao(dados(modalidade=Modalidade.PEDIDO_DEMISSAO, aviso=Aviso.INDENIZADO))

    with pytest.raises(ErroDeEntrada) as erro:
        calcular_rescisao(dados(admissao=date(2015, 1, 1), desligamento=date(2018, 6, 30)))
    assert "Não há tabela" in str(erro.value)
