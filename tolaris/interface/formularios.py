"""Seções do formulário. Cada função desenha campos e devolve os valores digitados.

Os campos usam chaves fixas no st.session_state para que o caso possa ser salvo e reaberto.
"""

from datetime import date
from decimal import Decimal

import streamlit as st

from tolaris.dinheiro import arredondar
from tolaris.interface.caso import CAMPOS, TABELAS
from tolaris.motor.atualizacao import ParametrosAtualizacao
from tolaris.motor.modelos import (
    AVISOS_PERMITIDOS,
    AdicionalOcupacional,
    AlteracaoSalarial,
    DadosLiquidacao,
    DadosPedidos,
    DadosRescisao,
    DsrNosReflexos,
    Modalidade,
    NaturezaPagamento,
    OutraVerba,
    Pagamento,
    PeriodoJornada,
    ValorPago,
    VerbaRescisoria,
)

DATA_MINIMA = date(1960, 1, 1)  # o cálculo avisa quando faltar tabela para o período
DIVISORES = {220: "220 (44 h semanais)", 200: "200 (40 h semanais)", 180: "180 (36 h semanais)", 150: "150 (30 h)"}
PADROES = {
    "admissao": None,
    "desligamento": None,
    "salario": 0.0,
    "media_variaveis": 0.0,
    "ferias_vencidas": 0,
    "faltas_periodo_aquisitivo": 0,
    "faltas_mes_rescisao": 0,
    "dependentes_ir": 0,
    "decimo_terceiro_pago": 0.0,
    "outros_descontos": 0.0,
    "saldo_fgts": 0.0,
    "divisor": 220,
    "adicional_he_1": 50.0,
    "adicional_he_2": 100.0,
    "adicional_noturno": 20.0,
    "hora_noturna_reduzida": True,
    "adicional_todo_contrato": True,
    "adicional_inicio": None,
    "adicional_fim": None,
    "considerar_prescricao": True,
    "atualizar": True,
    "juros_pre_judiciais": True,
    "dsr_nos_reflexos": DsrNosReflexos.OJ_394_ATUAL,
    "informar_base_insalubridade": False,
    "base_insalubridade": 0.0,
    # liquidação
    "liq_rescisorias": False,
    "liq_verbas_rescisorias": list(VerbaRescisoria),
    "liq_pedidos": True,
    "considerar_salario_pago": True,
    "simples_nacional": False,
    "aliquota_rat": 2.0,
    "aliquota_terceiros": 5.8,
    "honorarios_percentual": 10.0,
    "sucumbencia_reclamante": False,
    "honorarios_reclamante_base": 0.0,
    "honorarios_reclamante_percentual": 10.0,
    "justica_gratuita": True,
    "custas_fixadas": False,
    "custas_valor": 0.0,
    "informar_prazo_citacao": False,
    "fim_prazo_citacao": None,
    "honorarios_periciais": 0.0,
    "periciais_pelo_reclamante": False,
    "pensao_percentual": 0.0,
    "honorarios_contratuais_percentual": 0.0,
}
COLUNAS_OUTRA = {
    "descricao": "Descrição",
    "competencia": "Competência (mês)",
    "valor": "Valor (R$)",
    "natureza": "Natureza",
    "fgts": "Incide FGTS",
    "dano_moral": "Danos morais",
}
LINHA_OUTRA_VAZIA = {
    COLUNAS_OUTRA["descricao"]: "",
    COLUNAS_OUTRA["competencia"]: None,
    COLUNAS_OUTRA["valor"]: 0.0,
    COLUNAS_OUTRA["natureza"]: NaturezaPagamento.INDENIZATORIA.rotulo,
    COLUNAS_OUTRA["fgts"]: False,
    COLUNAS_OUTRA["dano_moral"]: False,
}
COLUNAS_PAGAMENTO = {
    "descricao": "Descrição",
    "data": "Data",
    "valor": "Valor (R$)",
    "deposito": "Depósito judicial (saldo atual)",
}
LINHA_PAGAMENTO_VAZIA = {
    COLUNAS_PAGAMENTO["descricao"]: "",
    COLUNAS_PAGAMENTO["data"]: None,
    COLUNAS_PAGAMENTO["valor"]: 0.0,
    COLUNAS_PAGAMENTO["deposito"]: False,
}
COLUNAS_PAGO = {
    "descricao": "Descrição",
    "competencia": "Competência (mês)",
    "valor": "Valor (R$)",
    "natureza": "Natureza",
    "fgts": "FGTS já depositado",
}
NATUREZAS = {n.rotulo: n for n in NaturezaPagamento}
LINHA_PAGO_VAZIA = {
    COLUNAS_PAGO["descricao"]: "",
    COLUNAS_PAGO["competencia"]: None,
    COLUNAS_PAGO["valor"]: 0.0,
    COLUNAS_PAGO["natureza"]: NaturezaPagamento.SALARIAL.rotulo,
    COLUNAS_PAGO["fgts"]: False,
}
COLUNAS_PERIODO = {
    "inicio": "Início (vazio = admissão)",
    "fim": "Fim (vazio = desligamento)",
    "he_1": "HE 1º adicional (h/mês)",
    "he_2": "HE 2º adicional (h/mês)",
    "noturnas": "Horas noturnas (h/mês)",
}
LINHA_PERIODO_VAZIA = {
    COLUNAS_PERIODO["inicio"]: None,
    COLUNAS_PERIODO["fim"]: None,
    COLUNAS_PERIODO["he_1"]: 0.0,
    COLUNAS_PERIODO["he_2"]: 0.0,
    COLUNAS_PERIODO["noturnas"]: 0.0,
}


