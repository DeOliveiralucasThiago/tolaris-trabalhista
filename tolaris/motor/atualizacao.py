"""Correção monetária e juros dos créditos trabalhistas.

Critério padrão: ADC 58/59 do STF (com os embargos de declaração) e Lei nº 14.905/2024, na
forma fixada pela SDI-1 do TST (E-ED-RR-713-03.2010.5.04.0029, 17/10/2024):

- até 29/08/2024, fase pré-judicial: IPCA-E + juros do art. 39, caput, da Lei nº 8.177/1991 (TR);
- até 29/08/2024, do ajuizamento em diante: SELIC (correção e juros juntos);
- a partir de 30/08/2024: correção pelo IPCA (art. 389, parágrafo único, CC) e juros pela taxa
  legal = SELIC − IPCA, com piso zero (art. 406, CC; Resolução CMN nº 5.171/2024).

Regras de cálculo detalhadas em `regras/atualizacao.md`.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from tolaris.datas import formatar_data, primeiro_dia_do_mes, somar_meses
from tolaris.dinheiro import ZERO, arredondar, formatar_brl
from tolaris.motor.modelos import ErroDeEntrada, Grupo, ResultadoCalculo
from tolaris.tabelas import Indices, TabelaIndisponivel, indices

INICIO_LEI_14905 = date(2024, 9, 1)  # 30/08/2024: simplificação mensal, a partir da competência 09/2024
UM = Decimal(1)
SERIES_NECESSARIAS = ("ipca_e", "tr", "selic", "ipca", "taxa_legal")


@dataclass(frozen=True)
class ParametrosAtualizacao:
    data_atualizacao: date
    data_ajuizamento: date | None = None  # None ou data futura: todo o período é pré-judicial
    juros_pre_judiciais: bool = True


@dataclass(frozen=True)
class Componentes:
    original: Decimal = ZERO
    correcao: Decimal = ZERO  # IPCA-E e IPCA
    selic: Decimal = ZERO  # fase judicial até 29/08/2024 (correção + juros)
    juros: Decimal = ZERO  # TR (pré-judicial até 29/08/2024) e taxa legal (desde 30/08/2024)

    @property
    def total(self) -> Decimal:
        return self.original + self.correcao + self.selic + self.juros

    def __add__(self, outro: "Componentes") -> "Componentes":
        return Componentes(
            self.original + outro.original,
            self.correcao + outro.correcao,
            self.selic + outro.selic,
            self.juros + outro.juros,
        )

    def arredondado(self) -> "Componentes":
        return Componentes(
            arredondar(self.original), arredondar(self.correcao), arredondar(self.selic), arredondar(self.juros)
        )


@dataclass(frozen=True)
class LinhaAtualizada:
    codigo: str
    descricao: str
    pedido: str
    grupo: Grupo
    valores: Componentes


@dataclass
class ResultadoAtualizacao:
    parametros: ParametrosAtualizacao
    linhas: list[LinhaAtualizada]
    descontos: Decimal  # descontos (INSS, IR etc.) não são atualizados
    atualizado_ate: date  # 1º dia do mês até onde os índices foram aplicados
    criterio: list[str]
    alertas: list[str] = field(default_factory=list)

    def soma(self, grupo: Grupo | None = None) -> Componentes:
        total = Componentes()
        for linha in self.linhas:
            if grupo is None or linha.grupo == grupo:
                total += linha.valores
        return total

    def por_pedido(self) -> dict[str, Componentes]:
        totais: dict[str, Componentes] = {}
        for linha in self.linhas:
            totais[linha.pedido] = totais.get(linha.pedido, Componentes()) + linha.valores
        return totais

    @property
    def total(self) -> Decimal:
        return self.soma().total - self.descontos


def fator_mensal(
    competencia_inicial: date,
    ate: date,
    ajuizamento: date | None,
    juros_pre_judiciais: bool,
    tabela: Indices,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Aplica os índices mês a mês a R$ 1,00 devido a partir de `competencia_inicial`.

    Devolve (correção, selic, juros, total) para cada R$ 1,00 de valor original.
    `ate` é o 1º dia do mês final (exclusivo): os índices aplicados vão de
    `competencia_inicial` até o mês anterior a `ate`.
    """

    def indice(serie: str, mes: date) -> Decimal:
        valor = tabela.valor(serie, mes)
        if valor is None:
            raise TabelaIndisponivel(f"Não há índice {serie.upper().replace('_', '-')} para {mes:%m/%Y} na tabela.")
        return valor

    mes_ajuizamento = primeiro_dia_do_mes(ajuizamento) if ajuizamento else None
    corrigido = UM  # principal corrigido (fase até 29/08/2024)
    soma_tr = soma_selic = soma_legal = Decimal(0)
    consolidado = None  # base a partir de 30/08/2024
    base_inicial = None
    mes = competencia_inicial
    while mes < ate:
        judicial = mes_ajuizamento is not None and mes >= mes_ajuizamento
        if mes < INICIO_LEI_14905:
            if judicial:
                soma_selic += indice("selic", mes)
            else:
                corrigido *= UM + indice("ipca_e", mes)
                if juros_pre_judiciais:
                    soma_tr += indice("tr", mes)
        else:
            if consolidado is None:
                consolidado = corrigido * (UM + soma_tr + soma_selic)
                base_inicial = consolidado
            consolidado *= UM + indice("ipca", mes)
            if judicial or juros_pre_judiciais:
                soma_legal += indice("taxa_legal", mes)
        mes = somar_meses(mes, 1)

    correcao = corrigido - UM
    selic = corrigido * soma_selic
    juros = corrigido * soma_tr
    if consolidado is not None:
        correcao += consolidado - base_inicial
        juros += consolidado * soma_legal
    return correcao, selic, juros, UM + correcao + selic + juros


