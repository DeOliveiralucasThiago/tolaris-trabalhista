"""Liquidação de sentença.

Junta as verbas deferidas (rescisórias e horas extras/adicionais), deduz os valores já pagos,
atualiza tudo e apura INSS, imposto de renda, honorários e custas. Regras detalhadas em
`regras/liquidacao.md`.
"""

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from tolaris.datas import (
    avos_no_ano,
    formatar_data,
    fracao_do_mes,
    primeiro_dia_do_mes,
    somar_meses,
    ultimo_dia_do_mes,
)
from tolaris.dinheiro import ZERO, arredondar, formatar_brl, formatar_percentual
from tolaris.motor.atualizacao import ParametrosAtualizacao, ResultadoAtualizacao, atualizar, fator_mensal
from tolaris.motor.contrato import ALIQUOTA_FGTS, MULTA_FGTS, salario_em
from tolaris.motor.horas_extras import calcular_pedidos
from tolaris.motor.modelos import (
    DadosLiquidacao,
    ErroDeEntrada,
    Grupo,
    Lancamento,
    NaturezaPagamento,
    ResultadoPedidos,
    VerbaRescisoria,
)
from tolaris.motor.rescisao import calcular_rescisao
from tolaris.motor.tributos import ResultadoIRRF, calcular_inss, calcular_irrf, calcular_irrf_rra
from tolaris.tabelas import (
    Indices,
    TabelaIndisponivel,
    aviso_tabela_desatualizada,
    indices,
    inss_vigente,
    tabelas_inss,
)

PEDIDO_RESCISORIAS = "Verbas rescisórias"
PEDIDO_DEDUCOES = "Valores pagos (dedução)"
PEDIDO_OUTRAS = "Outras verbas"
COTA_EMPRESA = Decimal("0.20")  # art. 22, I, Lei nº 8.212/1991
# Súmula 368, V, do TST: para o trabalho a partir de 05/03/2009, juros e multa contam da prestação
# dos serviços. Simplificação: competências a partir de 03/2009.
INICIO_REGIME_COMPETENCIA = date(2009, 3, 1)
JUROS_MES_DO_PAGAMENTO = Decimal("0.01")  # art. 61, § 3º, Lei nº 9.430/1996
MULTA_DIARIA = Decimal("0.0033")  # art. 61, caput e § 2º, Lei nº 9.430/1996
MULTA_MAXIMA = Decimal("0.20")
CUSTAS = Decimal("0.02")  # art. 789, I, CLT
CUSTAS_MINIMO = Decimal("10.64")
SALARIAL = "Salarial"
CRITERIO_SELIC = "SELIC (Súmula 368, V)"
CRITERIO_TRABALHISTA = "Índices trabalhistas"


def verba_rescisoria(codigo: str) -> VerbaRescisoria | None:
    """Grupo de verba rescisória a que pertence um lançamento de `calcular_rescisao`."""
    if codigo.startswith("decimo_terceiro_") and codigo != "decimo_terceiro_pago":
        return VerbaRescisoria.DECIMO_TERCEIRO
    if codigo.startswith("ferias"):
        return VerbaRescisoria.FERIAS
    if codigo in ("fgts_rescisorio", "multa_fgts"):
        return VerbaRescisoria.FGTS
    try:
        return VerbaRescisoria(codigo)
    except ValueError:
        return None


@dataclass(frozen=True)
class LinhaINSS:
    """Contribuição de uma competência (regime de competência, Súmula 368, IV e V, do TST)."""

    competencia: date
    decimo_terceiro: bool
    base_devida: Decimal  # verbas salariais deferidas na competência
    base_paga: Decimal  # salário já pago no mês (para as faixas e o teto)
    segurado: Decimal  # cota do empregado (valor histórico)
    empresa: Decimal  # cota patronal + RAT + terceiros (valor histórico)
    criterio: str
    fator: Decimal  # acréscimo sobre o valor histórico (juros SELIC ou atualização trabalhista)
    multa: Decimal = ZERO  # multa de mora (fração), depois de vencido o prazo da citação

    @property
    def valor_juros(self) -> Decimal:
        return arredondar((self.segurado + self.empresa) * self.fator)

    @property
    def valor_multa(self) -> Decimal:
        return arredondar((self.segurado + self.empresa) * self.multa)

    @property
    def acrescimos(self) -> Decimal:
        return self.valor_juros + self.valor_multa