def dec(valor) -> Decimal:
    return arredondar(Decimal(str(valor or 0)))


def iniciar_estado():
    # Reatribuir mantém o valor de campos que não aparecem nesta execução (ex.: os do outro
    # modo de cálculo); sem isso o Streamlit descarta o estado de widgets não desenhados.
    for chave in CAMPOS:
        if chave in st.session_state:
            st.session_state[chave] = st.session_state[chave]
    for chave, padrao in PADROES.items():
        st.session_state.setdefault(chave, padrao)
    st.session_state.setdefault("data_ajuizamento", date.today())
    st.session_state.setdefault("data_atualizacao", date.today())
    st.session_state.setdefault("data_interrupcao", None)
    for tabela in TABELAS:
        st.session_state.setdefault(f"{tabela}_versao", 0)
        st.session_state.setdefault(f"{tabela}_inicial", [])
        st.session_state.setdefault(f"{tabela}_atual", [])


def _tabela(nome: str, vazia: list[dict], column_config: dict) -> list[dict]:
    """Tabela editável cujo conteúdo pode ser recarregado ao abrir um caso."""
    linhas = st.data_editor(
        st.session_state[f"{nome}_inicial"] or vazia,
        num_rows="dynamic",
        key=f"{nome}_{st.session_state[f'{nome}_versao']}",
        column_config=column_config,
        width="stretch",
    )
    st.session_state[f"{nome}_atual"] = linhas
    return linhas


# ---------------------------------------------------------------- seções comuns


def secao_contrato(modo_rescisao: bool):
    with st.container(border=True):
        st.subheader("1. Contrato")
        c1, c2, c3 = st.columns(3)
        c1.date_input("Data de admissão", format="DD/MM/YYYY", key="admissao", min_value=DATA_MINIMA)
        c2.date_input(
            "Último dia trabalhado",
            format="DD/MM/YYYY",
            key="desligamento",
            min_value=DATA_MINIMA,
            help="Se o aviso foi trabalhado, é o último dia do aviso. Se foi indenizado, é o dia do afastamento.",
        )
        c3.number_input("Salário mensal (R$)", min_value=0.0, step=100.0, key="salario")
        if modo_rescisao:
            c1.number_input(
                "Média mensal de variáveis (R$)",
                min_value=0.0,
                step=50.0,
                key="media_variaveis",
                help="Horas extras, comissões, adicionais habituais etc. Integra aviso, 13º e férias.",
            )
        ajuda = (
            "Usado apenas para estimar o saldo do FGTS quando o extrato não for informado."
            if modo_rescisao
            else "O valor-hora de cada mês usa o salário da época."
        )
        usar = c2.checkbox("Houve alteração de salário durante o contrato?", key="usar_historico", help=ajuda)
        if usar:
            _tabela(
                "historico",
                [{"A partir de": None, "Salário (R$)": 0.0}],
                {
                    "A partir de": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
                    "Salário (R$)": st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f", required=True),
                },
            )


def historico_salarial() -> list[AlteracaoSalarial]:
    if not st.session_state.get("usar_historico"):
        return []
    return [
        AlteracaoSalarial(linha["A partir de"], dec(linha["Salário (R$)"]))
        for linha in st.session_state["historico_atual"]
        if linha.get("A partir de") and linha.get("Salário (R$)")
    ]


