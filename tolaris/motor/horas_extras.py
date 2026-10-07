"""Horas extras, adicional noturno e adicionais de insalubridade/periculosidade, com reflexos.

O cálculo é feito mês a mês (competência). Cada regra está descrita em `regras/horas_extras.md`.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from tolaris.datas import (
    UM_DIA,
    dias_corridos,
    dias_uteis_e_repousos,
    formatar_data,
    meses_entre,
    primeiro_dia_do_mes,
    somar_meses,
    ultimo_dia_do_mes,
)
from tolaris.dinheiro import ZERO, arredondar, formatar_brl, formatar_numero, formatar_percentual
from tolaris.motor.contrato import (
    ALIQUOTA_FGTS,
    AVISO_PELA_METADE,
    METADE,
    MULTA_FGTS,
    dias_aviso_indenizados,
    dias_de_aviso,
    salario_em,
)
from tolaris.motor.modelos import (
    AVISOS_PERMITIDOS,
    AdicionalOcupacional,
    DadosPedidos,
    ErroDeEntrada,
    Grupo,
    Lancamento,
    LinhaMensal,
    Modalidade,
    ResultadoPedidos,
)
from tolaris.tabelas import salario_minimo_vigente, tabelas_salario_minimo

# OJ 394 da SDI-1 (redação do IRR de 2023): o DSR majorado pelas horas extras repercute nas
# demais parcelas para horas extras trabalhadas a partir de 20/03/2023. Simplificação adotada:
# vale para as competências a partir de abril/2023.
INICIO_DSR_NOS_REFLEXOS = date(2023, 4, 1)
CONVERSAO_HORA_NOTURNA = Decimal(60) / Decimal("52.5")  # 8/7: hora noturna de 52min30s (art. 73, § 1º)
UM = Decimal(1)
DOZE = Decimal(12)
QUATRO_TERCOS = Decimal(4) / Decimal(3)

PEDIDO_HE = "Horas extras"
PEDIDO_NOTURNO = "Adicional noturno"


def calcular_pedidos(dados: DadosPedidos) -> ResultadoPedidos:
    _validar(dados)
    return _Calculo(dados).executar()


def marco_prescricional(data_ajuizamento: date) -> date:
    """Prescrição quinquenal: alcança as parcelas anteriores a 5 anos do ajuizamento
    (art. 7º, XXIX, CF; Súmula 308, I, do TST)."""
    return somar_meses(data_ajuizamento, -60)


def _validar(d: DadosPedidos) -> None:
    erros = []
    if d.desligamento < d.admissao:
        erros.append("A data de desligamento não pode ser anterior à admissão.")
    if d.salario <= 0:
        erros.append("Informe o salário mensal.")
    if d.divisor <= 0:
        erros.append("O divisor de horas deve ser positivo.")
    if d.aviso not in AVISOS_PERMITIDOS[d.modalidade]:
        erros.append(f"Aviso prévio incompatível com {d.modalidade.rotulo.lower()}.")
    for percentual, nome in (
        (d.adicional_he_1, "1º adicional de horas extras"),
        (d.adicional_he_2, "2º adicional de horas extras"),
        (d.adicional_noturno, "adicional noturno"),
    ):
        if percentual < 0:
            erros.append(f"O percentual do {nome} não pode ser negativo.")
    for i, periodo in enumerate(d.periodos, start=1):
        if periodo.fim < periodo.inicio:
            erros.append(f"Período {i} de jornada: o fim é anterior ao início.")
        if min(periodo.horas_extras_1, periodo.horas_extras_2, periodo.horas_noturnas) < 0:
            erros.append(f"Período {i} de jornada: as horas não podem ser negativas.")
    if d.adicional_inicio and d.adicional_fim and d.adicional_fim < d.adicional_inicio:
        erros.append("Adicional de insalubridade/periculosidade: o fim é anterior ao início.")

    tem_horas = any(p.horas_extras_1 or p.horas_extras_2 or p.horas_noturnas for p in d.periodos)
    pede_adicional = d.adicional_ocupacional != AdicionalOcupacional.NENHUM and not d.adicional_ja_pago
    if not tem_horas and not pede_adicional:
        erros.append(
            "Informe ao menos um pedido: horas extras, horas noturnas ou adicional de insalubridade/periculosidade."
        )

    if d.data_ajuizamento and d.desligamento >= d.admissao:
        if d.data_ajuizamento > somar_meses(d.desligamento, 24):
            erros.append(
                "A ação foi ajuizada mais de 2 anos após o fim do contrato: a pretensão está prescrita "
                "(prescrição bienal, art. 7º, XXIX, CF)."
            )
        elif marco_prescricional(d.data_ajuizamento) > d.desligamento:
            erros.append("Todas as parcelas do contrato estão alcançadas pela prescrição quinquenal.")
        elif d.data_ajuizamento < d.admissao:
            erros.append("A data de ajuizamento não pode ser anterior à admissão.")

    if d.adicional_ocupacional.insalubridade and d.desligamento >= d.admissao:
        primeira = min(t.vigencia for t in tabelas_salario_minimo())
        inicio = max(d.admissao, d.adicional_inicio or d.admissao)
        if d.data_ajuizamento:
            inicio = max(inicio, marco_prescricional(d.data_ajuizamento))
        if inicio < primeira:
            erros.append(
                f"O sistema tem a tabela do salário mínimo a partir de {formatar_data(primeira)}. "
                "Informe a data de ajuizamento (prescrição) ou o início do adicional a partir dessa data."
            )
    if erros:
        raise ErroDeEntrada(erros)


def _fracao(inicio: date, fim: date) -> Decimal:
    """Parte do mês entre `inicio` e `fim` (mesmo mês): mês completo = 1; senão dias ÷ 30."""
    if fim < inicio:
        return ZERO
    if inicio.day == 1 and fim == ultimo_dia_do_mes(fim.year, fim.month):
        return UM
    return min(Decimal(dias_corridos(inicio, fim)) / 30, UM)


def _sobreposicao(a_inicio: date, a_fim: date, b_inicio: date, b_fim: date) -> tuple[date, date] | None:
    inicio, fim = max(a_inicio, b_inicio), min(a_fim, b_fim)
    return (inicio, fim) if inicio <= fim else None


@dataclass(frozen=True)
class _Mes:
    """Quantidades de uma competência usadas nos reflexos (Súmula 347 do TST)."""

    competencia: date
    inicio: date
    fim: date
    fracao: Decimal
    h1: Decimal
    h2: Decimal
    hn: Decimal  # horas noturnas já convertidas
    meses_adicional: Decimal  # fração do mês com adicional ocupacional devido
    razao_dsr: Decimal  # repousos ÷ dias úteis
    dsr_nos_reflexos: bool
    projetado: bool = False  # mês da projeção do aviso: só entra nos reflexos


@dataclass(frozen=True)
class _Pedido:
    nome: str
    codigo: str
    artigo: str  # "das" horas extras, "do" adicional noturno — para as descrições
    componentes: tuple[tuple[str, Decimal, str], ...]  # (atributo de _Mes, multiplicador, rótulo)
    com_dsr: bool
    base_adicional: bool  # base = valor mensal do adicional, e não o valor-hora
    fundamento_principal: str
    fundamento_reflexos: str


class _Calculo:
    def __init__(self, dados: DadosPedidos):
        self.d = dados
        self.alertas: list[str] = []
        self.lancamentos: list[Lancamento] = []
        self.marco = marco_prescricional(dados.data_ajuizamento) if dados.data_ajuizamento else None
        self.inicio = max(dados.admissao, self.marco) if self.marco else dados.admissao
        self.dias_aviso = dias_de_aviso(dados.admissao, dados.desligamento)
        self.dias_aviso_indenizados = dias_aviso_indenizados(dados.modalidade, dados.aviso, self.dias_aviso)
        self.data_projetada = dados.desligamento + timedelta(days=self.dias_aviso_indenizados)
        self.adicional_inicio = dados.adicional_inicio or dados.admissao
        self.adicional_fim = dados.adicional_fim or self.data_projetada
        self.meses: list[_Mes] = []
        self.mensal: list[LinhaMensal] = []

    # ------------------------------------------------------------------ bases

    def _adicional_cheio(self, data: date) -> Decimal:
        """Valor mensal integral do adicional ocupacional vigente em `data` (zero se inativo)."""
        tipo = self.d.adicional_ocupacional
        if tipo == AdicionalOcupacional.NENHUM or not (self.adicional_inicio <= data <= self.adicional_fim):
            return ZERO
        if tipo.insalubridade:
            return tipo.percentual * salario_minimo_vigente(data).valor
        return tipo.percentual * salario_em(self.d.historico_salarial, self.d.salario, data)

    def _valor_hora(self, data: date) -> Decimal:
        """(Salário + adicional de insalubridade/periculosidade) ÷ divisor (Súmulas 132 e 139 do TST)."""
        salario = salario_em(self.d.historico_salarial, self.d.salario, data)
        return (salario + self._adicional_cheio(data)) / self.d.divisor

    def _horas(self, inicio: date, fim: date, atributo: str) -> Decimal:
        total = ZERO
        for periodo in self.d.periodos:
            intervalo = _sobreposicao(inicio, fim, periodo.inicio, periodo.fim)
            if intervalo:
                total += getattr(periodo, atributo) * _fracao(*intervalo)
        return total

    def _meses_de_adicional(self, inicio: date, fim: date) -> Decimal:
        if self.d.adicional_ocupacional == AdicionalOcupacional.NENHUM or self.d.adicional_ja_pago:
            return ZERO
        intervalo = _sobreposicao(inicio, fim, self.adicional_inicio, self.adicional_fim)
        return _fracao(*intervalo) if intervalo else ZERO

    # ------------------------------------------------------------------ mês a mês

    def _competencias(self):
        d = self.d
        conversao = CONVERSAO_HORA_NOTURNA if d.hora_noturna_reduzida else UM
        for competencia in meses_entre(self.inicio, d.desligamento):
            inicio = max(competencia, self.inicio)
            fim = min(ultimo_dia_do_mes(competencia.year, competencia.month), d.desligamento)
            uteis, repousos = dias_uteis_e_repousos(competencia.year, competencia.month)
            razao = Decimal(repousos) / Decimal(uteis)
            h1 = self._horas(inicio, fim, "horas_extras_1")
            h2 = self._horas(inicio, fim, "horas_extras_2")
            hn = self._horas(inicio, fim, "horas_noturnas") * conversao
            meses_adicional = self._meses_de_adicional(inicio, fim)
            valor_hora = self._valor_hora(fim)
            adicional_cheio = self._adicional_cheio(fim)

            valor_he_1 = arredondar(h1 * valor_hora * (UM + d.adicional_he_1))
            valor_he_2 = arredondar(h2 * valor_hora * (UM + d.adicional_he_2))
            valor_noturno = arredondar(hn * valor_hora * d.adicional_noturno)
            valor_adicional = arredondar(meses_adicional * self._adicional_cheio(fim))

            self.meses.append(
                _Mes(
                    competencia,
                    inicio,
                    fim,
                    _fracao(inicio, fim),
                    h1,
                    h2,
                    hn,
                    meses_adicional,
                    razao,
                    competencia >= INICIO_DSR_NOS_REFLEXOS,
                )
            )
            self.mensal.append(
                LinhaMensal(
                    competencia=competencia,
                    fracao=_fracao(inicio, fim),
                    salario=salario_em(d.historico_salarial, d.salario, fim),
                    adicional_ocupacional=arredondar(adicional_cheio),
                    valor_hora=valor_hora,
                    horas_extras_1=h1,
                    horas_extras_2=h2,
                    horas_noturnas=hn,
                    valor_he_1=valor_he_1,
                    valor_he_2=valor_he_2,
                    valor_noturno=valor_noturno,
                    valor_adicional=valor_adicional,
                    dias_uteis=uteis,
                    repousos=repousos,
                    dsr_he=arredondar((valor_he_1 + valor_he_2) * razao),
                    dsr_noturno=arredondar(valor_noturno * razao),
                )
            )

    def _meses_projetados(self):
        """Meses da projeção do aviso indenizado, com a média dos últimos 12 meses.
        Entram só no 13º e nas férias (art. 487, § 1º, CLT; OJ 82 da SDI-1)."""
        if not self.dias_aviso_indenizados or not self.meses:
            return
        ultimos = self.meses[-12:]
        soma_fracoes = sum((m.fracao for m in ultimos), ZERO)
        if soma_fracoes == 0:
            return
        media = {
            atributo: sum((getattr(m, atributo) for m in ultimos), ZERO) / soma_fracoes
            for atributo in ("h1", "h2", "hn")
        }
        inicio_projecao = self.d.desligamento + UM_DIA
        for competencia in meses_entre(inicio_projecao, self.data_projetada):
            inicio = max(competencia, inicio_projecao)
            fim = min(ultimo_dia_do_mes(competencia.year, competencia.month), self.data_projetada)
            fracao = _fracao(inicio, fim)
            uteis, repousos = dias_uteis_e_repousos(competencia.year, competencia.month)
            self.meses.append(
                _Mes(
                    competencia,
                    inicio,
                    fim,
                    fracao,
                    media["h1"] * fracao,
                    media["h2"] * fracao,
                    media["hn"] * fracao,
                    self._meses_de_adicional(inicio, fim),
                    Decimal(repousos) / Decimal(uteis),
                    competencia >= INICIO_DSR_NOS_REFLEXOS,
                    projetado=True,
                )
            )

    # ------------------------------------------------------------------ reflexos

    def _base(self, pedido: _Pedido, data: date) -> Decimal:
        if pedido.base_adicional:
            # Época do pagamento, limitada ao período em que o adicional era devido
            return self._adicional_cheio(min(max(data, self.adicional_inicio), self.adicional_fim))
        return self._valor_hora(data)

    def _quantidade(self, pedido: _Pedido, atributo: str, meses: list[tuple[_Mes, Decimal]]) -> Decimal:
        total = ZERO
        for mes, peso in meses:
            fator = UM + mes.razao_dsr if pedido.com_dsr and mes.dsr_nos_reflexos else UM
            total += getattr(mes, atributo) * peso * fator
        return total

    def _reflexo(self, pedido: _Pedido, meses, data_base: date, divisor: Decimal) -> tuple[Decimal, str]:
        """Σ quantidade × base da época × multiplicador ÷ divisor (Súmula 347 do TST)."""
        base = self._base(pedido, data_base)
        total = ZERO
        partes = []
        for atributo, multiplicador, rotulo in pedido.componentes:
            quantidade = self._quantidade(pedido, atributo, meses)
            if quantidade == 0:
                continue
            total += quantidade * base * multiplicador
            if pedido.base_adicional:
                partes.append(f"{formatar_numero(quantidade)} mês(es) × {formatar_brl(base)}")
            else:
                fator = formatar_numero(multiplicador, 4).rstrip("0").rstrip(",")
                partes.append(f"{formatar_numero(quantidade)} {rotulo} × {formatar_brl(base)} × {fator}")
        return total / divisor, " + ".join(partes)

    def _janela(self, inicio: date, fim: date) -> list[tuple[_Mes, Decimal]]:
        """Meses (com o peso da parte dentro da janela) que caem entre `inicio` e `fim`."""
        selecionados = []
        for mes in self.meses:
            intervalo = _sobreposicao(mes.inicio, mes.fim, inicio, fim)
            if intervalo:
                peso = Decimal(dias_corridos(*intervalo)) / Decimal(dias_corridos(mes.inicio, mes.fim))
                selecionados.append((mes, peso))
        return selecionados

    def _reflexo_13(self, pedido: _Pedido) -> tuple[Decimal, list[str], list[tuple[date, Decimal]]]:
        d = self.d
        total, partes, parcelas = ZERO, [], []
        for ano in range(self.meses[0].competencia.year, self.data_projetada.year + 1):
            ultimo_ano = ano >= d.desligamento.year
            if ultimo_ano and d.modalidade == Modalidade.JUSTA_CAUSA:
                continue
            meses = self._janela(date(ano, 1, 1), date(ano, 12, 31))
            if not meses:
                continue
            data_base = min(date(ano, 12, 31), d.desligamento)
            valor, memoria = self._reflexo(pedido, meses, data_base, DOZE)
            if ultimo_ano and d.modalidade == Modalidade.CULPA_RECIPROCA:
                valor *= METADE
                memoria += " × 50%"
            valor = arredondar(valor)
            if valor:
                total += valor
                partes.append(f"{ano}: ({memoria}) ÷ 12 = {formatar_brl(valor)}")
                competencia = date(ano, 12, 1) if not ultimo_ano else primeiro_dia_do_mes(d.desligamento)
                parcelas.append((competencia, valor))
        return total, partes, parcelas

    def _reflexo_ferias(self, pedido: _Pedido) -> tuple[Decimal, list[str], list[tuple[date, Decimal]]]:
        d = self.d
        total, partes, parcelas = ZERO, [], []
        k = 0
        while (inicio := somar_meses(d.admissao, 12 * k)) <= self.data_projetada:
            fim = somar_meses(d.admissao, 12 * (k + 1)) - UM_DIA
            k += 1
            completo = fim <= self.data_projetada
            if not completo and d.modalidade == Modalidade.JUSTA_CAUSA:
                continue
            meses = self._janela(inicio, fim)
            if not meses:
                continue
            valor, memoria = self._reflexo(pedido, meses, min(fim, d.desligamento), DOZE)
            valor *= QUATRO_TERCOS
            memoria = f"({memoria}) ÷ 12 × 4/3"
            if not completo and d.modalidade == Modalidade.CULPA_RECIPROCA:
                valor *= METADE
                memoria += " × 50%"
            valor = arredondar(valor)
            if valor:
                total += valor
                partes.append(f"{formatar_data(inicio)} a {formatar_data(fim)}: {memoria} = {formatar_brl(valor)}")
                parcelas.append((primeiro_dia_do_mes(min(fim + UM_DIA, d.desligamento)), valor))
        return total, partes, parcelas

    def _reflexo_aviso(self, pedido: _Pedido) -> tuple[Decimal, str]:
        if not self.dias_aviso_indenizados:
            return ZERO, ""
        reais = [m for m in self.meses if not m.projetado][-12:]
        soma_fracoes = sum((m.fracao for m in reais), ZERO)
        if soma_fracoes == 0:
            return ZERO, ""
        valor, memoria = self._reflexo(pedido, [(m, UM) for m in reais], self.d.desligamento, soma_fracoes)
        valor = valor * self.dias_aviso_indenizados / 30
        memoria = (
            f"média de {formatar_numero(soma_fracoes)} mês(es): ({memoria}) ÷ {formatar_numero(soma_fracoes)}"
            f" × {self.dias_aviso_indenizados}/30 dias"
        )
        if self.d.modalidade in AVISO_PELA_METADE:
            valor *= METADE
            memoria += " × 50%"
        return arredondar(valor), memoria

    # ------------------------------------------------------------------ lançamentos

    def _lancar(self, pedido, codigo, descricao, grupo, valor, formula, fundamento, natureza="Salarial", parcelas=()):
        valor = arredondar(valor)
        if valor > 0:
            self.lancamentos.append(
                Lancamento(
                    codigo,
                    descricao,
                    grupo,
                    valor,
                    natureza,
                    formula,
                    fundamento,
                    pedido=pedido.nome,
                    parcelas=tuple(parcelas),
                )
            )
        return valor

    def _periodo_texto(self, linhas: list[LinhaMensal]) -> str:
        return f"{linhas[0].competencia:%m/%Y} a {linhas[-1].competencia:%m/%Y}"

    def _pedido(self, pedido: _Pedido, principais: list[tuple[str, str, str]], dsr_campo: str | None):
        """principais: (campo de LinhaMensal, código, descrição)."""
        base_fgts = ZERO
        parcelas_fgts: list[tuple[date, Decimal]] = []  # composição mensal da base do FGTS
        for campo, codigo, descricao in principais:
            linhas = [linha for linha in self.mensal if getattr(linha, campo) > 0]
            if not linhas:
                continue
            total = sum((getattr(linha, campo) for linha in linhas), ZERO)
            parcelas = [(linha.competencia, getattr(linha, campo)) for linha in linhas]
            parcelas_fgts += parcelas
            base_fgts += self._lancar(
                pedido,
                codigo,
                descricao,
                Grupo.PROVENTO,
                total,
                f"Soma de {len(linhas)} competência(s), de {self._periodo_texto(linhas)} "
                "(valores mês a mês no demonstrativo mensal).",
                pedido.fundamento_principal,
                parcelas=parcelas,
            )
        if base_fgts == 0:
            return

        prefixo = pedido.nome.lower()
        codigo, artigo = pedido.codigo, pedido.artigo
        if dsr_campo:
            dsr = sum((getattr(linha, dsr_campo) for linha in self.mensal), ZERO)
            parcelas = [(linha.competencia, getattr(linha, dsr_campo)) for linha in self.mensal]
            parcelas_fgts += parcelas
            base_fgts += self._lancar(
                pedido,
                f"{codigo}_dsr",
                f"Reflexo {artigo} {prefixo} no DSR",
                Grupo.PROVENTO,
                dsr,
                "Em cada mês: valor ÷ dias úteis × domingos e feriados (demonstrativo mensal).",
                "Lei nº 605/1949, art. 7º; Súmula 172 do TST. Feriados nacionais apenas.",
                parcelas=parcelas,
            )

        reflexo_13, partes, parcelas = self._reflexo_13(pedido)
        parcelas_fgts += parcelas
        base_fgts += self._lancar(
            pedido,
            f"{codigo}_13",
            f"Reflexo {artigo} {prefixo} no 13º salário",
            Grupo.PROVENTO,
            reflexo_13,
            "; ".join(partes),
            f"Súmula 45 do TST. {pedido.fundamento_reflexos}",
            parcelas=parcelas,
        )
        reflexo_ferias, partes, parcelas = self._reflexo_ferias(pedido)
        self._lancar(
            pedido,
            f"{codigo}_ferias",
            f"Reflexo {artigo} {prefixo} em férias + 1/3",
            Grupo.PROVENTO,
            reflexo_ferias,
            "; ".join(partes),
            f"Art. 142, §§ 5º e 6º, CLT; art. 7º, XVII, CF. {pedido.fundamento_reflexos}",
            "Indenizatória",
            parcelas=parcelas,
        )
        reflexo_aviso, memoria = self._reflexo_aviso(pedido)
        mes_rescisao = primeiro_dia_do_mes(self.d.desligamento)
        parcelas_fgts.append((mes_rescisao, reflexo_aviso))
        base_fgts += self._lancar(
            pedido,
            f"{codigo}_aviso",
            f"Reflexo {artigo} {prefixo} no aviso prévio",
            Grupo.PROVENTO,
            reflexo_aviso,
            memoria,
            f"Art. 487, § 5º, CLT. {pedido.fundamento_reflexos}",
            "Indenizatória",
            parcelas=[(mes_rescisao, reflexo_aviso)],
        )

        fgts = self._lancar(
            pedido,
            f"{codigo}_fgts",
            f"FGTS (8%) sobre {prefixo} e reflexos",
            Grupo.FGTS,
            base_fgts * ALIQUOTA_FGTS,
            f"8% × {formatar_brl(base_fgts)} (parcela, DSR, 13º e aviso; não incide sobre férias indenizadas)",
            "Art. 15, Lei nº 8.036/1990; Súmula 63 do TST; OJ 195 da SDI-1.",
            "FGTS",
            parcelas=[(competencia, valor * ALIQUOTA_FGTS) for competencia, valor in parcelas_fgts if valor],
        )
        percentual = MULTA_FGTS.get(self.d.modalidade)
        if percentual:
            self._lancar(
                pedido,
                f"{codigo}_multa_fgts",
                f"Multa de {int(percentual * 100)}% sobre o FGTS de {prefixo}",
                Grupo.FGTS,
                fgts * percentual,
                f"{int(percentual * 100)}% × {formatar_brl(fgts)}",
                (
                    "Art. 484-A, I, b, CLT."
                    if self.d.modalidade == Modalidade.ACORDO
                    else "Art. 18, § 2º, Lei nº 8.036/1990; Súmula 14 do TST."
                    if self.d.modalidade == Modalidade.CULPA_RECIPROCA
                    else "Art. 18, § 1º, Lei nº 8.036/1990."
                ),
                "Indenizatória",
                parcelas=[(mes_rescisao, fgts * percentual)],
            )

    # ------------------------------------------------------------------ execução

    def executar(self) -> ResultadoPedidos:
        d = self.d
        self._competencias()
        self._meses_projetados()

        divisor = f"divisor {d.divisor}"
        if d.divisor == 200:
            divisor += " (Súmula 431 do TST)"
        reflexos_he = "Súmula 347 do TST (média física × valor-hora da época)."
        reflexos_he += " DSR integra os reflexos a partir de 04/2023: OJ 394 da SDI-1 (IRR de 2023)."

        self._pedido(
            _Pedido(
                PEDIDO_HE,
                "he",
                "das",
                (
                    ("h1", UM + d.adicional_he_1, f"h ({formatar_percentual(d.adicional_he_1)})"),
                    ("h2", UM + d.adicional_he_2, f"h ({formatar_percentual(d.adicional_he_2)})"),
                ),
                com_dsr=True,
                base_adicional=False,
                fundamento_principal=f"Art. 7º, XVI, CF; art. 59, CLT; {divisor}. "
                "Base: salário + insalubridade/periculosidade (Súmulas 132 e 139 do TST; Súmula 264).",
                fundamento_reflexos=reflexos_he,
            ),
            [
                ("valor_he_1", "he_1", f"Horas extras ({formatar_percentual(d.adicional_he_1)})"),
                ("valor_he_2", "he_2", f"Horas extras ({formatar_percentual(d.adicional_he_2)})"),
            ],
            "dsr_he",
        )
        self._pedido(
            _Pedido(
                PEDIDO_NOTURNO,
                "noturno",
                "do",
                (("hn", d.adicional_noturno, "h noturnas"),),
                com_dsr=True,
                base_adicional=False,
                fundamento_principal=(
                    f"Art. 73, CLT ({formatar_percentual(d.adicional_noturno)}"
                    + (", hora noturna de 52min30s" if d.hora_noturna_reduzida else "")
                    + f"); {divisor}."
                ),
                fundamento_reflexos="Súmula 60, I, do TST; Súmula 347 do TST.",
            ),
            [("valor_noturno", "noturno", "Adicional noturno")],
            "dsr_noturno",
        )
        tipo = d.adicional_ocupacional
        if tipo != AdicionalOcupacional.NENHUM and not d.adicional_ja_pago:
            if tipo.insalubridade:
                nome = "Adicional de insalubridade"
                fundamento = "Art. 192, CLT; base no salário mínimo (Súmula Vinculante 4 do STF)."
            else:
                nome = "Adicional de periculosidade"
                fundamento = "Art. 193, § 1º, CLT; Súmula 191 do TST (sobre o salário-base)."
            self._pedido(
                _Pedido(
                    nome,
                    "adicional",
                    "do",
                    (("meses_adicional", UM, "mês(es)"),),
                    com_dsr=False,
                    base_adicional=True,
                    fundamento_principal=fundamento + " Não gera reflexo em DSR (OJ 103 da SDI-1).",
                    fundamento_reflexos="Valor do adicional na época do pagamento de cada parcela.",
                ),
                [("valor_adicional", "adicional", f"{tipo.rotulo}")],
                None,
            )

        self._alertas()
        return ResultadoPedidos(
            "Memória de cálculo de horas extras e adicionais",
            self.lancamentos,
            self.alertas,
            self._resumo(),
            d,
            self.mensal,
        )

    def _alertas(self):
        d = self.d
        if not d.data_ajuizamento:
            self.alertas.append(
                "Sem data de ajuizamento, o cálculo considera o contrato inteiro. Para a petição inicial, "
                "informe a data prevista de distribuição: a prescrição quinquenal exclui as parcelas "
                "anteriores a 5 anos dessa data."
            )
        elif self.marco and self.marco > d.admissao:
            self.alertas.append(
                f"Parcelas anteriores a {formatar_data(self.marco)} estão prescritas e foram excluídas "
                f"(prescrição quinquenal contada do ajuizamento em {formatar_data(d.data_ajuizamento)})."
            )
        for i, periodo in enumerate(d.periodos, start=1):
            if periodo.inicio < d.admissao or periodo.fim > d.desligamento:
                self.alertas.append(
                    f"O período {i} de jornada ultrapassa o contrato; foi considerado só entre "
                    f"{formatar_data(d.admissao)} e {formatar_data(d.desligamento)}."
                )
        if d.adicional_ocupacional.insalubridade:
            ultima = max(t.vigencia for t in tabelas_salario_minimo())
            if self.data_projetada.year > ultima.year:
                self.alertas.append(f"A tabela de salário mínimo vai até {ultima.year}; confira se há valor novo.")

    def _resumo(self) -> dict[str, str]:
        d = self.d
        resumo = {
            "Modalidade": d.modalidade.rotulo,
            "Admissão": formatar_data(d.admissao),
            "Desligamento": formatar_data(d.desligamento),
            "Período calculado": f"{formatar_data(self.inicio)} a {formatar_data(d.desligamento)}",
        }
        if d.data_ajuizamento:
            resumo["Ajuizamento"] = formatar_data(d.data_ajuizamento)
            resumo["Marco prescricional"] = formatar_data(self.marco)
        resumo["Divisor"] = str(d.divisor)
        resumo["Adicionais de horas extras"] = (
            f"{formatar_percentual(d.adicional_he_1)} e {formatar_percentual(d.adicional_he_2)}"
        )
        if any(p.horas_noturnas for p in d.periodos):
            resumo["Adicional noturno"] = formatar_percentual(d.adicional_noturno) + (
                " com hora reduzida (52min30s)" if d.hora_noturna_reduzida else ""
            )
        if d.adicional_ocupacional != AdicionalOcupacional.NENHUM:
            resumo["Insalubridade/periculosidade"] = d.adicional_ocupacional.rotulo + (
                " (já pago: só integra a base das horas extras)" if d.adicional_ja_pago else ""
            )
        if self.dias_aviso_indenizados:
            resumo["Aviso indenizado"] = (
                f"{self.dias_aviso_indenizados} dias, projeção até {formatar_data(self.data_projetada)}"
            )
        return resumo