def _ultimo_mes_comum(tabela: Indices) -> date:
    ultimos = [tabela.ultimo_mes(serie) for serie in SERIES_NECESSARIAS]
    if any(u is None for u in ultimos):
        raise TabelaIndisponivel("A tabela de índices está incompleta.")
    return min(ultimos)


def atualizar(
    resultado: ResultadoCalculo,
    parametros: ParametrosAtualizacao,
    competencia_padrao: date,
    tabela: Indices | None = None,
) -> ResultadoAtualizacao:
    """Atualiza proventos e FGTS do resultado. `competencia_padrao` é usada para lançamentos
    sem composição mensal (em regra, o mês do desligamento)."""
    try:
        tabela = tabela or indices()
        ultimo = _ultimo_mes_comum(tabela)
    except TabelaIndisponivel as erro:
        raise ErroDeEntrada([str(erro)]) from erro

    alertas = []
    ate = primeiro_dia_do_mes(parametros.data_atualizacao)
    limite = somar_meses(ultimo, 1)
    if ate > limite:
        alertas.append(
            f"Os índices disponíveis vão até {ultimo:%m/%Y}: a atualização foi feita até {formatar_data(limite)}, "
            f"e não até {formatar_data(parametros.data_atualizacao)}."
        )
        ate = limite

    fatores: dict[date, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    linhas = []
    descontos = ZERO
    for item in resultado.lancamentos:
        if item.grupo == Grupo.DESCONTO:
            descontos += item.valor
            continue
        parcelas = item.parcelas or ((competencia_padrao, item.valor),)
        valores = Componentes()
        for competencia, valor in parcelas:
            # Época própria: mês seguinte à competência (Súmula 381 do TST)
            inicio = somar_meses(primeiro_dia_do_mes(competencia), 1)
            if inicio not in fatores:
                try:
                    fatores[inicio] = fator_mensal(
                        inicio, ate, parametros.data_ajuizamento, parametros.juros_pre_judiciais, tabela
                    )
                except TabelaIndisponivel as erro:
                    raise ErroDeEntrada([str(erro)]) from erro
            correcao, selic, juros, _ = fatores[inicio]
            valores += Componentes(valor, valor * correcao, valor * selic, valor * juros)
        valores = valores.arredondado()
        # O valor original é o do lançamento (as parcelas podem ter centavos não arredondados)
        valores = Componentes(item.valor, valores.correcao, valores.selic, valores.juros)
        linhas.append(LinhaAtualizada(item.codigo, item.descricao, item.pedido, item.grupo, valores))

    return ResultadoAtualizacao(parametros, linhas, descontos, ate, _criterio(parametros, ate), alertas)


def _criterio(p: ParametrosAtualizacao, ate: date) -> list[str]:
    linhas = [
        f"Valores atualizados até {formatar_data(ate)}, a partir do mês seguinte a cada competência "
        "(Súmula 381 do TST).",
        "Até 29/08/2024, fase pré-judicial: IPCA-E"
        + (" + juros da TR (art. 39, caput, Lei nº 8.177/1991)" if p.juros_pre_judiciais else " (sem juros)")
        + "; fase judicial: SELIC (ADC 58 do STF).",
        "A partir de 30/08/2024: IPCA (art. 389, parágrafo único, CC) e juros pela taxa legal, SELIC − IPCA "
        "com piso zero (art. 406, CC; Resolução CMN nº 5.171/2024), conforme a SDI-1 do TST "
        "(E-ED-RR-713-03.2010.5.04.0029)" + ("" if p.juros_pre_judiciais else "; sem juros antes do ajuizamento") + ".",
        "Correção composta mês a mês; SELIC, TR e taxa legal somadas (juros simples, Súmula 121 do STF).",
    ]
    if p.data_ajuizamento and p.data_ajuizamento < ate:
        linhas.append(f"Ajuizamento em {formatar_data(p.data_ajuizamento)} (início da fase judicial).")
    else:
        linhas.append("Todo o período foi tratado como fase pré-judicial (ação ainda não ajuizada).")
    linhas.append("Descontos (INSS, IR e outros) não são atualizados.")
    return linhas


def resumo_texto(atualizado: ResultadoAtualizacao) -> str:
    total = atualizado.soma()
    return (
        f"Original {formatar_brl(total.original)} + correção {formatar_brl(total.correcao)} + SELIC "
        f"{formatar_brl(total.selic)} + juros {formatar_brl(total.juros)} = {formatar_brl(total.total)}"
    )
