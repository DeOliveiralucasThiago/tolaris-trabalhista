"""Horas extras, adicional noturno e insalubridade/periculosidade com reflexos.

Valores esperados calculados à mão. Calendário usado no DSR (dias úteis / domingos e feriados):
jan/2022 25/6 (01/01 caiu no sábado), fev/2022 24/4, mar/2022 27/4;
jan/2025 26/5, fev/2025 24/4, mar/2025 26/5, abr/2025 25/5 (21/04).
"""

from datetime import date
from decimal import Decimal

import pytest

from tolaris.datas import dias_uteis_e_repousos
from tolaris.motor.horas_extras import calcular_pedidos, marco_prescricional
from tolaris.motor.modelos import (
    AdicionalOcupacional,
    Aviso,
    DadosPedidos,
    ErroDeEntrada,
    Modalidade,
    PeriodoJornada,
)


def valores(resultado) -> dict[str, Decimal]:
    return {item.codigo: item.valor for item in resultado.lancamentos}


def dados(ano=2022, horas=Decimal(20), **kwargs) -> DadosPedidos:
    padrao = dict(
        admissao=date(ano, 1, 1),
        desligamento=date(ano, 3, 31),
        modalidade=Modalidade.SEM_JUSTA_CAUSA,
        aviso=Aviso.INDENIZADO,
        salario=Decimal("2200"),  # valor-hora 10,00 com divisor 220
        periodos=[PeriodoJornada(date(ano, 1, 1), date(ano, 3, 31), horas_extras_1=horas)],
    )
    padrao.update(kwargs)
    return DadosPedidos(**padrao)


def test_calendario_do_dsr():
    assert dias_uteis_e_repousos(2022, 1) == (25, 6)
    assert dias_uteis_e_repousos(2025, 4) == (25, 5)
    assert dias_uteis_e_repousos(2024, 11) == (23, 7)  # 4 domingos + 02/11 (sáb), 15/11 (sex), 20/11 (qua)
    assert dias_uteis_e_repousos(2023, 11) == (24, 6)  # 20/11 ainda não era feriado nacional


def test_horas_extras_antes_de_2023_sem_dsr_nos_reflexos():
    # 20 h/mês × R$ 10,00 × 1,5 = R$ 300,00 por mês; aviso de 30 dias projeta abril/2022
    v = valores(calcular_pedidos(dados()))
    assert v["he_1"] == Decimal("900.00")
    # DSR: 300 × 6/25 = 72,00 + 300 × 4/24 = 50,00 + 300 × 4/27 = 44,44
    assert v["he_dsr"] == Decimal("166.44")
    # 13º: (60 h + 20 h da projeção) × 10 × 1,5 ÷ 12 = 100,00
    assert v["he_13"] == Decimal("100.00")
    assert v["he_ferias"] == Decimal("133.33")  # 100,00 × 4/3
    # Aviso: média de 20 h × 10 × 1,5 × 30/30
    assert v["he_aviso"] == Decimal("300.00")
    # FGTS: 8% × (900 + 166,44 + 100 + 300) = 117,32; multa 40%
    assert v["he_fgts"] == Decimal("117.32")
    assert v["he_multa_fgts"] == Decimal("46.93")


def test_a_partir_de_abril_de_2023_o_dsr_entra_nos_reflexos():
    # Horas de DSR: 20 × 5/26 + 20 × 4/24 + 20 × 5/26 + (projeção abr) 20 × 5/25 = 15,0256 h
    # 13º: (80 + 15,0256) × 10 × 1,5 ÷ 12 = 118,78
    v = valores(calcular_pedidos(dados(ano=2025)))
    assert v["he_dsr"] == Decimal("165.38")  # 57,69 + 50,00 + 57,69
    assert v["he_13"] == Decimal("118.78")
    assert v["he_ferias"] == Decimal("158.38")
    # Aviso: (60 + 11,0256) h ÷ 3 meses × 10 × 1,5 = 355,13
    assert v["he_aviso"] == Decimal("355.13")
    assert v["he_fgts"] == Decimal("123.14")


