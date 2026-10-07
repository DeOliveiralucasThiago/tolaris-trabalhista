"""Salvar e abrir um caso em JSON, para o advogado guardar no próprio computador."""

import json
from dataclasses import fields
from datetime import date
from decimal import Decimal

from tolaris.motor.modelos import AlteracaoSalarial, Aviso, DadosRescisao, Modalidade

VERSAO = 1


def caso_para_json(dados: DadosRescisao) -> str:
    conteudo = {}
    for campo in fields(dados):
        valor = getattr(dados, campo.name)
        if campo.name == "historico_salarial":
            valor = [{"inicio": a.inicio.isoformat(), "salario": str(a.salario)} for a in valor]
        elif isinstance(valor, date):
            valor = valor.isoformat()
        elif isinstance(valor, Decimal):
            valor = str(valor)
        conteudo[campo.name] = valor
    return json.dumps({"versao": VERSAO, "tipo": "rescisao", "dados": conteudo}, ensure_ascii=False, indent=2)


def caso_de_json(texto: str) -> DadosRescisao:
    pacote = json.loads(texto)
    if pacote.get("tipo") != "rescisao" or pacote.get("versao") != VERSAO:
        raise ValueError("Arquivo de caso não reconhecido ou de versão incompatível.")
    c = pacote["dados"]

    def decimal_ou_none(valor):
        return None if valor is None else Decimal(valor)

    return DadosRescisao(
        admissao=date.fromisoformat(c["admissao"]),
        desligamento=date.fromisoformat(c["desligamento"]),
        modalidade=Modalidade(c["modalidade"]),
        aviso=Aviso(c["aviso"]),
        salario=Decimal(c["salario"]),
        media_variaveis=Decimal(c["media_variaveis"]),
        historico_salarial=[
            AlteracaoSalarial(date.fromisoformat(a["inicio"]), Decimal(a["salario"])) for a in c["historico_salarial"]
        ],
        ferias_vencidas=int(c["ferias_vencidas"]),
        faltas_periodo_aquisitivo=int(c["faltas_periodo_aquisitivo"]),
        faltas_mes_rescisao=int(c["faltas_mes_rescisao"]),
        dependentes_ir=int(c["dependentes_ir"]),
        decimo_terceiro_pago=Decimal(c["decimo_terceiro_pago"]),
        saldo_fgts=decimal_ou_none(c["saldo_fgts"]),
        pagamento_em_atraso=bool(c["pagamento_em_atraso"]),
        multa_467=bool(c["multa_467"]),
        outros_descontos=Decimal(c["outros_descontos"]),
    )
