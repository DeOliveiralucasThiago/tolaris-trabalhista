"""Cálculo das verbas rescisórias.

Cada regra aqui está descrita, com fundamento e exemplos, em `regras/rescisao.md`.
Toda alteração de regra deve atualizar esse arquivo e os testes em `tests/`.
"""

from datetime import date, timedelta
from decimal import Decimal

from tolaris.datas import (
    UM_DIA,
    anos_completos,
    avos_no_ano,
    dias_corridos,
    formatar_data,
    meses_com_fracao,
    meses_entre,
    somar_meses,
    ultimo_dia_do_mes,
)
from tolaris.dinheiro import ZERO, arredondar, formatar_brl, formatar_numero
from tolaris.motor.contrato import (
    ALIQUOTA_FGTS,
    AVISO_PELA_METADE,
    AVISO_PELO_EMPREGADOR,
    METADE,
    MULTA_FGTS,
    dias_aviso_indenizados,
    dias_de_aviso,
    salario_em,
)
from tolaris.motor.modelos import (
    AVISOS_PERMITIDOS,
    Aviso,
    DadosRescisao,
    ErroDeEntrada,
    Grupo,
    Lancamento,
    Modalidade,
    ResultadoRescisao,
)
from tolaris.motor.tributos import calcular_inss, calcular_irrf
from tolaris.tabelas import TabelaIndisponivel, aviso_tabela_desatualizada, inss_vigente, irrf_vigente


def dias_de_ferias_por_faltas(faltas: int) -> int:
    """Art. 130 da CLT."""
    if faltas <= 5:
        return 30
    if faltas <= 14:
        return 24
    if faltas <= 23:
        return 18
    if faltas <= 32:
        return 12
    return 0


def calcular_rescisao(dados: DadosRescisao, com_tributos: bool = True) -> ResultadoRescisao:
    """`com_tributos=False` omite INSS e IRRF (a liquidação de sentença os apura por outras regras)."""
    _validar(dados, com_tributos)
    return _Calculo(dados, com_tributos).executar()


def _validar(d: DadosRescisao, com_tributos: bool = True) -> None:
    erros = []
    if d.desligamento < d.admissao:
        erros.append("A data de desligamento não pode ser anterior à admissão.")
    if d.salario <= 0:
        erros.append("Informe o salário mensal.")
    if d.media_variaveis < 0:
        erros.append("A média de variáveis não pode ser negativa.")
    if d.aviso not in AVISOS_PERMITIDOS[d.modalidade]:
        permitidos = ", ".join(a.rotulo for a in AVISOS_PERMITIDOS[d.modalidade])
        erros.append(f"Para {d.modalidade.rotulo.lower()}, o aviso prévio deve ser: {permitidos}.")
    for campo, nome in (
        (d.ferias_vencidas, "períodos de férias vencidas"),
        (d.faltas_periodo_aquisitivo, "faltas no período aquisitivo"),
        (d.faltas_mes_rescisao, "faltas no mês da rescisão"),
        (d.dependentes_ir, "dependentes"),
    ):
        if campo < 0:
            erros.append(f"O número de {nome} não pode ser negativo.")
    if d.desligamento >= d.admissao:
        completos = anos_completos(d.admissao, d.desligamento)
        if d.ferias_vencidas > completos:
            erros.append(
                f"Foram informados {d.ferias_vencidas} período(s) de férias vencidas, mas o contrato "
                f"tem apenas {completos} período(s) aquisitivo(s) completo(s) até o desligamento."
            )
    for valor, nome in (
        (d.decimo_terceiro_pago, "13º já pago"),
        (d.outros_descontos, "outros descontos"),
        (d.saldo_fgts, "saldo do FGTS"),
    ):
        if valor is not None and valor < 0:
            erros.append(f"O valor de {nome} não pode ser negativo.")
    for alteracao in d.historico_salarial:
        if alteracao.salario <= 0:
            erros.append(f"Salário do histórico a partir de {formatar_data(alteracao.inicio)} deve ser positivo.")
    try:
        if com_tributos:
            inss_vigente(d.desligamento)
            irrf_vigente(d.desligamento)
    except TabelaIndisponivel as erro:
        erros.append(str(erro))
    if erros:
        raise ErroDeEntrada(erros)