def test_horas_com_segundo_adicional():
    periodos = [PeriodoJornada(date(2022, 1, 1), date(2022, 3, 31), horas_extras_2=Decimal(8))]
    v = valores(calcular_pedidos(dados(periodos=periodos)))
    assert v["he_2"] == Decimal("480.00")  # 8 h × 10 × 2 × 3 meses


def test_adicional_noturno_com_hora_reduzida():
    periodos = [PeriodoJornada(date(2022, 1, 1), date(2022, 3, 31), horas_noturnas=Decimal(10))]
    r = calcular_pedidos(dados(periodos=periodos))
    # 10 h de relógio = 11,4286 h noturnas × 10 × 20% = 22,86 por mês
    assert valores(r)["noturno"] == Decimal("68.58")
    assert r.mensal[0].valor_noturno == Decimal("22.86")
    sem_reducao = calcular_pedidos(dados(periodos=periodos, hora_noturna_reduzida=False))
    assert valores(sem_reducao)["noturno"] == Decimal("60.00")


def test_insalubridade_devida_com_reflexos_e_integrando_as_horas_extras():
    r = calcular_pedidos(dados(ano=2025, adicional_ocupacional=AdicionalOcupacional.INSALUBRIDADE_MEDIO))
    v = valores(r)
    # 20% × salário mínimo de 2025 (1.518,00) = 303,60 por mês
    assert v["adicional"] == Decimal("910.80")
    assert "adicional_dsr" not in v  # OJ 103 da SDI-1
    assert v["adicional_13"] == Decimal("101.20")  # 4 meses (com a projeção) × 303,60 ÷ 12
    assert v["adicional_ferias"] == Decimal("134.93")
    assert v["adicional_aviso"] == Decimal("303.60")
    assert v["adicional_fgts"] == Decimal("105.25")  # 8% × (910,80 + 101,20 + 303,60)
    # Valor-hora com insalubridade: (2.200 + 303,60) ÷ 220 = 11,38 → 20 h × 11,38 × 1,5 = 341,40
    assert r.mensal[0].valor_he_1 == Decimal("341.40")
    assert set(r.por_pedido()) == {"Horas extras", "Adicional de insalubridade"}


def test_adicional_ja_pago_so_integra_a_base_das_horas_extras():
    r = calcular_pedidos(
        dados(ano=2025, adicional_ocupacional=AdicionalOcupacional.PERICULOSIDADE, adicional_ja_pago=True)
    )
    assert "adicional" not in valores(r)
    assert r.mensal[0].valor_he_1 == Decimal("390.00")  # (2.200 + 660) ÷ 220 = 13 × 1,5 × 20


def test_prescricao_quinquenal_proporcional_no_primeiro_mes():
    assert marco_prescricional(date(2026, 3, 15)) == date(2021, 3, 15)
    r = calcular_pedidos(
        dados(
            admissao=date(2015, 1, 1),
            desligamento=date(2025, 6, 30),
            data_ajuizamento=date(2026, 3, 15),
            periodos=[PeriodoJornada(date(2015, 1, 1), date(2025, 6, 30), horas_extras_1=Decimal(10))],
        )
    )
    primeiro = r.mensal[0]
    assert primeiro.competencia == date(2021, 3, 1)
    assert primeiro.fracao == Decimal(17) / 30  # 15 a 31/03
    assert any("prescritas" in alerta for alerta in r.alertas)


def test_prescricao_bienal_e_validacoes():
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_pedidos(dados(data_ajuizamento=date(2024, 4, 1)))
    assert "bienal" in str(erro.value)
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_pedidos(dados(periodos=[]))
    assert "ao menos um pedido" in str(erro.value)