@dataclass(frozen=True)
class ImpostoRenda:
    acumulado: ResultadoIRRF | None  # anos anteriores ao da liquidação (art. 12-A)
    meses: int  # NM do cálculo acumulado
    ano_corrente: ResultadoIRRF | None  # ano da liquidação (art. 12-B)

    @property
    def valor(self) -> Decimal:
        return sum((r.valor for r in (self.acumulado, self.ano_corrente) if r), ZERO)

    @property
    def rendimento(self) -> Decimal:
        return sum((r.rendimento for r in (self.acumulado, self.ano_corrente) if r), ZERO)

    @property
    def memoria(self) -> str:
        partes = []
        if self.acumulado:
            partes.append("Anos anteriores (art. 12-A da Lei nº 7.713/1988): " + self.acumulado.memoria)
        if self.ano_corrente:
            partes.append(
                "Ano da liquidação (art. 12-B da Lei nº 7.713/1988), tabela mensal sobre o total: "
                + self.ano_corrente.memoria
            )
        return " ".join(partes) or "Não há verbas tributáveis."


@dataclass
class ResultadoLiquidacao(ResultadoPedidos):
    dados_liquidacao: DadosLiquidacao | None = None
    atualizado: ResultadoAtualizacao | None = None
    inss: list[LinhaINSS] = field(default_factory=list)
    irrf: ImpostoRenda | None = None
    honorarios: Decimal = ZERO  # devidos pela reclamada ao advogado do reclamante
    honorarios_reclamante: Decimal = ZERO  # devidos pelo reclamante ao advogado da reclamada
    honorarios_reclamante_suspensos: bool = False
    custas: Decimal = ZERO
    honorarios_periciais: Decimal = ZERO
    periciais_do_reclamante: bool = False  # descontados do crédito do reclamante
    periciais_pela_uniao: bool = False  # reclamante com justiça gratuita (art. 790-B, § 4º, CLT)
    pensao: Decimal = ZERO
    pagamentos: list[tuple[str, Decimal]] = field(default_factory=list)  # (descrição, valor atualizado)
    # (seção, rótulo, valor, destaque)
    quadro: list[tuple[str, str, Decimal, bool]] = field(default_factory=list)

    @property
    def inss_segurado(self) -> Decimal:
        return sum((linha.segurado for linha in self.inss), ZERO)

    @property
    def inss_empresa(self) -> Decimal:
        return sum((linha.empresa for linha in self.inss), ZERO)

    @property
    def inss_acrescimos(self) -> Decimal:
        return sum((linha.acrescimos for linha in self.inss), ZERO)

    @property
    def bruto_atualizado(self) -> Decimal:
        """Verbas deferidas atualizadas, sem FGTS."""
        return self.atualizado.soma(Grupo.PROVENTO).total

    @property
    def fgts_atualizado(self) -> Decimal:
        return self.atualizado.soma(Grupo.FGTS).total

    @property
    def periciais_descontados(self) -> Decimal:
        return self.honorarios_periciais if self.periciais_do_reclamante else ZERO

    @property
    def periciais_reclamada(self) -> Decimal:
        if self.periciais_do_reclamante or self.periciais_pela_uniao:
            return ZERO
        return self.honorarios_periciais

    @property
    def liquido_reclamante(self) -> Decimal:
        descontos = self.inss_segurado + self.irrf.valor + self.pensao + self.periciais_descontados
        if not self.honorarios_reclamante_suspensos:
            descontos += self.honorarios_reclamante
        return self.bruto_atualizado - descontos

    @property
    def total_reclamada(self) -> Decimal:
        """Tudo o que a reclamada paga. INSS do reclamante, IR, pensão e honorários retidos já estão
        dentro das verbas, pois saem do crédito do reclamante."""
        return (
            self.bruto_atualizado
            + self.fgts_atualizado
            + self.inss_empresa
            + self.inss_acrescimos
            + self.honorarios
            + self.custas
            + self.periciais_reclamada
        )

    @property
    def total_pagamentos(self) -> Decimal:
        return sum((valor for _, valor in self.pagamentos), ZERO)

    @property
    def saldo_reclamada(self) -> Decimal:
        return self.total_reclamada - self.total_pagamentos


def calcular_liquidacao(dados: DadosLiquidacao, tabela: Indices | None = None) -> ResultadoLiquidacao:
    _validar(dados)
    try:
        tabela = tabela or indices()
    except TabelaIndisponivel as erro:
        raise ErroDeEntrada([str(erro)]) from erro
    return _Liquidacao(dados, tabela).executar()