class _Calculo:
    def __init__(self, dados: DadosRescisao, com_tributos: bool = True):
        self.d = dados
        self.com_tributos = com_tributos
        self.lancamentos: list[Lancamento] = []
        self.alertas: list[str] = []
        self.remuneracao = arredondar(dados.salario + dados.media_variaveis)
        self.culpa_reciproca = dados.modalidade == Modalidade.CULPA_RECIPROCA

        self.anos_servico = anos_completos(dados.admissao, dados.desligamento)
        self.dias_aviso = dias_de_aviso(dados.admissao, dados.desligamento)
        self.dias_aviso_indenizados = dias_aviso_indenizados(dados.modalidade, dados.aviso, self.dias_aviso)
        self.data_projetada = dados.desligamento + timedelta(days=self.dias_aviso_indenizados)

        # Bases acumuladas para tributos, FGTS e multa do art. 467
        self.saldo_salario = ZERO
        self.aviso_indenizado = ZERO
        self.decimo_terceiro = ZERO
        self.ferias = ZERO
        self.multa_fgts = ZERO

    # ------------------------------------------------------------------ apoio

    def _lancar(self, codigo, descricao, grupo, valor, natureza, formula, fundamento) -> Decimal:
        valor = arredondar(valor)
        if valor > 0:
            self.lancamentos.append(Lancamento(codigo, descricao, grupo, valor, natureza, formula, fundamento))
        return valor

    # ------------------------------------------------------------------ verbas

    def executar(self) -> ResultadoRescisao:
        self._saldo_de_salario()
        self._aviso_previo()
        self._decimo_terceiro()
        self._ferias()
        self._multa_477()
        self._fgts()
        self._multa_467()
        self._descontos()

        alerta_tabela = aviso_tabela_desatualizada(self.d.desligamento) if self.com_tributos else None
        if alerta_tabela:
            self.alertas.append(alerta_tabela)
        return ResultadoRescisao(
            "Memória de cálculo de verbas rescisórias", self.lancamentos, self.alertas, self._resumo(), self.d
        )

    def _saldo_de_salario(self):
        d = self.d
        inicio = max(d.admissao, d.desligamento.replace(day=1))
        dias = dias_corridos(inicio, d.desligamento)
        fim_do_mes = ultimo_dia_do_mes(d.desligamento.year, d.desligamento.month)
        mes_completo = inicio.day == 1 and d.desligamento == fim_do_mes
        if mes_completo:
            dias = 30
        dias = min(dias, 30)
        dias_pagos = max(dias - d.faltas_mes_rescisao, 0)
        formula = f"{formatar_brl(d.salario)} ÷ 30 × {dias_pagos} dias"
        if d.faltas_mes_rescisao:
            formula += f" ({dias} dias no mês − {d.faltas_mes_rescisao} falta(s))"
        if mes_completo:
            formula += " (mês completo conta como 30 dias)"
        self.saldo_salario = self._lancar(
            "saldo_salario",
            f"Saldo de salário ({dias_pagos} dias)",
            Grupo.PROVENTO,
            d.salario / 30 * dias_pagos,
            "Salarial",
            formula,
            "Art. 457 e art. 477, CLT.",
        )

    def _aviso_previo(self):
        d = self.d
        if d.modalidade == Modalidade.PEDIDO_DEMISSAO:
            return  # desconto do aviso não cumprido é tratado em _descontos
        dias = self.dias_aviso_indenizados
        if dias <= 0:
            return
        fator = METADE if d.modalidade in AVISO_PELA_METADE else Decimal(1)
        formula = f"{formatar_brl(self.remuneracao)} ÷ 30 × {dias} dias"
        if d.aviso == Aviso.TRABALHADO:
            formula += f" (aviso de {self.dias_aviso} dias: 30 trabalhados, {dias} indenizados)"
        fundamento = "Art. 487, § 1º, CLT; Lei nº 12.506/2011 (30 dias + 3 por ano completo, até 90)."
        if fator != 1:
            formula += " × 50%"
            fundamento += (
                " Metade do aviso: art. 484-A, I, a, CLT."
                if d.modalidade == Modalidade.ACORDO
                else " Metade do aviso: Súmula 14 do TST."
            )
        self.aviso_indenizado = self._lancar(
            "aviso_previo",
            f"Aviso prévio indenizado ({dias} dias)",
            Grupo.PROVENTO,
            self.remuneracao / 30 * dias * fator,
            "Indenizatória",
            formula,
            fundamento,
        )

    def _decimo_terceiro(self):
        d = self.d
        if d.modalidade == Modalidade.JUSTA_CAUSA:
            return
        fator = METADE if self.culpa_reciproca else Decimal(1)
        for ano in range(d.desligamento.year, self.data_projetada.year + 1):
            inicio = max(d.admissao, date(ano, 1, 1))
            if inicio > self.data_projetada:
                continue
            avos = avos_no_ano(inicio, self.data_projetada, ano)
            avos_trabalhados = avos_no_ano(inicio, d.desligamento, ano) if inicio <= d.desligamento else 0
            if avos == 0:
                continue
            formula = f"{formatar_brl(self.remuneracao)} ÷ 12 × {avos} avos"
            if avos > avos_trabalhados:
                projecao = formatar_data(self.data_projetada)
                formula += f" ({avos - avos_trabalhados} avo(s) pela projeção do aviso até {projecao})"
            fundamento = "Lei nº 4.090/1962 (mês com 15 dias ou mais conta como avo)."
            if d.modalidade == Modalidade.PEDIDO_DEMISSAO:
                fundamento += " Devido no pedido de demissão: Súmula 157 do TST."
            if avos > avos_trabalhados:
                fundamento += " Projeção do aviso: art. 487, § 1º, CLT."
            if fator != 1:
                formula += " × 50%"
                fundamento += " Metade: Súmula 14 do TST."
            self.decimo_terceiro += self._lancar(
                f"decimo_terceiro_{ano}",
                f"13º salário proporcional {ano} ({avos}/12)",
                Grupo.PROVENTO,
                self.remuneracao / 12 * avos * fator,
                "Salarial",
                formula,
                fundamento,
            )
        if d.desligamento.month == 12:
            self.alertas.append(
                "Desligamento em dezembro: confira se o 13º do ano já foi pago e informe o valor "
                "pago em '13º já pago' para não cobrar em duplicidade."
            )

    def _ferias(self):
        d = self.d
        completos = self.anos_servico
        completos_com_projecao = anos_completos(d.admissao, self.data_projetada)

        for i in range(completos - d.ferias_vencidas, completos):
            inicio = somar_meses(d.admissao, 12 * i)
            fim = somar_meses(d.admissao, 12 * (i + 1)) - UM_DIA
            fim_concessivo = somar_meses(d.admissao, 12 * (i + 2)) - UM_DIA
            dobra = fim_concessivo < d.desligamento
            periodo = f"{formatar_data(inicio)} a {formatar_data(fim)}"
            if dobra:
                formula = (
                    f"{formatar_brl(self.remuneracao)} × 2 (período concessivo terminou em "
                    f"{formatar_data(fim_concessivo)}, antes do desligamento)"
                )
                fundamento = "Arts. 134 e 137, CLT (férias não concedidas no prazo são pagas em dobro)."
            else:
                formula = f"{formatar_brl(self.remuneracao)} (30 dias)"
                fundamento = "Art. 146, caput, CLT (férias vencidas são devidas em qualquer modalidade)."
            self._lancar_ferias(
                f"ferias_vencidas_{i}",
                f"Férias vencidas {'em dobro ' if dobra else ''}({periodo})",
                self.remuneracao * (2 if dobra else 1),
                formula,
                fundamento,
            )

        for i in range(completos, completos_com_projecao):
            inicio = somar_meses(d.admissao, 12 * i)
            fim = somar_meses(d.admissao, 12 * (i + 1)) - UM_DIA
            self._lancar_ferias(
                f"ferias_integrais_projecao_{i}",
                f"Férias integrais ({formatar_data(inicio)} a {formatar_data(fim)})",
                self.remuneracao,
                f"{formatar_brl(self.remuneracao)} (período completado durante a projeção do aviso)",
                "Art. 146, CLT; projeção do aviso: art. 487, § 1º, CLT.",
            )

        if d.modalidade == Modalidade.JUSTA_CAUSA:
            return
        inicio = somar_meses(d.admissao, 12 * completos_com_projecao)
        avos = min(meses_com_fracao(inicio, self.data_projetada), 12)
        if avos == 0:
            return
        dias_direito = dias_de_ferias_por_faltas(d.faltas_periodo_aquisitivo)
        if dias_direito == 0:
            self.alertas.append(
                f"Com {d.faltas_periodo_aquisitivo} faltas injustificadas no período aquisitivo, o "
                "empregado perde o direito às férias proporcionais (art. 130, CLT)."
            )
            return
        fator = METADE if self.culpa_reciproca else Decimal(1)
        formula = f"{formatar_brl(self.remuneracao)} ÷ 12 × {avos} avos"
        if dias_direito < 30:
            formula += f" × {dias_direito}/30 dias ({d.faltas_periodo_aquisitivo} faltas, art. 130 CLT)"
        fundamento = "Art. 146, parágrafo único, CLT (fração superior a 14 dias conta como mês)."
        if d.modalidade == Modalidade.PEDIDO_DEMISSAO:
            fundamento += " Devidas no pedido de demissão: Súmula 261 do TST."
        if self.dias_aviso_indenizados:
            fundamento += f" Período contado até a projeção do aviso ({formatar_data(self.data_projetada)})."
        if fator != 1:
            formula += " × 50%"
            fundamento += " Metade: Súmula 14 do TST."
        self._lancar_ferias(
            "ferias_proporcionais",
            f"Férias proporcionais ({avos}/12)",
            self.remuneracao / 12 * avos * Decimal(dias_direito) / 30 * fator,
            formula,
            fundamento,
        )

    def _lancar_ferias(self, codigo, descricao, valor, formula, fundamento):
        valor = self._lancar(codigo, descricao, Grupo.PROVENTO, valor, "Indenizatória", formula, fundamento)
        terco = self._lancar(
            f"{codigo}_terco",
            f"1/3 constitucional – {descricao[0].lower()}{descricao[1:]}",
            Grupo.PROVENTO,
            valor / 3,
            "Indenizatória",
            f"{formatar_brl(valor)} ÷ 3",
            "Art. 7º, XVII, CF; Súmula 328 do TST.",
        )
        self.ferias += valor + terco

    def _multa_477(self):
        if not self.d.pagamento_em_atraso:
            return
        self._lancar(
            "multa_477",
            "Multa do art. 477, § 8º, CLT",
            Grupo.PROVENTO,
            self.d.salario,
            "Indenizatória",
            f"Um salário: {formatar_brl(self.d.salario)}",
            "Art. 477, §§ 6º e 8º, CLT (pagamento das verbas rescisórias fora do prazo de 10 dias).",
        )

    def _fgts(self):
        d = self.d
        base = self.saldo_salario + self.decimo_terceiro + self.aviso_indenizado
        deposito = self._lancar(
            "fgts_rescisorio",
            "FGTS sobre verbas rescisórias (8%)",
            Grupo.FGTS,
            base * ALIQUOTA_FGTS,
            "FGTS",
            f"8% × {formatar_brl(base)} (saldo de salário + 13º + aviso prévio indenizado)",
            "Art. 15, Lei nº 8.036/1990; Súmula 305 do TST (aviso indenizado). "
            "Não incide sobre férias indenizadas: OJ 195 da SDI-1 do TST.",
        )

        percentual = MULTA_FGTS.get(d.modalidade)
        if not percentual:
            return
        if d.saldo_fgts is not None:
            saldo = arredondar(d.saldo_fgts)
            origem = f"saldo informado {formatar_brl(saldo)}"
        else:
            saldo = self._estimar_saldo_fgts()
            origem = f"saldo estimado {formatar_brl(saldo)}"
            self.alertas.append(
                "O saldo do FGTS foi estimado a partir do salário (8% ao mês + 13º), sem juros e "
                "atualização monetária da conta. Informe o saldo para fins rescisórios do extrato "
                "para um valor preciso."
            )
        base_multa = saldo + deposito
        fundamento = (
            "Art. 18, § 1º, Lei nº 8.036/1990."
            if percentual == Decimal("0.40")
            else (
                "Art. 484-A, I, b, CLT."
                if d.modalidade == Modalidade.ACORDO
                else "Art. 18, § 2º, Lei nº 8.036/1990; Súmula 14 do TST."
            )
        )
        self.multa_fgts = self._lancar(
            "multa_fgts",
            f"Multa de {int(percentual * 100)}% do FGTS",
            Grupo.FGTS,
            base_multa * percentual,
            "Indenizatória",
            f"{int(percentual * 100)}% × ({origem} + depósito rescisório {formatar_brl(deposito)})",
            fundamento,
        )

    def _estimar_saldo_fgts(self) -> Decimal:
        """Depósitos mensais de 8% do salário, do mês da admissão ao mês anterior ao
        desligamento, mais 8% do 13º de cada ano completo anterior. Sem JAM."""
        d = self.d
        total = ZERO
        fim = d.desligamento.replace(day=1) - UM_DIA
        for mes in meses_entre(d.admissao, fim):
            if mes.year == d.admissao.year and mes.month == d.admissao.month and d.admissao.day > 1:
                dias = min(dias_corridos(d.admissao, ultimo_dia_do_mes(mes.year, mes.month)), 30)
            else:
                dias = 30
            total += salario_em(d.historico_salarial, d.salario, mes) / 30 * dias * ALIQUOTA_FGTS
        for ano in range(d.admissao.year, d.desligamento.year):
            avos = avos_no_ano(max(d.admissao, date(ano, 1, 1)), date(ano, 12, 31), ano)
            total += salario_em(d.historico_salarial, d.salario, date(ano, 12, 1)) / 12 * avos * ALIQUOTA_FGTS
        return arredondar(total)

    def _multa_467(self):
        if not self.d.multa_467:
            return
        base = self.saldo_salario + self.aviso_indenizado + self.decimo_terceiro + self.ferias + self.multa_fgts
        self._lancar(
            "multa_467",
            "Multa do art. 467 da CLT (50%)",
            Grupo.PROVENTO,
            base * METADE,
            "Penalidade",
            f"50% × {formatar_brl(base)} (saldo, aviso, 13º, férias + 1/3 e multa do FGTS)",
            "Art. 467, CLT (verbas rescisórias incontroversas não pagas na primeira audiência).",
        )

    def _tributos(self):
        d = self.d
        inss_mensal = calcular_inss(self.saldo_salario, d.desligamento)
        self._lancar(
            "inss_mensal",
            "INSS sobre saldo de salário",
            Grupo.DESCONTO,
            inss_mensal.valor,
            "Tributária",
            inss_mensal.memoria,
            "Lei nº 8.212/1991, art. 20 e art. 28. Não incide sobre aviso indenizado nem férias indenizadas.",
        )
        inss_13 = calcular_inss(self.decimo_terceiro, d.desligamento)
        self._lancar(
            "inss_13",
            "INSS sobre 13º salário",
            Grupo.DESCONTO,
            inss_13.valor,
            "Tributária",
            inss_13.memoria,
            "Lei nº 8.212/1991, art. 28, § 7º (13º calculado em separado).",
        )

        irrf_mensal = calcular_irrf(self.saldo_salario, inss_mensal.valor, d.dependentes_ir, d.desligamento)
        self._lancar(
            "irrf_mensal",
            "IRRF sobre saldo de salário",
            Grupo.DESCONTO,
            irrf_mensal.valor,
            "Tributária",
            irrf_mensal.memoria,
            "Lei nº 7.713/1988. Férias indenizadas + 1/3 e aviso indenizado não são tributáveis.",
        )
        irrf_13 = calcular_irrf(
            self.decimo_terceiro, inss_13.valor, d.dependentes_ir, d.desligamento, permitir_simplificado=False
        )
        self._lancar(
            "irrf_13",
            "IRRF sobre 13º salário",
            Grupo.DESCONTO,
            irrf_13.valor,
            "Tributária",
            irrf_13.memoria,
            "Lei nº 7.713/1988, art. 26 (tributação exclusiva do 13º).",
        )

    def _descontos(self):
        d = self.d
        if d.modalidade == Modalidade.PEDIDO_DEMISSAO and d.aviso == Aviso.NAO_CUMPRIDO:
            self._lancar(
                "desconto_aviso",
                "Aviso prévio não cumprido pelo empregado (30 dias)",
                Grupo.DESCONTO,
                d.salario,
                "Dedução",
                f"{formatar_brl(d.salario)} ÷ 30 × 30 dias",
                "Art. 487, § 2º, CLT.",
            )

        if self.com_tributos:
            self._tributos()

        self._lancar(
            "decimo_terceiro_pago",
            "13º salário já pago (adiantamento)",
            Grupo.DESCONTO,
            d.decimo_terceiro_pago,
            "Dedução",
            f"Valor informado: {formatar_brl(d.decimo_terceiro_pago)}",
            "Lei nº 4.749/1965, art. 3º.",
        )
        self._lancar(
            "outros_descontos",
            "Outros descontos",
            Grupo.DESCONTO,
            d.outros_descontos,
            "Dedução",
            f"Valor informado: {formatar_brl(d.outros_descontos)}",
            "Art. 462, CLT.",
        )

        if self.total_provisorio() < 0:
            self.alertas.append(
                "Os descontos superam os proventos. Pelo art. 477, § 5º, da CLT, a compensação na "
                "rescisão não pode exceder um mês de remuneração do empregado."
            )

    def total_provisorio(self) -> Decimal:
        proventos = sum((x.valor for x in self.lancamentos if x.grupo == Grupo.PROVENTO), ZERO)
        descontos = sum((x.valor for x in self.lancamentos if x.grupo == Grupo.DESCONTO), ZERO)
        return proventos - descontos

    def _resumo(self) -> dict[str, str]:
        d = self.d
        resumo = {
            "Modalidade": d.modalidade.rotulo,
            "Admissão": formatar_data(d.admissao),
            "Desligamento": formatar_data(d.desligamento),
            "Tempo de serviço": f"{self.anos_servico} ano(s) completo(s)",
            "Remuneração para cálculo": (
                f"{formatar_brl(self.remuneracao)} (salário {formatar_brl(d.salario)}"
                f" + média de variáveis {formatar_brl(d.media_variaveis)})"
            ),
            "Aviso prévio": d.aviso.rotulo,
        }
        if d.modalidade in AVISO_PELO_EMPREGADOR:
            resumo["Dias de aviso (Lei 12.506/2011)"] = f"{self.dias_aviso} dias"
        if self.dias_aviso_indenizados:
            resumo["Data projetada (OJ 82 SDI-1)"] = formatar_data(self.data_projetada)
        resumo["Dependentes para IR"] = formatar_numero(d.dependentes_ir, 0)
        return resumo
