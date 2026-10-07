"""Correção monetária e juros com índices fictícios, para conferência à mão.

Índices de teste (todos os meses): IPCA-E 1%, TR 0,1%, SELIC 1%, IPCA 0,5%, taxa legal 0,5%.
"""

from datetime import date
from decimal import Decimal

import pytest

from tolaris.datas import meses_entre
from tolaris.motor.atualizacao import ParametrosAtualizacao, atualizar, fator_mensal
from tolaris.motor.horas_extras import calcular_pedidos
from tolaris.motor.modelos import (
    Aviso,
    DadosPedidos,
    ErroDeEntrada,
    Grupo,
    Lancamento,
    Modalidade,
    PeriodoJornada,
    ResultadoCalculo,
)
from tolaris.tabelas import Indices, indices

TAXAS = {"ipca_e": "0.01", "tr": "0.001", "selic": "0.01", "ipca": "0.005", "taxa_legal": "0.005"}
INDICES = Indices(
    {
        serie: {f"{mes:%Y-%m}": Decimal(taxa) for mes in meses_entre(date(2015, 1, 1), date(2026, 8, 31))}
        for serie, taxa in TAXAS.items()
    }
)


def resultado_simples(valor="1000", competencia=date(2022, 1, 1), grupo=Grupo.PROVENTO) -> ResultadoCalculo:
    item = Lancamento(
        "x", "Verba", grupo, Decimal(valor), "Salarial", "", "", parcelas=((competencia, Decimal(valor)),)
    )
    return ResultadoCalculo("Teste", [item], [], {})


def atualizado(resultado, ate, ajuizamento=None, juros_pre=True):
    parametros = ParametrosAtualizacao(ate, ajuizamento, juros_pre)
    return atualizar(resultado, parametros, date(2022, 1, 1), INDICES)


def test_fase_pre_judicial_antes_da_lei_14905():
    # Competência 01/2022 → índices de fev, mar e abr (Súmula 381); atualização em 10/05/2022
    linha = atualizado(resultado_simples(), date(2022, 5, 10)).linhas[0].valores
    assert linha.correcao == Decimal("30.30")  # 1,01³ − 1 = 3,0301%
    assert linha.juros == Decimal("3.09")  # 1.030,30 × (0,1% × 3)
    assert linha.selic == 0
    assert linha.total == Decimal("1033.39")


def test_fase_judicial_selic_sem_somar_outro_indice():
    # Ajuizamento em 15/03/2022: fevereiro pré-judicial; março e abril com SELIC
    linha = atualizado(resultado_simples(), date(2022, 5, 10), ajuizamento=date(2022, 3, 15)).linhas[0].valores
    assert linha.correcao == Decimal("10.00")  # IPCA-E de fevereiro
    assert linha.juros == Decimal("1.01")  # TR de fevereiro sobre 1.010,00
    assert linha.selic == Decimal("20.20")  # (1% + 1%) × 1.010,00
    assert linha.total == Decimal("1031.21")


def test_travessia_de_30_08_2024():
    # Competência 06/2024: jul e ago pelo regime antigo (IPCA-E + TR); set e out pelo IPCA + taxa legal.
    # Até ago: 1,01² = 1,0201; TR 0,2% → base consolidada 1,0201 × 1,002 = 1,0221402
    # Set-out: × 1,005² → 1,03238716; juros taxa legal 1% sobre 1,03238716
    correcao, selic, juros, total = fator_mensal(date(2024, 7, 1), date(2024, 11, 1), None, True, INDICES)
    assert round(correcao, 8) == Decimal("0.03034696")
    assert selic == 0
    assert round(juros, 8) == Decimal("0.01236407")  # 0,0020402 + 0,0103238716
    assert round(total, 8) == Decimal("1.04271103")


def test_sem_juros_pre_judiciais():
    correcao, selic, juros, total = fator_mensal(date(2024, 7, 1), date(2024, 11, 1), None, False, INDICES)
    assert juros == 0
    assert round(total, 8) == Decimal("1.03032650")  # 1,01² × 1,005² = 1,0201 × 1,010025


def test_depois_da_lei_14905_fase_judicial():
    # Ajuizada em 2023: SELIC até ago/2024; depois IPCA + taxa legal sobre o valor consolidado
    correcao, selic, juros, _ = fator_mensal(date(2024, 7, 1), date(2024, 10, 1), date(2023, 1, 10), True, INDICES)
    assert selic == Decimal("0.02")  # jul e ago
    assert round(correcao, 6) == Decimal("0.005100")  # 1,02 × 0,5% (set)
    assert round(juros, 6) == Decimal("0.005126")  # 1,0251 × 0,5%


def test_competencia_do_proprio_mes_nao_e_corrigida():
    linha = atualizado(resultado_simples(competencia=date(2022, 4, 1)), date(2022, 5, 10)).linhas[0].valores
    assert linha.total == Decimal("1000.00")


def test_descontos_nao_sao_atualizados():
    resultado = resultado_simples()
    resultado.lancamentos.append(Lancamento("inss", "INSS", Grupo.DESCONTO, Decimal("100"), "Tributária", "", ""))
    r = atualizado(resultado, date(2022, 5, 10))
    assert r.descontos == Decimal("100")
    assert r.total == Decimal("933.39")


def test_alerta_quando_faltam_indices():
    r = atualizado(resultado_simples(), date(2026, 12, 15))
    assert r.atualizado_ate == date(2026, 9, 1)
    assert any("até 08/2026" in alerta for alerta in r.alertas)


def test_competencia_sem_indice_gera_erro_claro():
    with pytest.raises(ErroDeEntrada) as erro:
        atualizado(resultado_simples(competencia=date(2010, 1, 1)), date(2022, 5, 10))
    assert "02/2010" in str(erro.value)


def test_atualiza_pedidos_por_competencia():
    dados = DadosPedidos(
        date(2022, 1, 1),
        date(2022, 3, 31),
        Modalidade.SEM_JUSTA_CAUSA,
        Aviso.INDENIZADO,
        Decimal("2200"),
        periodos=[PeriodoJornada(date(2022, 1, 1), date(2022, 3, 31), horas_extras_1=Decimal(20))],
    )
    resultado = calcular_pedidos(dados)
    r = atualizar(resultado, ParametrosAtualizacao(date(2022, 5, 10)), date(2022, 3, 1), INDICES)
    horas = next(linha for linha in r.linhas if linha.codigo == "he_1").valores
    # 300 de jan (fev-abr: 3 meses), 300 de fev (mar-abr), 300 de mar (abr)
    # correção: 300 × (0,030301 + 0,0201 + 0,01) = 18,1203 → 18,12
    assert horas.correcao == Decimal("18.12")
    assert r.soma().original == resultado.total_geral
    assert set(r.por_pedido()) == {"Horas extras"}


def test_tabela_real_de_indices_quando_disponivel():
    try:
        tabela = indices()
    except Exception:
        pytest.skip("indices.json ainda não foi baixado do Banco Central")
    # Conferência com números oficiais: IPCA 2023 = 4,62%; IPCA 2024 = 4,83%
    for ano, esperado in ((2023, Decimal("4.62")), (2024, Decimal("4.83"))):
        fator = Decimal(1)
        for mes in meses_entre(date(ano, 1, 1), date(ano, 12, 1)):
            fator *= 1 + tabela.valor("ipca", mes)
        assert round((fator - 1) * 100, 2) == esperado