def _validar(d: DadosLiquidacao) -> None:
    erros = []
    if d.rescisao is None and d.pedidos is None and not d.outras_verbas:
        erros.append("Marque ao menos um grupo de verbas deferidas na sentença.")
    if d.rescisao is not None and not d.verbas_rescisorias:
        erros.append("Escolha quais verbas rescisórias a sentença deferiu.")
    contrato = d.rescisao or d.pedidos or d.contrato
    if contrato is None:
        erros.append("Informe os dados do contrato.")
    if contrato is not None and d.data_ajuizamento < contrato.admissao:
        erros.append("A data do ajuizamento não pode ser anterior à admissão.")
    if d.data_liquidacao < d.data_ajuizamento:
        erros.append("A data da liquidação não pode ser anterior ao ajuizamento.")
    for i, pago in enumerate(d.valores_pagos, start=1):
        if pago.valor <= 0:
            erros.append(f"Valor pago {i}: informe um valor positivo.")
    for i, verba in enumerate(d.outras_verbas, start=1):
        if verba.valor <= 0:
            erros.append(f"Outra verba {i}: informe um valor positivo.")
        if verba.competencia is None and not verba.dano_moral:
            erros.append(f"Outra verba {i}: informe a competência (mês a que se refere).")
    for i, pagamento in enumerate(d.pagamentos, start=1):
        if pagamento.valor <= 0:
            erros.append(f"Pagamento {i}: informe um valor positivo.")
        if pagamento.data > d.data_liquidacao:
            erros.append(f"Pagamento {i}: a data é posterior à da liquidação.")
    if d.pensao_percentual > 1:
        erros.append("A pensão alimentícia não pode passar de 100%.")
    for valor, nome in (
        (d.aliquota_rat, "RAT"),
        (d.aliquota_terceiros, "terceiros"),
        (d.honorarios_percentual, "honorários"),
        (d.honorarios_reclamante_percentual, "honorários devidos pelo reclamante"),
        (d.honorarios_reclamante_base, "base dos honorários devidos pelo reclamante"),
        (d.honorarios_periciais, "honorários periciais"),
        (d.pensao_percentual, "pensão alimentícia"),
        (d.honorarios_contratuais_percentual, "honorários contratuais"),
    ):
        if valor < 0:
            erros.append(f"O percentual ou valor de {nome} não pode ser negativo.")
    if d.custas_informadas is not None and d.custas_informadas < 0:
        erros.append("As custas não podem ser negativas.")
    if erros:
        raise ErroDeEntrada(erros)


