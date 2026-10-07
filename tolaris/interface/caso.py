"""Salvar e abrir um caso: o arquivo .json guarda o formulário preenchido.

O arquivo fica no computador do advogado; nada é armazenado no servidor.
"""

import json
from datetime import date
from enum import Enum

from tolaris.motor.modelos import AdicionalOcupacional, Aviso, Modalidade

VERSAO = 2
ENUMS = {cls.__name__: cls for cls in (Modalidade, Aviso, AdicionalOcupacional)}

# Campos do formulário salvos no caso (chaves do st.session_state)
CAMPOS = (
    "modo",
    "admissao",
    "desligamento",
    "salario",
    "usar_historico",
    "modalidade",
    "aviso",
    # rescisão
    "media_variaveis",
    "ferias_vencidas",
    "faltas_periodo_aquisitivo",
    "faltas_mes_rescisao",
    "decimo_terceiro_pago",
    "informar_saldo_fgts",
    "saldo_fgts",
    "pagamento_em_atraso",
    "multa_467",
    "dependentes_ir",
    "outros_descontos",
    # horas extras e adicionais
    "divisor",
    "adicional_he_1",
    "adicional_he_2",
    "adicional_noturno",
    "hora_noturna_reduzida",
    "adicional_ocupacional",
    "adicional_todo_contrato",
    "adicional_inicio",
    "adicional_fim",
    "adicional_ja_pago",
    "considerar_prescricao",
    "data_ajuizamento",
    # atualização
    "atualizar",
    "data_atualizacao",
    "juros_pre_judiciais",
)
TABELAS = ("historico", "periodos")


def _codificar(valor):
    if isinstance(valor, Enum):
        return {"enum": type(valor).__name__, "valor": valor.value}
    if isinstance(valor, date):
        return {"data": valor.isoformat()}
    if isinstance(valor, list):
        return [_codificar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _codificar(v) for k, v in valor.items()}
    return valor


def _decodificar(valor):
    if isinstance(valor, dict):
        if set(valor) == {"enum", "valor"}:
            return ENUMS[valor["enum"]](valor["valor"])
        if set(valor) == {"data"}:
            return date.fromisoformat(valor["data"])
        return {k: _decodificar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_decodificar(v) for v in valor]
    return valor


def formulario_para_json(campos: dict, tabelas: dict[str, list[dict]]) -> str:
    conteudo = {
        "versao": VERSAO,
        "campos": {k: _codificar(v) for k, v in campos.items() if k in CAMPOS},
        "tabelas": {k: _codificar(v) for k, v in tabelas.items() if k in TABELAS},
    }
    return json.dumps(conteudo, ensure_ascii=False, indent=2)


def formulario_de_json(texto: str) -> tuple[dict, dict[str, list[dict]]]:
    conteudo = json.loads(texto)
    if conteudo.get("versao") != VERSAO:
        raise ValueError("Arquivo de caso não reconhecido ou de versão incompatível.")
    campos = {k: _decodificar(v) for k, v in conteudo.get("campos", {}).items() if k in CAMPOS}
    tabelas = {k: _decodificar(v) for k, v in conteudo.get("tabelas", {}).items() if k in TABELAS}
    return campos, tabelas