def secao_extincao():
    with st.container(border=True):
        st.subheader("2. Como o contrato terminou")
        c1, c2 = st.columns(2)
        modalidade = c1.selectbox(
            "Modalidade de extinção", list(Modalidade), format_func=lambda m: m.rotulo, key="modalidade"
        )
        opcoes = list(AVISOS_PERMITIDOS[modalidade])
        if st.session_state.get("aviso") not in opcoes:
            st.session_state["aviso"] = opcoes[0]
        c2.selectbox("Aviso prévio", opcoes, format_func=lambda a: a.rotulo, key="aviso", disabled=len(opcoes) == 1)


def pendencias_contrato() -> list[str]:
    estado = st.session_state
    faltando = []
    if not estado.get("admissao"):
        faltando.append("data de admissão")
    if not estado.get("desligamento"):
        faltando.append("último dia trabalhado")
    if not estado.get("salario"):
        faltando.append("salário mensal")
    return faltando


# ---------------------------------------------------------------- rescisão


def secoes_rescisao():
    secao_ferias_e_13("3. Férias, faltas e 13º")
    secao_fgts_e_multas("4. FGTS, multas e descontos", com_dependentes=True)
    secao_ajuizamento_e_atualizacao(5, com_prescricao=False)


def secao_ferias_e_13(titulo: str):
    with st.container(border=True):
        st.subheader(titulo)
        c1, c2, c3, c4 = st.columns(4)
        c1.number_input(
            "Períodos de férias vencidas não gozadas",
            min_value=0,
            step=1,
            key="ferias_vencidas",
            help="Quantos períodos aquisitivos de 12 meses já completos o empregado não tirou. "
            "O sistema identifica sozinho quais devem ser pagos em dobro.",
        )
        c2.number_input(
            "Faltas injustificadas no período aquisitivo atual",
            min_value=0,
            step=1,
            key="faltas_periodo_aquisitivo",
            help="Reduz os dias de férias proporcionais (art. 130 da CLT).",
        )
        c3.number_input("Faltas injustificadas no mês do desligamento", min_value=0, step=1, key="faltas_mes_rescisao")
        c4.number_input(
            "13º já pago no ano (R$)",
            min_value=0.0,
            step=100.0,
            key="decimo_terceiro_pago",
            help="Adiantamento (1ª parcela) já recebido, que será descontado.",
        )


def secao_fgts_e_multas(titulo: str, com_dependentes: bool):
    with st.container(border=True):
        st.subheader(titulo)
        c1, c2, c3 = st.columns(3)
        if c1.checkbox("Tenho o saldo do FGTS (extrato)", key="informar_saldo_fgts"):
            c1.number_input(
                "Saldo para fins rescisórios (R$)",
                min_value=0.0,
                step=100.0,
                key="saldo_fgts",
                help="Valor do extrato do FGTS. Sem ele, o sistema estima o saldo pelo salário.",
            )
        c2.checkbox(
            "Verbas pagas fora do prazo (multa do art. 477)",
            key="pagamento_em_atraso",
            help="Prazo de 10 dias a contar do término do contrato (art. 477, § 6º, CLT).",
        )
        c2.checkbox(
            "Aplicar multa do art. 467",
            key="multa_467",
            help="50% sobre as verbas rescisórias incontroversas não pagas na primeira audiência.",
        )
        if com_dependentes:
            c3.number_input("Dependentes para IR", min_value=0, step=1, key="dependentes_ir")
        c3.number_input("Outros descontos (R$)", min_value=0.0, step=50.0, key="outros_descontos")


def dados_rescisao() -> DadosRescisao:
    e = st.session_state
    return DadosRescisao(
        admissao=e["admissao"],
        desligamento=e["desligamento"],
        modalidade=e["modalidade"],
        aviso=e["aviso"],
        salario=dec(e["salario"]),
        media_variaveis=dec(e["media_variaveis"]),
        historico_salarial=historico_salarial(),
        ferias_vencidas=int(e["ferias_vencidas"]),
        faltas_periodo_aquisitivo=int(e["faltas_periodo_aquisitivo"]),
        faltas_mes_rescisao=int(e["faltas_mes_rescisao"]),
        dependentes_ir=int(e["dependentes_ir"]),
        decimo_terceiro_pago=dec(e["decimo_terceiro_pago"]),
        saldo_fgts=dec(e["saldo_fgts"]) if e.get("informar_saldo_fgts") else None,
        pagamento_em_atraso=bool(e.get("pagamento_em_atraso")),
        multa_467=bool(e.get("multa_467")),
        outros_descontos=dec(e["outros_descontos"]),
    )