def test_justa_causa_sem_aviso_sem_13_e_ferias_proporcionais_do_ultimo_periodo():
    v = valores(calcular_pedidos(dados(modalidade=Modalidade.JUSTA_CAUSA, aviso=Aviso.NAO_SE_APLICA)))
    assert v["he_1"] == Decimal("900.00")
    assert not any(c in v for c in ("he_13", "he_ferias", "he_aviso", "he_multa_fgts"))


def test_culpa_reciproca_reduz_reflexos_do_ultimo_periodo():
    v = valores(calcular_pedidos(dados(modalidade=Modalidade.CULPA_RECIPROCA)))
    assert v["he_13"] == Decimal("50.00")
    assert v["he_aviso"] == Decimal("150.00")


def test_periodo_fora_do_contrato_e_recortado():
    periodos = [PeriodoJornada(date(2021, 6, 1), date(2022, 12, 31), horas_extras_1=Decimal(20))]
    r = calcular_pedidos(dados(periodos=periodos))
    assert valores(r)["he_1"] == Decimal("900.00")
    assert any("ultrapassa o contrato" in alerta for alerta in r.alertas)


def _contrato_antigo(**kwargs):
    padrao = dict(
        admissao=date(2015, 1, 1),
        desligamento=date(2023, 6, 30),
        periodos=[PeriodoJornada(date(2015, 1, 1), date(2023, 6, 30), horas_extras_1=Decimal(10))],
    )
    padrao.update(kwargs)
    return dados(**padrao)


def test_interrupcao_da_prescricao_conta_os_5_anos_da_acao_anterior():
    # Ação anterior em 10/03/2024 (dentro do biênio): marco em 10/03/2019, mesmo com esta ação
    # ajuizada em 2026, mais de 2 anos após o fim do contrato
    r = calcular_pedidos(
        _contrato_antigo(data_ajuizamento=date(2026, 10, 8), data_interrupcao_prescricao=date(2024, 3, 10))
    )
    assert r.mensal[0].competencia == date(2019, 3, 1)
    assert r.mensal[0].fracao == Decimal(22) / 30  # 10 a 31/03
    assert r.resumo["Marco prescricional"] == "10/03/2019"
    assert any("Súmula 268" in alerta for alerta in r.alertas)


def test_sem_interrupcao_a_mesma_acao_esta_prescrita_e_o_erro_sugere_informar():
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_pedidos(_contrato_antigo(data_ajuizamento=date(2026, 10, 8)))
    assert "bienal" in str(erro.value) and "interrupção" in str(erro.value)


def test_interrupcao_fora_do_bienio_ou_depois_do_ajuizamento_e_recusada():
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_pedidos(
            _contrato_antigo(data_ajuizamento=date(2026, 10, 8), data_interrupcao_prescricao=date(2025, 8, 1))
        )
    assert "mais de 2 anos" in str(erro.value)
    with pytest.raises(ErroDeEntrada) as erro:
        calcular_pedidos(
            _contrato_antigo(data_ajuizamento=date(2024, 1, 10), data_interrupcao_prescricao=date(2024, 3, 10))
        )
    assert "anterior ao ajuizamento" in str(erro.value)


def test_contrato_desde_2005_com_insalubridade_usa_salario_minimo_da_epoca():
    r = calcular_pedidos(
        dados(
            admissao=date(2005, 3, 1),
            desligamento=date(2006, 6, 30),
            periodos=[],
            adicional_ocupacional=AdicionalOcupacional.INSALUBRIDADE_MAXIMO,
        )
    )
    meses = {linha.competencia: linha.valor_adicional for linha in r.mensal}
    assert meses[date(2005, 3, 1)] == Decimal("104.00")  # 40% × R$ 260,00
    assert meses[date(2005, 5, 1)] == Decimal("120.00")  # 40% × R$ 300,00 (desde 01/05/2005)
    assert meses[date(2006, 4, 1)] == Decimal("140.00")  # 40% × R$ 350,00 (desde 01/04/2006)
