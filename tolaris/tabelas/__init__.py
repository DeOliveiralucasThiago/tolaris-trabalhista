"""Tabelas oficiais (INSS, IRRF, salário mínimo) organizadas por data de vigência.

Cada arquivo JSON lista tabelas com o campo `vigencia`: a tabela vale dessa data até a
vigência da próxima. Datas anteriores à primeira tabela geram `TabelaIndisponivel`;
o cálculo nunca usa a tabela de outro período sem avisar.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

PASTA = Path(__file__).parent


class TabelaIndisponivel(LookupError):
    pass


@dataclass(frozen=True)
class FaixaINSS:
    ate: Decimal
    aliquota: Decimal


@dataclass(frozen=True)
class TabelaINSS:
    vigencia: date
    tipo: str  # "progressiva" (desde 03/2020) ou "aliquota_unica"
    fonte: str
    faixas: tuple[FaixaINSS, ...]

    @property
    def teto(self) -> Decimal:
        return self.faixas[-1].ate


@dataclass(frozen=True)
class FaixaIRRF:
    ate: Decimal | None  # None = sem limite
    aliquota: Decimal
    parcela: Decimal


@dataclass(frozen=True)
class RedutorIRRF:
    """Redução mensal do imposto (Lei nº 15.270/2025)."""

    isencao_ate: Decimal
    reducao_maxima: Decimal
    decrescente_ate: Decimal
    constante: Decimal
    coeficiente: Decimal


@dataclass(frozen=True)
class TabelaIRRF:
    vigencia: date
    fonte: str
    deducao_dependente: Decimal
    desconto_simplificado: Decimal | None
    redutor: RedutorIRRF | None
    faixas: tuple[FaixaIRRF, ...]


@dataclass(frozen=True)
class SalarioMinimo:
    vigencia: date
    valor: Decimal
    fonte: str


def _ler(nome: str) -> list[dict]:
    with open(PASTA / nome, encoding="utf-8") as arquivo:
        return json.load(arquivo)["tabelas"]


def _dec(valor) -> Decimal | None:
    return None if valor is None else Decimal(valor)


@cache
def tabelas_inss() -> tuple[TabelaINSS, ...]:
    return tuple(
        TabelaINSS(
            vigencia=date.fromisoformat(t["vigencia"]),
            tipo=t["tipo"],
            fonte=t["fonte"],
            faixas=tuple(FaixaINSS(Decimal(f["ate"]), Decimal(f["aliquota"])) for f in t["faixas"]),
        )
        for t in _ler("inss.json")
    )


@cache
def tabelas_irrf() -> tuple[TabelaIRRF, ...]:
    return tuple(
        TabelaIRRF(
            vigencia=date.fromisoformat(t["vigencia"]),
            fonte=t["fonte"],
            deducao_dependente=Decimal(t["deducao_dependente"]),
            desconto_simplificado=_dec(t["desconto_simplificado"]),
            redutor=RedutorIRRF(**{k: Decimal(v) for k, v in t["redutor"].items()}) if t["redutor"] else None,
            faixas=tuple(FaixaIRRF(_dec(f["ate"]), Decimal(f["aliquota"]), Decimal(f["parcela"])) for f in t["faixas"]),
        )
        for t in _ler("irrf.json")
    )


@cache
def tabelas_salario_minimo() -> tuple[SalarioMinimo, ...]:
    return tuple(
        SalarioMinimo(date.fromisoformat(t["vigencia"]), Decimal(t["valor"]), t["fonte"])
        for t in _ler("salario_minimo.json")
    )


def _vigente(tabelas, data: date, nome: str):
    candidatas = [t for t in tabelas if t.vigencia <= data]
    if not candidatas:
        primeira = min(t.vigencia for t in tabelas)
        raise TabelaIndisponivel(
            f"Não há tabela de {nome} para {data:%d/%m/%Y}. O sistema cobre datas a partir de {primeira:%d/%m/%Y}."
        )
    return max(candidatas, key=lambda t: t.vigencia)


def inss_vigente(data: date) -> TabelaINSS:
    return _vigente(tabelas_inss(), data, "INSS")


def irrf_vigente(data: date) -> TabelaIRRF:
    return _vigente(tabelas_irrf(), data, "IRRF")


def salario_minimo_vigente(data: date) -> SalarioMinimo:
    return _vigente(tabelas_salario_minimo(), data, "salário mínimo")


def aviso_tabela_desatualizada(data: date) -> str | None:
    """Alerta quando a data é de um ano posterior ao da tabela mais recente cadastrada.

    As tabelas mudam todo ano; aplicar a do ano anterior pode estar errado."""
    ultimas = {
        "INSS": max(t.vigencia for t in tabelas_inss()),
        "IRRF": max(t.vigencia for t in tabelas_irrf()),
    }
    atrasadas = [nome for nome, vigencia in ultimas.items() if data.year > vigencia.year]
    if not atrasadas:
        return None
    return (
        f"A tabela mais recente de {' e '.join(atrasadas)} cadastrada no sistema é anterior a "
        f"{data.year}. Confira se já existe tabela nova antes de usar este resultado."
    )


@dataclass(frozen=True)
class Indices:
    """Séries mensais em fração (0,0042 = 0,42%), indexadas por "AAAA-MM"."""

    series: dict[str, dict[str, Decimal]]
    atualizado_em: date | None = None

    def valor(self, serie: str, competencia: date) -> Decimal | None:
        return self.series.get(serie, {}).get(f"{competencia:%Y-%m}")

    def ultimo_mes(self, serie: str) -> date | None:
        meses = self.series.get(serie)
        if not meses:
            return None
        ano, mes = max(meses).split("-")
        return date(int(ano), int(mes), 1)


@cache
def indices() -> Indices:
    caminho = PASTA / "indices.json"
    if not caminho.exists():
        raise TabelaIndisponivel(
            "A tabela de índices do Banco Central ainda não foi baixada "
            "(rode scripts/atualizar_indices.py ou a rotina 'Atualizar índices' do GitHub)."
        )
    with open(caminho, encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    series = {
        nome: {mes: Decimal(valor) / 100 for mes, valor in meses.items()} for nome, meses in conteudo["series"].items()
    }
    return Indices(series, date.fromisoformat(conteudo["atualizado_em"]))