class _Liquidacao:
    def __init__(self, dados: DadosLiquidacao, tabela: Indices):
        self.d = dados
        self.tabela = tabela
        contrato = dados.rescisao or dados.pedidos or dados.contrato
        self.admissao = contrato.admissao
        self.desligamento = contrato.desligamento
        self.modalidade = contrato.modalidade
        self.salario = contrato.salario
        self.historico = contrato.historico_salarial
        self.mes_desligamento = primeiro_dia_do_mes(contrato.desligamento)
        self.lancamentos: list[Lancamento] = []
        self.alertas: list[str] = []
        self.resumo: dict[str, str] = {}
        self.mensal = []

    # ------------------------------------------------------------------ verbas

    def _verbas_rescisorias(self):
        d = self.d
        resultado = calcular_rescisao(d.rescisao, com_tributos=False)
        self.alertas += resultado.alertas
        self.resumo.update(resultado.resumo)
        for item in resultado.lancamentos:
            if item.grupo != Grupo.DESCONTO:
                if verba_rescisoria(item.codigo) in d.verbas_rescisorias:
                    self.lancamentos.append(replace(item, pedido=PEDIDO_RESCISORIAS))
                continue
            # Descontos da rescisão: INSS e IR são apurados de novo na liquidação; as deduções viram
            # valores negativos, atualizados como as verbas.
            if item.codigo == "decimo_terceiro_pago":
                if VerbaRescisoria.DECIMO_TERCEIRO not in d.verbas_rescisorias:
                    continue
                natureza, descricao = SALARIAL, "(−) 13º salário já pago (adiantamento)"
                codigo = "deducao_decimo_terceiro"
            elif item.codigo in ("desconto_aviso", "outros_descontos"):
                natureza, descricao, codigo = "Dedução", f"(−) {item.descricao}", f"deducao_{item.codigo}"
            else:
                continue
            self.lancamentos.append(
                Lancamento(
                    codigo,
                    descricao,
                    Grupo.PROVENTO,
                    -item.valor,
                    natureza,
                    item.formula,
                    item.fundamento,
                    pedido=PEDIDO_DEDUCOES,
                )
            )

    def _verbas_pedidos(self):
        resultado = calcular_pedidos(self.d.pedidos)
        alertas = resultado.alertas
        if self.d.pedidos.data_ajuizamento is None:
            alertas = [a for a in alertas if not a.startswith("Sem data de ajuizamento")]
            alertas.append("Prescrição quinquenal não aplicada (não pronunciada na sentença): contrato inteiro.")
        self.alertas += alertas
        self.resumo.update(resultado.resumo)
        self.lancamentos += resultado.lancamentos
        self.mensal = resultado.mensal

    def _valores_pagos(self):
        multa = MULTA_FGTS.get(self.modalidade)
        for i, pago in enumerate(self.d.valores_pagos, start=1):
            competencia = primeiro_dia_do_mes(pago.competencia)
            natureza = "Indenizatória" if pago.natureza == NaturezaPagamento.INDENIZATORIA else SALARIAL
            codigo = f"pago_13_{i}" if pago.natureza == NaturezaPagamento.DECIMO_TERCEIRO else f"pago_{i}"
            self.lancamentos.append(
                Lancamento(
                    codigo,
                    f"(−) {pago.descricao or 'Valor pago'} ({competencia:%m/%Y})",
                    Grupo.PROVENTO,
                    -pago.valor,
                    natureza,
                    f"Valor pago informado: {formatar_brl(pago.valor)}, competência {competencia:%m/%Y}.",
                    "Dedução dos valores pagos sob o mesmo título, pelo critério global (OJ 415 da SDI-1 do TST).",
                    pedido=PEDIDO_DEDUCOES,
                    parcelas=((competencia, -pago.valor),),
                )
            )
            if not pago.abater_fgts or pago.natureza == NaturezaPagamento.INDENIZATORIA:
                continue
            fgts = arredondar(pago.valor * ALIQUOTA_FGTS)
            self.lancamentos.append(
                Lancamento(
                    f"{codigo}_fgts",
                    f"(−) FGTS já depositado sobre o valor pago {i}",
                    Grupo.FGTS,
                    -fgts,
                    "FGTS",
                    f"8% × {formatar_brl(pago.valor)}",
                    "Art. 15, Lei nº 8.036/1990.",
                    pedido=PEDIDO_DEDUCOES,
                    parcelas=((competencia, -fgts),),
                )
            )
            if multa:
                valor_multa = arredondar(fgts * multa)
                self.lancamentos.append(
                    Lancamento(
                        f"{codigo}_multa_fgts",
                        f"(−) Multa do FGTS sobre o valor pago {i}",
                        Grupo.FGTS,
                        -valor_multa,
                        "Indenizatória",
                        f"{formatar_percentual(multa)} × {formatar_brl(fgts)}",
                        "Art. 18, Lei nº 8.036/1990.",
                        pedido=PEDIDO_DEDUCOES,
                        parcelas=((self.mes_desligamento, -valor_multa),),
                    )
                )

    def _outras_verbas(self):
        multa = MULTA_FGTS.get(self.modalidade)
        for i, verba in enumerate(self.d.outras_verbas, start=1):
            descricao = verba.descricao or ("Danos morais" if verba.dano_moral else f"Outra verba {i}")
            if verba.dano_moral:
                # Época própria no mês anterior ao ajuizamento: os índices começam no ajuizamento
                competencia = somar_meses(primeiro_dia_do_mes(self.d.data_ajuizamento), -1)
                natureza = "Indenizatória"
                formula = f"Valor arbitrado: {formatar_brl(verba.valor)}, atualizado desde o ajuizamento."
                fundamento = (
                    "Correção e juros desde o ajuizamento (SDI-1 do TST, E-RR-202-65.2011.5.04.0030; Súmula 439 "
                    "cancelada pela Res. 225/2025). Não incide INSS nem IR (Súmula 498 do STJ)."
                )
            else:
                competencia = primeiro_dia_do_mes(verba.competencia)
                natureza = "Indenizatória" if verba.natureza == NaturezaPagamento.INDENIZATORIA else SALARIAL
                formula = f"Valor deferido: {formatar_brl(verba.valor)}, competência {competencia:%m/%Y}."
                fundamento = f"Verba deferida na sentença (natureza {verba.natureza.rotulo.lower()})."
            codigo = f"outra_13_{i}" if verba.natureza == NaturezaPagamento.DECIMO_TERCEIRO else f"outra_{i}"
            self.lancamentos.append(
                Lancamento(
                    codigo,
                    descricao,
                    Grupo.PROVENTO,
                    verba.valor,
                    natureza,
                    formula,
                    fundamento,
                    pedido=descricao,
                    parcelas=((competencia, verba.valor),),
                )
            )
            if not verba.fgts or verba.dano_moral:
                continue
            fgts = arredondar(verba.valor * ALIQUOTA_FGTS)
            self.lancamentos.append(
                Lancamento(
                    f"{codigo}_fgts",
                    f"FGTS (8%) sobre {descricao.lower()}",
                    Grupo.FGTS,
                    fgts,
                    "FGTS",
                    f"8% × {formatar_brl(verba.valor)}",
                    "Art. 15, Lei nº 8.036/1990.",
                    pedido=descricao,
                    parcelas=((competencia, fgts),),
                )
            )
            if multa:
                valor_multa = arredondar(fgts * multa)
                self.lancamentos.append(
                    Lancamento(
                        f"{codigo}_multa_fgts",
                        f"Multa de {formatar_percentual(multa)} sobre o FGTS de {descricao.lower()}",
                        Grupo.FGTS,
                        valor_multa,
                        "Indenizatória",
                        f"{formatar_percentual(multa)} × {formatar_brl(fgts)}",
                        "Art. 18, Lei nº 8.036/1990.",
                        pedido=descricao,
                        parcelas=((self.mes_desligamento, valor_multa),),
                    )
                )

    # ------------------------------------------------------------------ INSS

    def _decimo_terceiro(self, item: Lancamento) -> bool:
        codigo = item.codigo
        return (
            codigo.startswith(("decimo_terceiro_", "pago_13_", "outra_13_"))
            or codigo == "deducao_decimo_terceiro"
            or (codigo.startswith(("he_", "noturno_", "adicional_")) and codigo.endswith("_13"))
        )

    def _parcelas(self, item: Lancamento):
        return item.parcelas or ((self.mes_desligamento, item.valor),)

    def _base_paga(self, competencia: date, decimo: bool) -> Decimal:
        """Salário já pago (e já submetido à contribuição) na competência."""
        if not self.d.considerar_salario_pago:
            return ZERO
        rescisorias = self.d.verbas_rescisorias if self.d.rescisao else frozenset()
        if decimo:
            ano = competencia.year
            if VerbaRescisoria.DECIMO_TERCEIRO in rescisorias and ano >= self.desligamento.year:
                return ZERO
            fim = min(date(ano, 12, 31), self.desligamento)
            if fim < self.admissao:
                return ZERO
            avos = avos_no_ano(max(self.admissao, date(ano, 1, 1)), fim, ano)
            return arredondar(salario_em(self.historico, self.salario, fim) * avos / 12)
        inicio = max(self.admissao, competencia)
        fim = min(ultimo_dia_do_mes(competencia.year, competencia.month), self.desligamento)
        if fim < inicio:
            return ZERO
        if competencia == self.mes_desligamento and VerbaRescisoria.SALDO_SALARIO in rescisorias:
            return ZERO  # o saldo de salário não foi pago: está na condenação
        return arredondar(salario_em(self.historico, self.salario, fim) * fracao_do_mes(inicio, fim))

    def _fator_inss(self, competencia: date, ate: date) -> tuple[str, Decimal]:
        if competencia >= INICIO_REGIME_COMPETENCIA:
            # Vencimento no dia 20 do mês seguinte; juros SELIC a partir do mês seguinte ao do
            # vencimento até o mês anterior ao pagamento, mais 1% no mês do pagamento.
            primeiro = somar_meses(competencia, 2)
            if ate < primeiro:
                return CRITERIO_SELIC, ZERO
            soma = JUROS_MES_DO_PAGAMENTO
            mes = primeiro
            while mes < ate:
                valor = self.tabela.valor("selic", mes)
                if valor is None:
                    raise ErroDeEntrada([f"Não há índice SELIC para {mes:%m/%Y} na tabela."])
                soma += valor
                mes = somar_meses(mes, 1)
            return CRITERIO_SELIC, soma
        try:
            _, _, _, total = fator_mensal(
                somar_meses(competencia, 1), ate, self.d.data_ajuizamento, self.d.juros_pre_judiciais, self.tabela
            )
        except TabelaIndisponivel as erro:
            raise ErroDeEntrada([str(erro)]) from erro
        return CRITERIO_TRABALHISTA, total - 1

    def _inss(self, ate: date) -> list[LinhaINSS]:
        bases: dict[tuple[date, bool], Decimal] = {}
        for item in self.lancamentos:
            if item.grupo != Grupo.PROVENTO or item.natureza != SALARIAL:
                continue
            decimo = self._decimo_terceiro(item)
            for competencia, valor in self._parcelas(item):
                chave = (primeiro_dia_do_mes(competencia), decimo)
                bases[chave] = bases.get(chave, ZERO) + valor

        if self.d.simples_nacional:
            aliquota_empresa = ZERO
        else:
            aliquota_empresa = COTA_EMPRESA + self.d.aliquota_rat + self.d.aliquota_terceiros
        # Multa de mora: 0,33% ao dia, até 20%, a partir do fim do prazo da citação (Súmula 368, V)
        multa = ZERO
        if self.d.fim_prazo_citacao and self.d.data_liquidacao > self.d.fim_prazo_citacao:
            dias = (self.d.data_liquidacao - self.d.fim_prazo_citacao).days
            multa = min(MULTA_DIARIA * dias, MULTA_MAXIMA)
        linhas, faltando = [], []
        for (competencia, decimo), base in sorted(bases.items()):
            devida = max(arredondar(base), ZERO)
            if devida == 0:
                continue
            try:
                inss_vigente(competencia)
            except TabelaIndisponivel:
                faltando.append(f"{competencia:%m/%Y}")
                continue
            paga = self._base_paga(competencia, decimo)
            segurado = calcular_inss(paga + devida, competencia).valor - calcular_inss(paga, competencia).valor
            criterio, fator = self._fator_inss(competencia, ate)
            linhas.append(
                LinhaINSS(
                    competencia,
                    decimo,
                    devida,
                    paga,
                    max(segurado, ZERO),
                    arredondar(devida * aliquota_empresa),
                    criterio,
                    fator,
                    multa if criterio == CRITERIO_SELIC else ZERO,
                )
            )
        if faltando:
            primeira = min(t.vigencia for t in tabelas_inss())
            raise ErroDeEntrada(
                [
                    f"Não há tabela de INSS para as competências {', '.join(faltando)}. O sistema cobre "
                    f"competências a partir de {formatar_data(primeira)}."
                ]
            )
        return linhas

    # ------------------------------------------------------------------ IR

    def _irrf(self, ate: date, inss: list[LinhaINSS], fracao_deducoes: Decimal) -> ImpostoRenda:
        """IR das verbas salariais (Súmula 368, VI, do TST). Anos anteriores ao da liquidação: rendimentos
        recebidos acumuladamente (art. 12-A da Lei nº 7.713/1988). Ano da liquidação: tabela mensal comum
        sobre o total (art. 12-B)."""
        ano = self.d.data_liquidacao.year
        fatores: dict[date, Decimal] = {}
        anteriores = corrente = ZERO
        meses: set[date] = set()
        decimos: set[int] = set()
        for item in self.lancamentos:
            if item.grupo != Grupo.PROVENTO or item.natureza != SALARIAL:
                continue
            decimo = self._decimo_terceiro(item)
            for competencia, valor in self._parcelas(item):
                competencia = primeiro_dia_do_mes(competencia)
                if competencia not in fatores:
                    try:
                        correcao, _, _, _ = fator_mensal(
                            somar_meses(competencia, 1),
                            ate,
                            self.d.data_ajuizamento,
                            self.d.juros_pre_judiciais,
                            self.tabela,
                        )
                    except TabelaIndisponivel as erro:
                        raise ErroDeEntrada([str(erro)]) from erro
                    fatores[competencia] = correcao
                # A correção acompanha o principal; juros (TR, SELIC e taxa legal) não são tributáveis
                # (OJ 400 da SDI-1 do TST; Tema 808 do STF).
                tributavel = valor * (1 + fatores[competencia])
                if competencia.year >= ano:
                    corrente += tributavel
                    continue
                anteriores += tributavel
                if valor > 0:
                    # O 13º de cada ano conta como um mês a mais (art. 37, § 1º, IN RFB nº 1.500/2014)
                    if decimo:
                        decimos.add(competencia.year)
                    else:
                        meses.add(competencia)
        inss_anteriores = sum((linha.segurado for linha in inss if linha.competencia.year < ano), ZERO)
        inss_corrente = sum((linha.segurado for linha in inss if linha.competencia.year >= ano), ZERO)
        quantidade = max(len(meses) + len(decimos), 1)
        # Pensão alimentícia e honorários contratuais, na proporção dos rendimentos tributáveis (art. 12-A, §§ 2º e 3º)
        outras_anteriores = arredondar(max(anteriores, ZERO) * fracao_deducoes)
        outras_corrente = arredondar(max(corrente, ZERO) * fracao_deducoes)
        try:
            acumulado = (
                calcular_irrf_rra(
                    max(anteriores, ZERO), inss_anteriores, quantidade, self.d.data_liquidacao, outras_anteriores
                )
                if anteriores > 0
                else None
            )
            mensal = (
                calcular_irrf(
                    max(corrente, ZERO),
                    inss_corrente,
                    0,
                    self.d.data_liquidacao,
                    permitir_simplificado=False,
                    outras_deducoes=outras_corrente,
                )
                if corrente > 0
                else None
            )
        except TabelaIndisponivel as erro:
            raise ErroDeEntrada([str(erro)]) from erro
        return ImpostoRenda(acumulado, quantidade if acumulado else 0, mensal)

    # ------------------------------------------------------------------ execução

    def executar(self) -> ResultadoLiquidacao:
        d = self.d
        if d.rescisao is not None:
            self._verbas_rescisorias()
        if d.pedidos is not None:
            self._verbas_pedidos()
        self._outras_verbas()
        self._valores_pagos()

        parametros = ParametrosAtualizacao(d.data_liquidacao, d.data_ajuizamento, d.juros_pre_judiciais)
        verbas = ResultadoPedidos("Liquidação de sentença", self.lancamentos, [], {})
        atualizado = atualizar(verbas, parametros, self.mes_desligamento, self.tabela)
        self.alertas += atualizado.alertas

        inss = self._inss(atualizado.atualizado_ate)
        bruto = atualizado.soma(Grupo.PROVENTO).total
        segurado = sum((linha.segurado for linha in inss), ZERO)
        pensao = arredondar(max(bruto - segurado, ZERO) * d.pensao_percentual)
        fracao = d.honorarios_contratuais_percentual + (pensao / bruto if bruto > 0 else ZERO)
        irrf = self._irrf(atualizado.atualizado_ate, inss, fracao)

        resultado = ResultadoLiquidacao(
            "Liquidação de sentença",
            self.lancamentos,
            self.alertas,
            self.resumo,
            d.pedidos,
            self.mensal,
            dados_liquidacao=d,
            atualizado=atualizado,
            inss=inss,
            irrf=irrf,
            pensao=pensao,
            pagamentos=self._pagamentos(atualizado.atualizado_ate),
        )
        self._honorarios_e_custas(resultado)
        self._finalizar(resultado)
        return resultado

    def _pagamentos(self, ate: date) -> list[tuple[str, Decimal]]:
        """Pagamentos atualizados pelos mesmos índices até a liquidação; depósitos pelo saldo informado."""
        lista = []
        for i, pagamento in enumerate(self.d.pagamentos, start=1):
            descricao = pagamento.descricao or f"Pagamento {i}"
            if pagamento.deposito_judicial:
                lista.append((f"{descricao} (saldo do depósito)", arredondar(pagamento.valor)))
                continue
            try:
                _, _, _, fator = fator_mensal(
                    somar_meses(primeiro_dia_do_mes(pagamento.data), 1),
                    ate,
                    self.d.data_ajuizamento,
                    self.d.juros_pre_judiciais,
                    self.tabela,
                )
            except TabelaIndisponivel as erro:
                raise ErroDeEntrada([str(erro)]) from erro
            lista.append(
                (f"{descricao} ({formatar_data(pagamento.data)}, atualizado)", arredondar(pagamento.valor * fator))
            )
        return lista

    def _honorarios_e_custas(self, r: ResultadoLiquidacao):
        d = self.d
        r.honorarios_periciais = arredondar(d.honorarios_periciais)
        r.periciais_pela_uniao = d.periciais_pelo_reclamante and d.justica_gratuita and r.honorarios_periciais > 0
        r.periciais_do_reclamante = d.periciais_pelo_reclamante and not r.periciais_pela_uniao
        condenacao = r.bruto_atualizado + r.fgts_atualizado
        r.honorarios = arredondar(max(condenacao, ZERO) * d.honorarios_percentual)
        r.honorarios_reclamante = arredondar(d.honorarios_reclamante_base * d.honorarios_reclamante_percentual)
        r.honorarios_reclamante_suspensos = d.justica_gratuita and r.honorarios_reclamante > 0
        if d.custas_informadas is not None:
            r.custas = arredondar(d.custas_informadas)
        elif condenacao > 0:
            teto = inss_vigente(d.data_liquidacao).teto * 4
            r.custas = min(max(arredondar(condenacao * CUSTAS), CUSTAS_MINIMO), arredondar(teto))

    def _finalizar(self, r: ResultadoLiquidacao):
        d = self.d
        credito = "Crédito do reclamante"
        encargos = "Recolhimentos e despesas da reclamada"
        honorarios_exigiveis = r.honorarios_reclamante if not r.honorarios_reclamante_suspensos else ZERO
        quadro = [
            (credito, "Verbas deferidas atualizadas (sem FGTS)", r.bruto_atualizado, False),
            (credito, "(−) INSS do reclamante (cota-parte)", -r.inss_segurado, False),
            (credito, "(−) Imposto de renda retido na fonte", -r.irrf.valor, False),
            (credito, "(−) Pensão alimentícia", -r.pensao, False),
            (credito, "(−) Honorários devidos pelo reclamante", -honorarios_exigiveis, False),
            (credito, "(−) Honorários periciais a cargo do reclamante", -r.periciais_descontados, False),
            (credito, "Líquido devido ao reclamante", r.liquido_reclamante, True),
            (encargos, "FGTS a depositar na conta vinculada (com multa)", r.fgts_atualizado, False),
            (encargos, "INSS do reclamante (retido do crédito)", r.inss_segurado, False),
            (encargos, "INSS da reclamada (empresa, RAT e terceiros)", r.inss_empresa, False),
            (encargos, "Juros e multa sobre o INSS (ou atualização)", r.inss_acrescimos, False),
            (encargos, "Imposto de renda (retido do crédito)", r.irrf.valor, False),
            (encargos, "Pensão alimentícia (retida do crédito)", r.pensao, False),
            (encargos, "Honorários de sucumbência (advogado do reclamante)", r.honorarios, False),
            (encargos, "Honorários devidos pelo reclamante (retidos do crédito)", honorarios_exigiveis, False),
            (encargos, "Honorários periciais", r.periciais_reclamada + r.periciais_descontados, False),
            (encargos, "Custas processuais", r.custas, False),
            ("Total", "Total devido pela reclamada", r.total_reclamada, True),
        ]
        if r.pagamentos:
            quadro += [("Total", f"(−) {descricao}", -valor, False) for descricao, valor in r.pagamentos]
            quadro.append(("Total", "Saldo a pagar pela reclamada", r.saldo_reclamada, True))
        r.quadro = [linha for linha in quadro if linha[2] or linha[3]]

        r.resumo.update(
            {
                "Ajuizamento": formatar_data(d.data_ajuizamento),
                "Data da liquidação": formatar_data(d.data_liquidacao),
                "Atualizado até": formatar_data(r.atualizado.atualizado_ate),
            }
        )
        if d.rescisao is not None:
            r.resumo["Verbas rescisórias deferidas"] = ", ".join(
                v.rotulo for v in VerbaRescisoria if v in d.verbas_rescisorias
            )
        if r.honorarios_reclamante_suspensos:
            self.alertas.append(
                f"Honorários devidos pelo reclamante ({formatar_brl(r.honorarios_reclamante)}) com exigibilidade "
                "suspensa por ser beneficiário da justiça gratuita (art. 791-A, § 4º, CLT; ADI 5766 do STF): "
                "não foram descontados do crédito."
            )
        for percentual, quem in (
            (d.honorarios_percentual, "da reclamada"),
            (d.honorarios_reclamante_percentual, "do reclamante"),
        ):
            if percentual and not (Decimal("0.05") <= percentual <= Decimal("0.15")):
                self.alertas.append(
                    f"Os honorários {quem} estão fora da faixa de 5% a 15% do art. 791-A da CLT. Confira a sentença."
                )
        if r.bruto_atualizado < 0:
            self.alertas.append("Os valores pagos superam as verbas deferidas: não há crédito a receber.")
        if r.periciais_pela_uniao:
            self.alertas.append(
                f"Honorários periciais ({formatar_brl(r.honorarios_periciais)}) a cargo do reclamante, beneficiário da "
                "justiça gratuita: pagos pela União (art. 790-B, § 4º, CLT; ADI 5766 do STF), fora deste total."
            )
        if r.saldo_reclamada < 0:
            self.alertas.append("Os pagamentos e depósitos superam o total devido: há saldo a devolver à reclamada.")
        if r.inss and not d.fim_prazo_citacao and any(linha.criterio == CRITERIO_SELIC for linha in r.inss):
            self.alertas.append(
                "A multa de mora sobre o INSS (art. 61, Lei nº 9.430/1996) só incide depois de vencido o prazo da "
                "citação para pagamento (Súmula 368, V, do TST) e não foi incluída. Para incluí-la, informe "
                "a data do fim desse prazo."
            )
        alerta = aviso_tabela_desatualizada(d.data_liquidacao)
        if alerta:
            self.alertas.append(alerta)


def comparar(
    quadro: list[tuple[str, str, Decimal, bool]], outro_calculo: dict[str, Decimal]
) -> list[tuple[str, Decimal, Decimal | None, Decimal | None]]:
    """Compara o resumo com outro cálculo (da parte contrária ou da contadoria).

    Devolve (rótulo, este cálculo, outro cálculo, diferença) para cada linha do resumo."""
    linhas = []
    for _, rotulo, valor, _ in quadro:
        outro = outro_calculo.get(rotulo)
        linhas.append((rotulo, valor, outro, None if outro is None else valor - outro))
    return linhas