# ---------------------------------------------------------------- horas extras e adicionais


def secoes_pedidos():
    secao_jornada("3. Jornada: horas extras e horas noturnas não pagas")
    secao_adicional("4. Insalubridade ou periculosidade")
    secao_ajuizamento_e_atualizacao(5, com_prescricao=True)


def secao_jornada(titulo: str):
    with st.container(border=True):
        st.subheader(titulo)
        st.caption(
            "Informe a média mensal de horas devidas e não pagas em cada período. "
            "Ex.: 2 horas extras por dia × 22 dias = 44 h/mês. "
            "Deixe Início e Fim em branco para usar o contrato inteiro."
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.selectbox("Divisor", list(DIVISORES), format_func=DIVISORES.get, key="divisor")
        c2.number_input("1º adicional de HE (%)", min_value=0.0, step=5.0, key="adicional_he_1")
        c3.number_input(
            "2º adicional de HE (%)",
            min_value=0.0,
            step=5.0,
            key="adicional_he_2",
            help="Em regra 100%: trabalho em domingos e feriados sem folga compensatória (Súmula 146 do TST).",
        )
        c4.number_input("Adicional noturno (%)", min_value=0.0, step=5.0, key="adicional_noturno")
        c1, c2 = st.columns(2)
        c1.checkbox(
            "Converter horas noturnas em hora reduzida (52min30s)",
            key="hora_noturna_reduzida",
            help="Art. 73, § 1º, CLT: cada 52min30s de trabalho noturno contam como 1 hora.",
        )
        c2.selectbox(
            "DSR majorado nos reflexos (13º, férias e aviso)",
            list(DsrNosReflexos),
            format_func=lambda o: o.rotulo,
            key="dsr_nos_reflexos",
            help="OJ 394 da SDI-1 do TST. Use outra opção só se a sentença fixou critério diferente.",
        )
        _tabela(
            "periodos",
            [dict(LINHA_PERIODO_VAZIA)],
            {
                COLUNAS_PERIODO["inicio"]: st.column_config.DateColumn(format="DD/MM/YYYY"),
                COLUNAS_PERIODO["fim"]: st.column_config.DateColumn(format="DD/MM/YYYY"),
                COLUNAS_PERIODO["he_1"]: st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                COLUNAS_PERIODO["he_2"]: st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                COLUNAS_PERIODO["noturnas"]: st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
            },
        )


def secao_adicional(titulo: str):
    with st.container(border=True):
        st.subheader(titulo)
        c1, c2 = st.columns(2)
        tipo = c1.selectbox(
            "Adicional",
            list(AdicionalOcupacional),
            format_func=lambda a: a.rotulo,
            key="adicional_ocupacional",
            help="Os dois adicionais não se acumulam (art. 193, § 2º, CLT).",
        )
        if tipo != AdicionalOcupacional.NENHUM:
            c2.checkbox(
                "Já era pago (só integra a base das horas extras)",
                key="adicional_ja_pago",
                help="Marque se o empregado já recebia o adicional e o pedido é apenas a integração no valor-hora.",
            )
            if not c2.checkbox("Durante todo o contrato", key="adicional_todo_contrato"):
                c3, c4 = st.columns(2)
                c3.date_input(
                    "Adicional devido desde", format="DD/MM/YYYY", key="adicional_inicio", min_value=DATA_MINIMA
                )
                c4.date_input("Adicional devido até", format="DD/MM/YYYY", key="adicional_fim", min_value=DATA_MINIMA)
            if tipo.insalubridade and c1.checkbox(
                "Base diferente do salário mínimo",
                key="informar_base_insalubridade",
                help="Base fixada na sentença ou em norma coletiva (ex.: piso da categoria).",
            ):
                c1.number_input(
                    "Base mensal da insalubridade (R$)", min_value=0.0, step=100.0, key="base_insalubridade"
                )


def secao_ajuizamento_e_atualizacao(numero: int, com_prescricao: bool, liquidacao: bool = False):
    titulo = "Ajuizamento, prescrição e atualização" if com_prescricao else "Ajuizamento e atualização"
    with st.container(border=True):
        st.subheader(f"{numero}. {titulo}")
        c1, c2, c3 = st.columns(3)
        c1.date_input(
            "Data do ajuizamento" if liquidacao else "Data do ajuizamento (ou prevista)",
            format="DD/MM/YYYY",
            key="data_ajuizamento",
            min_value=DATA_MINIMA,
            help="Início da fase judicial (SELIC até 29/08/2024)."
            if liquidacao
            else "Para a petição inicial, use a data prevista de distribuição: todo o período será "
            "tratado como fase pré-judicial.",
        )
        if com_prescricao and c1.checkbox(
            "A sentença aplicou a prescrição quinquenal" if liquidacao else "Aplicar prescrição quinquenal",
            key="considerar_prescricao",
            help="Exclui as parcelas anteriores a 5 anos da data do ajuizamento (art. 7º, XXIX, CF).",
        ):
            if c1.checkbox(
                "Prescrição interrompida (ação anterior ou protesto)",
                key="prescricao_interrompida",
                help="A ação anterior arquivada (Súmula 268 do TST) ou o protesto judicial (OJ 392 da SDI-1) "
                "interrompem a prescrição: os 5 anos passam a ser contados da data do ajuizamento deles.",
            ):
                c1.date_input(
                    "Ajuizamento da ação anterior ou do protesto",
                    format="DD/MM/YYYY",
                    key="data_interrupcao",
                    min_value=DATA_MINIMA,
                )
        if liquidacao:
            c2.date_input(
                "Data da liquidação (atualizar até)",
                format="DD/MM/YYYY",
                key="data_atualizacao",
                min_value=DATA_MINIMA,
                help="Correção e juros pela ADC 58 do STF e pela Lei nº 14.905/2024, conforme a SDI-1 do TST.",
            )
        if liquidacao or c2.checkbox(
            "Atualizar valores (correção e juros)",
            key="atualizar",
            help="ADC 58 do STF e Lei nº 14.905/2024, conforme a SDI-1 do TST.",
        ):
            if not liquidacao:
                c2.date_input("Atualizar até", format="DD/MM/YYYY", key="data_atualizacao", min_value=DATA_MINIMA)
            c3.checkbox(
                "Juros antes do ajuizamento",
                key="juros_pre_judiciais",
                help="Fase pré-judicial: TR (art. 39, caput, Lei nº 8.177/1991) até 29/08/2024 e taxa legal "
                "depois. Desmarque se o juízo aplica juros só a partir do ajuizamento (art. 883 da CLT).",
            )


def parametros_atualizacao() -> ParametrosAtualizacao | None:
    e = st.session_state
    if not e.get("atualizar") or not e.get("data_atualizacao"):
        return None
    return ParametrosAtualizacao(
        data_atualizacao=e["data_atualizacao"],
        data_ajuizamento=e.get("data_ajuizamento"),
        juros_pre_judiciais=bool(e.get("juros_pre_judiciais")),
    )


def periodos_jornada(admissao: date, desligamento: date) -> list[PeriodoJornada]:
    periodos = []
    for linha in st.session_state["periodos_atual"]:
        horas = [dec(linha.get(COLUNAS_PERIODO[c])) for c in ("he_1", "he_2", "noturnas")]
        if not any(horas):
            continue
        periodos.append(
            PeriodoJornada(
                inicio=linha.get(COLUNAS_PERIODO["inicio"]) or admissao,
                fim=linha.get(COLUNAS_PERIODO["fim"]) or desligamento,
                horas_extras_1=horas[0],
                horas_extras_2=horas[1],
                horas_noturnas=horas[2],
            )
        )
    return periodos


def dados_pedidos() -> DadosPedidos:
    e = st.session_state
    tipo = e.get("adicional_ocupacional", AdicionalOcupacional.NENHUM)
    todo_contrato = e.get("adicional_todo_contrato", True)
    return DadosPedidos(
        admissao=e["admissao"],
        desligamento=e["desligamento"],
        modalidade=e["modalidade"],
        aviso=e["aviso"],
        salario=dec(e["salario"]),
        historico_salarial=historico_salarial(),
        data_ajuizamento=e.get("data_ajuizamento") if e.get("considerar_prescricao") else None,
        data_interrupcao_prescricao=(
            e.get("data_interrupcao") if e.get("considerar_prescricao") and e.get("prescricao_interrompida") else None
        ),
        divisor=int(e["divisor"]),
        adicional_he_1=dec(e["adicional_he_1"]) / 100,
        adicional_he_2=dec(e["adicional_he_2"]) / 100,
        adicional_noturno=dec(e["adicional_noturno"]) / 100,
        hora_noturna_reduzida=bool(e.get("hora_noturna_reduzida")),
        periodos=periodos_jornada(e["admissao"], e["desligamento"]),
        adicional_ocupacional=tipo,
        adicional_inicio=None if todo_contrato else e.get("adicional_inicio"),
        adicional_fim=None if todo_contrato else e.get("adicional_fim"),
        adicional_ja_pago=bool(e.get("adicional_ja_pago")) and tipo != AdicionalOcupacional.NENHUM,
        base_insalubridade=(
            dec(e["base_insalubridade"])
            if tipo.insalubridade and e.get("informar_base_insalubridade") and e.get("base_insalubridade")
            else None
        ),
        dsr_nos_reflexos=e.get("dsr_nos_reflexos", DsrNosReflexos.OJ_394_ATUAL),
    )


# ---------------------------------------------------------------- liquidação de sentença


def secoes_liquidacao():
    e = st.session_state
    with st.container(border=True):
        st.subheader("3. Verbas deferidas na sentença")
        c1, c2 = st.columns(2)
        c1.checkbox("Verbas rescisórias", key="liq_rescisorias")
        c2.checkbox("Horas extras, adicional noturno, insalubridade ou periculosidade", key="liq_pedidos")
        if e.get("liq_rescisorias"):
            c1.multiselect(
                "Quais verbas rescisórias?",
                list(VerbaRescisoria),
                format_func=lambda v: v.rotulo,
                key="liq_verbas_rescisorias",
            )
    if e.get("liq_rescisorias"):
        secao_ferias_e_13("Verbas rescisórias: férias, faltas e 13º")
        secao_fgts_e_multas("Verbas rescisórias: FGTS, multas e descontos", com_dependentes=False)
    if e.get("liq_pedidos"):
        secao_jornada("Jornada: horas extras e horas noturnas não pagas")
        secao_adicional("Insalubridade ou periculosidade")
    with st.container(border=True):
        st.subheader("Outras verbas deferidas")
        st.caption(
            "Diferenças salariais, multa convencional, danos morais e outras verbas com valor definido. "
            "Danos morais são atualizados desde o ajuizamento, sem INSS e IR. Deixe em branco se não houver."
        )
        _tabela(
            "outras",
            [dict(LINHA_OUTRA_VAZIA)],
            {
                COLUNAS_OUTRA["descricao"]: st.column_config.TextColumn(),
                COLUNAS_OUTRA["competencia"]: st.column_config.DateColumn(format="MM/YYYY"),
                COLUNAS_OUTRA["valor"]: st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f"),
                COLUNAS_OUTRA["natureza"]: st.column_config.SelectboxColumn(options=list(NATUREZAS)),
                COLUNAS_OUTRA["fgts"]: st.column_config.CheckboxColumn(),
                COLUNAS_OUTRA["dano_moral"]: st.column_config.CheckboxColumn(),
            },
        )

    with st.container(border=True):
        st.subheader("4. Valores já pagos (dedução)")
        st.caption(
            "Valores pagos sob o mesmo título, a deduzir pelo critério global (OJ 415 da SDI-1 do TST). "
            "Deixe em branco se não houver."
        )
        _tabela(
            "pagos",
            [dict(LINHA_PAGO_VAZIA)],
            {
                COLUNAS_PAGO["descricao"]: st.column_config.TextColumn(),
                COLUNAS_PAGO["competencia"]: st.column_config.DateColumn(format="MM/YYYY"),
                COLUNAS_PAGO["valor"]: st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f"),
                COLUNAS_PAGO["natureza"]: st.column_config.SelectboxColumn(options=list(NATUREZAS)),
                COLUNAS_PAGO["fgts"]: st.column_config.CheckboxColumn(
                    help="Marque se o FGTS desse valor já foi depositado: o sistema deduz também 8% e a multa."
                ),
            },
        )

    secao_ajuizamento_e_atualizacao(5, com_prescricao=bool(e.get("liq_pedidos")), liquidacao=True)
    with st.container(border=True):
        st.subheader("Pagamentos e depósitos no processo")
        st.caption(
            "Valores já pagos no processo (incontroverso, parcelas) são atualizados até a liquidação e abatidos do "
            "total. Para depósito judicial ou recursal, informe o saldo atual (o banco já o atualizou)."
        )
        _tabela(
            "pagamentos",
            [dict(LINHA_PAGAMENTO_VAZIA)],
            {
                COLUNAS_PAGAMENTO["descricao"]: st.column_config.TextColumn(),
                COLUNAS_PAGAMENTO["data"]: st.column_config.DateColumn(format="DD/MM/YYYY"),
                COLUNAS_PAGAMENTO["valor"]: st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f"),
                COLUNAS_PAGAMENTO["deposito"]: st.column_config.CheckboxColumn(),
            },
        )

    with st.container(border=True):
        st.subheader("6. INSS, imposto de renda, honorários e custas")
        c1, c2, c3 = st.columns(3)
        c1.checkbox(
            "Somar o salário já pago (faixas e teto do INSS)",
            key="considerar_salario_pago",
            help="INSS devido = INSS(salário pago + verbas deferidas) − INSS(salário pago), em cada competência.",
        )
        if not c1.checkbox("Empresa do Simples Nacional", key="simples_nacional", help="Sem cota patronal."):
            c1.number_input("RAT ajustado pelo FAP (%)", min_value=0.0, step=0.5, format="%.4f", key="aliquota_rat")
            c1.number_input("Terceiros (%)", min_value=0.0, step=0.1, format="%.2f", key="aliquota_terceiros")
        c2.number_input(
            "Honorários de sucumbência devidos pela reclamada (%)",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            key="honorarios_percentual",
            help="Art. 791-A da CLT (5% a 15%), sobre o valor bruto da liquidação (OJ 348 da SDI-1).",
        )
        if c2.checkbox("Houve sucumbência do reclamante", key="sucumbencia_reclamante"):
            c2.number_input(
                "Valor dos pedidos rejeitados (R$)", min_value=0.0, step=1000.0, key="honorarios_reclamante_base"
            )
            c2.number_input(
                "Honorários devidos pelo reclamante (%)",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                key="honorarios_reclamante_percentual",
            )
            c2.checkbox(
                "Reclamante com justiça gratuita",
                key="justica_gratuita",
                help="A exigibilidade fica suspensa (art. 791-A, § 4º, CLT; ADI 5766 do STF).",
            )
        if c1.checkbox(
            "Prazo da citação para pagamento já venceu",
            key="informar_prazo_citacao",
            help="A multa de mora sobre o INSS (0,33% ao dia, até 20%) corre do dia seguinte (Súmula 368, V, do TST).",
        ):
            c1.date_input("Último dia do prazo", format="DD/MM/YYYY", key="fim_prazo_citacao", min_value=DATA_MINIMA)
        c2.number_input(
            "Pensão alimentícia (% do crédito)",
            min_value=0.0,
            max_value=100.0,
            step=5.0,
            key="pensao_percentual",
            help="Sobre as verbas atualizadas menos o INSS do reclamante. Também é deduzida da base do IR.",
        )
        c2.number_input(
            "Honorários contratuais (%), só para o IR",
            min_value=0.0,
            max_value=100.0,
            step=5.0,
            key="honorarios_contratuais_percentual",
            help="Honorários pagos pelo reclamante ao seu advogado reduzem a base do IR (art. 12-A, § 2º, Lei nº "
            "7.713/1988). Não são descontados no cálculo.",
        )
        if c3.checkbox(
            "Custas fixadas na sentença",
            key="custas_fixadas",
            help="Sem marcar, o sistema calcula 2% sobre a condenação (art. 789, CLT).",
        ):
            c3.number_input("Valor das custas (R$)", min_value=0.0, step=10.0, key="custas_valor")
        c3.number_input("Honorários periciais (R$)", min_value=0.0, step=100.0, key="honorarios_periciais")
        c3.checkbox(
            "Perícia a cargo do reclamante",
            key="periciais_pelo_reclamante",
            help="Com justiça gratuita, a União paga (art. 790-B, § 4º, CLT; ADI 5766 do STF).",
        )


def pendencias_liquidacao() -> list[str]:
    e = st.session_state
    faltando = []
    if not e.get("data_ajuizamento"):
        faltando.append("data do ajuizamento")
    if not e.get("data_atualizacao"):
        faltando.append("data da liquidação")
    if not e.get("liq_rescisorias") and not e.get("liq_pedidos") and not outras_verbas():
        faltando.append("verbas deferidas")
    return faltando


def _percentual(valor) -> Decimal:
    return Decimal(str(valor or 0)) / 100


def valores_pagos() -> list[ValorPago]:
    pagos = []
    for linha in st.session_state["pagos_atual"]:
        valor = dec(linha.get(COLUNAS_PAGO["valor"]))
        competencia = linha.get(COLUNAS_PAGO["competencia"])
        if not valor or not competencia:
            continue
        pagos.append(
            ValorPago(
                descricao=linha.get(COLUNAS_PAGO["descricao"]) or "",
                competencia=competencia,
                valor=valor,
                natureza=NATUREZAS.get(linha.get(COLUNAS_PAGO["natureza"]), NaturezaPagamento.SALARIAL),
                abater_fgts=bool(linha.get(COLUNAS_PAGO["fgts"])),
            )
        )
    return pagos


def outras_verbas() -> list[OutraVerba]:
    verbas = []
    for linha in st.session_state.get("outras_atual", []):
        valor = dec(linha.get(COLUNAS_OUTRA["valor"]))
        if not valor:
            continue
        verbas.append(
            OutraVerba(
                descricao=linha.get(COLUNAS_OUTRA["descricao"]) or "",
                competencia=linha.get(COLUNAS_OUTRA["competencia"]),
                valor=valor,
                natureza=NATUREZAS.get(linha.get(COLUNAS_OUTRA["natureza"]), NaturezaPagamento.INDENIZATORIA),
                fgts=bool(linha.get(COLUNAS_OUTRA["fgts"])),
                dano_moral=bool(linha.get(COLUNAS_OUTRA["dano_moral"])),
            )
        )
    return verbas


def pagamentos() -> list[Pagamento]:
    lista = []
    for linha in st.session_state.get("pagamentos_atual", []):
        valor = dec(linha.get(COLUNAS_PAGAMENTO["valor"]))
        data = linha.get(COLUNAS_PAGAMENTO["data"])
        if not valor or not data:
            continue
        lista.append(
            Pagamento(
                descricao=linha.get(COLUNAS_PAGAMENTO["descricao"]) or "",
                data=data,
                valor=valor,
                deposito_judicial=bool(linha.get(COLUNAS_PAGAMENTO["deposito"])),
            )
        )
    return lista


def dados_liquidacao() -> DadosLiquidacao:
    e = st.session_state
    sucumbencia = bool(e.get("sucumbencia_reclamante"))
    return DadosLiquidacao(
        data_ajuizamento=e["data_ajuizamento"],
        data_liquidacao=e["data_atualizacao"],
        rescisao=dados_rescisao() if e.get("liq_rescisorias") else None,
        verbas_rescisorias=frozenset(e.get("liq_verbas_rescisorias") or ()),
        pedidos=dados_pedidos() if e.get("liq_pedidos") else None,
        valores_pagos=valores_pagos(),
        juros_pre_judiciais=bool(e.get("juros_pre_judiciais")),
        considerar_salario_pago=bool(e.get("considerar_salario_pago")),
        simples_nacional=bool(e.get("simples_nacional")),
        aliquota_rat=_percentual(e.get("aliquota_rat")),
        aliquota_terceiros=_percentual(e.get("aliquota_terceiros")),
        honorarios_percentual=_percentual(e.get("honorarios_percentual")),
        honorarios_reclamante_base=dec(e.get("honorarios_reclamante_base")) if sucumbencia else Decimal(0),
        honorarios_reclamante_percentual=_percentual(e.get("honorarios_reclamante_percentual"))
        if sucumbencia
        else Decimal(0),
        justica_gratuita=bool(e.get("justica_gratuita")),
        custas_informadas=dec(e.get("custas_valor")) if e.get("custas_fixadas") else None,
        outras_verbas=outras_verbas(),
        pagamentos=pagamentos(),
        fim_prazo_citacao=e.get("fim_prazo_citacao") if e.get("informar_prazo_citacao") else None,
        honorarios_periciais=dec(e.get("honorarios_periciais")),
        periciais_pelo_reclamante=bool(e.get("periciais_pelo_reclamante")),
        pensao_percentual=_percentual(e.get("pensao_percentual")),
        honorarios_contratuais_percentual=_percentual(e.get("honorarios_contratuais_percentual")),
        contrato=dados_rescisao(),
    )
