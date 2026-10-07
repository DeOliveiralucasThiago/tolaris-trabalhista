"""Entradas e saídas do cálculo de rescisão."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from tolaris.dinheiro import ZERO


class Modalidade(StrEnum):
    SEM_JUSTA_CAUSA = "sem_justa_causa"
    PEDIDO_DEMISSAO = "pedido_demissao"
    JUSTA_CAUSA = "justa_causa"
    RESCISAO_INDIRETA = "rescisao_indireta"
    ACORDO = "acordo"
    CULPA_RECIPROCA = "culpa_reciproca"

    @property
    def rotulo(self) -> str:
        return ROTULOS_MODALIDADE[self]


ROTULOS_MODALIDADE = {
    Modalidade.SEM_JUSTA_CAUSA: "Dispensa sem justa causa",
    Modalidade.PEDIDO_DEMISSAO: "Pedido de demissão",
    Modalidade.JUSTA_CAUSA: "Dispensa por justa causa",
    Modalidade.RESCISAO_INDIRETA: "Rescisão indireta (art. 483 CLT)",
    Modalidade.ACORDO: "Acordo entre as partes (art. 484-A CLT)",
    Modalidade.CULPA_RECIPROCA: "Culpa recíproca (art. 484 CLT)",
}


class Aviso(StrEnum):
    INDENIZADO = "indenizado"
    TRABALHADO = "trabalhado"
    NAO_CUMPRIDO = "nao_cumprido"  # pedido de demissão: empregado não cumpriu, empregador desconta
    DISPENSADO = "dispensado"  # pedido de demissão: empregador dispensou o cumprimento
    NAO_SE_APLICA = "nao_se_aplica"  # justa causa

    @property
    def rotulo(self) -> str:
        return ROTULOS_AVISO[self]


ROTULOS_AVISO = {
    Aviso.INDENIZADO: "Indenizado",
    Aviso.TRABALHADO: "Trabalhado",
    Aviso.NAO_CUMPRIDO: "Não cumprido pelo empregado (será descontado)",
    Aviso.DISPENSADO: "Dispensado pelo empregador (sem desconto)",
    Aviso.NAO_SE_APLICA: "Não se aplica",
}

AVISOS_PERMITIDOS = {
    Modalidade.SEM_JUSTA_CAUSA: (Aviso.INDENIZADO, Aviso.TRABALHADO),
    Modalidade.RESCISAO_INDIRETA: (Aviso.INDENIZADO,),
    Modalidade.ACORDO: (Aviso.INDENIZADO, Aviso.TRABALHADO),
    Modalidade.CULPA_RECIPROCA: (Aviso.INDENIZADO,),
    Modalidade.PEDIDO_DEMISSAO: (Aviso.TRABALHADO, Aviso.NAO_CUMPRIDO, Aviso.DISPENSADO),
    Modalidade.JUSTA_CAUSA: (Aviso.NAO_SE_APLICA,),
}


@dataclass(frozen=True)
class AlteracaoSalarial:
    """Salário mensal vigente a partir de `inicio`."""

    inicio: date
    salario: Decimal


@dataclass
class DadosRescisao:
    admissao: date
    desligamento: date  # último dia efetivamente trabalhado
    modalidade: Modalidade
    aviso: Aviso
    salario: Decimal  # salário mensal na data do desligamento
    media_variaveis: Decimal = ZERO  # média mensal de horas extras, comissões etc.
    historico_salarial: list[AlteracaoSalarial] = field(default_factory=list)  # só para estimar o FGTS
    ferias_vencidas: int = 0  # períodos aquisitivos completos e não gozados
    faltas_periodo_aquisitivo: int = 0  # faltas injustificadas no período aquisitivo em curso
    faltas_mes_rescisao: int = 0  # faltas injustificadas no mês do desligamento (dias)
    dependentes_ir: int = 0
    decimo_terceiro_pago: Decimal = ZERO  # adiantamento (1ª parcela) já pago no ano
    saldo_fgts: Decimal | None = None  # saldo para fins rescisórios, do extrato; None = estimar
    pagamento_em_atraso: bool = False  # multa do art. 477, § 8º
    multa_467: bool = False
    outros_descontos: Decimal = ZERO


class Grupo(StrEnum):
    PROVENTO = "Provento"
    DESCONTO = "Desconto"
    FGTS = "FGTS"


@dataclass(frozen=True)
class Lancamento:
    codigo: str
    descricao: str
    grupo: Grupo
    valor: Decimal
    natureza: str
    formula: str
    fundamento: str


@dataclass
class ResultadoRescisao:
    dados: DadosRescisao
    lancamentos: list[Lancamento]
    alertas: list[str]
    resumo: dict[str, str]  # informações do contrato apuradas (tempo de serviço, aviso, datas)

    def _soma(self, grupo: Grupo) -> Decimal:
        return sum((item.valor for item in self.lancamentos if item.grupo == grupo), ZERO)

    @property
    def total_proventos(self) -> Decimal:
        return self._soma(Grupo.PROVENTO)

    @property
    def total_descontos(self) -> Decimal:
        return self._soma(Grupo.DESCONTO)

    @property
    def liquido(self) -> Decimal:
        return self.total_proventos - self.total_descontos

    @property
    def total_fgts(self) -> Decimal:
        return self._soma(Grupo.FGTS)

    @property
    def total_geral(self) -> Decimal:
        return self.liquido + self.total_fgts

    def do_grupo(self, grupo: Grupo) -> list[Lancamento]:
        return [item for item in self.lancamentos if item.grupo == grupo]


class ErroDeEntrada(ValueError):
    def __init__(self, mensagens: list[str]):
        super().__init__("; ".join(mensagens))
        self.mensagens = mensagens
