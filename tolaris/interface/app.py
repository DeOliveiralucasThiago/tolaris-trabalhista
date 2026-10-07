"""Interface Streamlit: coleta os dados, chama o motor e mostra o resultado.

Nenhuma regra de cálculo fica aqui; tudo vem de `tolaris.motor`.
"""

from datetime import date
from decimal import Decimal

import streamlit as st

from tolaris.dinheiro import arredondar, formatar_brl
from tolaris.motor.caso import caso_de_json, caso_para_json
from tolaris.motor.modelos import (
    AVISOS_PERMITIDOS,
    AlteracaoSalarial,
    DadosRescisao,
    ErroDeEntrada,
    Grupo,
    Modalidade,
    ResultadoRescisao,
)
from tolaris.motor.rescisao import calcular_rescisao
from tolaris.relatorios.excel import gerar_excel
from tolaris.relatorios.pdf import TITULOS_GRUPO, gerar_pdf

DATA_MINIMA = date(2019, 1, 1)
CAMPOS_NUMERICOS = {
    "salario": 0.0,
    "media_variaveis": 0.0,
    "ferias_vencidas": 0,
    "faltas_periodo_aquisitivo": 0,
    "faltas_mes_rescisao": 0,
    "dependentes_ir": 0,
    "decimo_terceiro_pago": 0.0,
    "outros_descontos": 0.0,
    "saldo_fgts": 0.0,
}

CSS = """
<style>
h1, h2, h3, h4 { color: #002B5B; }
div[data-testid="stMetricValue"] { font-size: 1.6rem; }
</style>
"""


def _md(texto: str) -> str:
    """Escapa o cifrão: no Markdown do Streamlit, "R$ ... R$" vira fórmula matemática."""
    return str(texto).replace("$", "\\$")


def _dec(valor) -> Decimal:
    return arredondar(Decimal(str(valor or 0)))


def _iniciar_estado():
    for chave, padrao in CAMPOS_NUMERICOS.items():
        st.session_state.setdefault(chave, padrao)
    st.session_state.setdefault("admissao", None)
    st.session_state.setdefault("desligamento", None)
    st.session_state.setdefault("versao_historico", 0)
    st.session_state.setdefault("historico_inicial", [])


def _abrir_caso():
    arquivo = st.session_state.get("arquivo_caso")
    if arquivo is None:
        return
    try:
        dados = caso_de_json(arquivo.getvalue().decode("utf-8"))
    except (ValueError, KeyError) as erro:
        st.session_state["erro_caso"] = f"Não foi possível abrir o caso: {erro}"
        return
    estado = st.session_state
    estado["erro_caso"] = None
    estado["admissao"] = dados.admissao
    estado["desligamento"] = dados.desligamento
    estado["modalidade"] = dados.modalidade
    estado["aviso"] = dados.aviso
    estado["salario"] = float(dados.salario)
    estado["media_variaveis"] = float(dados.media_variaveis)
    estado["ferias_vencidas"] = dados.ferias_vencidas
    estado["faltas_periodo_aquisitivo"] = dados.faltas_periodo_aquisitivo
    estado["faltas_mes_rescisao"] = dados.faltas_mes_rescisao
    estado["dependentes_ir"] = dados.dependentes_ir
    estado["decimo_terceiro_pago"] = float(dados.decimo_terceiro_pago)
    estado["outros_descontos"] = float(dados.outros_descontos)
    estado["informar_saldo_fgts"] = dados.saldo_fgts is not None
    estado["saldo_fgts"] = float(dados.saldo_fgts or 0)
    estado["pagamento_em_atraso"] = dados.pagamento_em_atraso
    estado["multa_467"] = dados.multa_467
    estado["usar_historico"] = bool(dados.historico_salarial)
    estado["historico_inicial"] = [
        {"A partir de": a.inicio, "Salário (R$)": float(a.salario)} for a in dados.historico_salarial
    ]
    estado["versao_historico"] += 1


def _formulario() -> DadosRescisao | None:
    with st.expander("Abrir um caso salvo"):
        st.file_uploader("Arquivo .json do caso", type="json", key="arquivo_caso", on_change=_abrir_caso)
        if st.session_state.get("erro_caso"):
            st.error(st.session_state["erro_caso"])

    with st.container(border=True):
        st.subheader("1. Contrato")
        c1, c2, c3 = st.columns(3)
        admissao = c1.date_input("Data de admissão", format="DD/MM/YYYY", key="admissao", min_value=date(1980, 1, 1))
        desligamento = c2.date_input(
            "Último dia trabalhado",
            format="DD/MM/YYYY",
            key="desligamento",
            min_value=DATA_MINIMA,
            help="Se o aviso foi trabalhado, é o último dia do aviso. Se foi indenizado, é o dia do afastamento.",
        )
        salario = c3.number_input("Salário mensal (R$)", min_value=0.0, step=100.0, key="salario")
        media = c1.number_input(
            "Média mensal de variáveis (R$)",
            min_value=0.0,
            step=50.0,
            key="media_variaveis",
            help="Horas extras, comissões, adicionais habituais etc. Integra aviso, 13º e férias.",
        )
        usar_historico = c2.checkbox(
            "Houve alteração de salário durante o contrato?",
            key="usar_historico",
            help="Usado apenas para estimar o saldo do FGTS quando o extrato não for informado.",
        )
        historico = []
        if usar_historico:
            tabela = st.data_editor(
                st.session_state["historico_inicial"] or [{"A partir de": None, "Salário (R$)": 0.0}],
                num_rows="dynamic",
                key=f"historico_{st.session_state['versao_historico']}",
                column_config={
                    "A partir de": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
                    "Salário (R$)": st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f", required=True),
                },
            )
            historico = [
                AlteracaoSalarial(linha["A partir de"], _dec(linha["Salário (R$)"]))
                for linha in tabela
                if linha.get("A partir de") and linha.get("Salário (R$)")
            ]

    with st.container(border=True):
        st.subheader("2. Como o contrato terminou")
        c1, c2 = st.columns(2)
        modalidade = c1.selectbox(
            "Modalidade de extinção", list(Modalidade), format_func=lambda m: m.rotulo, key="modalidade"
        )
        opcoes_aviso = list(AVISOS_PERMITIDOS[modalidade])
        if st.session_state.get("aviso") not in opcoes_aviso:
            st.session_state["aviso"] = opcoes_aviso[0]
        aviso = c2.selectbox(
            "Aviso prévio",
            opcoes_aviso,
            format_func=lambda a: a.rotulo,
            key="aviso",
            disabled=len(opcoes_aviso) == 1,
        )

    with st.container(border=True):
        st.subheader("3. Férias, faltas e 13º")
        c1, c2, c3, c4 = st.columns(4)
        ferias_vencidas = c1.number_input(
            "Períodos de férias vencidas não gozadas",
            min_value=0,
            step=1,
            key="ferias_vencidas",
            help="Quantos períodos aquisitivos de 12 meses já completos o empregado não tirou. "
            "O sistema identifica sozinho quais devem ser pagos em dobro.",
        )
        faltas_pa = c2.number_input(
            "Faltas injustificadas no período aquisitivo atual",
            min_value=0,
            step=1,
            key="faltas_periodo_aquisitivo",
            help="Reduz os dias de férias proporcionais (art. 130 da CLT).",
        )
        faltas_mes = c3.number_input(
            "Faltas injustificadas no mês do desligamento", min_value=0, step=1, key="faltas_mes_rescisao"
        )
        decimo_pago = c4.number_input(
            "13º já pago no ano (R$)",
            min_value=0.0,
            step=100.0,
            key="decimo_terceiro_pago",
            help="Adiantamento (1ª parcela) já recebido, que será descontado.",
        )

    with st.container(border=True):
        st.subheader("4. FGTS, multas e descontos")
        c1, c2, c3 = st.columns(3)
        informar_fgts = c1.checkbox("Tenho o saldo do FGTS (extrato)", key="informar_saldo_fgts")
        saldo_fgts = None
        if informar_fgts:
            saldo_fgts = _dec(
                c1.number_input(
                    "Saldo para fins rescisórios (R$)",
                    min_value=0.0,
                    step=100.0,
                    key="saldo_fgts",
                    help="Valor do extrato do FGTS. Sem ele, o sistema estima o saldo pelo salário.",
                )
            )
        atraso = c2.checkbox(
            "Verbas pagas fora do prazo (multa do art. 477)",
            key="pagamento_em_atraso",
            help="Prazo de 10 dias a contar do término do contrato (art. 477, § 6º, CLT).",
        )
        multa_467 = c2.checkbox(
            "Aplicar multa do art. 467",
            key="multa_467",
            help="50% sobre as verbas rescisórias incontroversas não pagas na primeira audiência.",
        )
        dependentes = c3.number_input("Dependentes para IR", min_value=0, step=1, key="dependentes_ir")
        outros = c3.number_input("Outros descontos (R$)", min_value=0.0, step=50.0, key="outros_descontos")

    pendencias = []
    if not admissao:
        pendencias.append("data de admissão")
    if not desligamento:
        pendencias.append("último dia trabalhado")
    if not salario:
        pendencias.append("salário mensal")
    if pendencias:
        st.info(f"Para calcular, preencha: {', '.join(pendencias)}.")
        return None

    return DadosRescisao(
        admissao=admissao,
        desligamento=desligamento,
        modalidade=modalidade,
        aviso=aviso,
        salario=_dec(salario),
        media_variaveis=_dec(media),
        historico_salarial=historico,
        ferias_vencidas=int(ferias_vencidas),
        faltas_periodo_aquisitivo=int(faltas_pa),
        faltas_mes_rescisao=int(faltas_mes),
        dependentes_ir=int(dependentes),
        decimo_terceiro_pago=_dec(decimo_pago),
        saldo_fgts=saldo_fgts,
        pagamento_em_atraso=atraso,
        multa_467=multa_467,
        outros_descontos=_dec(outros),
    )


def _resultado(resultado: ResultadoRescisao):
    st.divider()
    st.header("Resultado")
    c1, c2, c3 = st.columns(3)
    c1.metric("Líquido rescisório", formatar_brl(resultado.liquido))
    c2.metric("FGTS a depositar", formatar_brl(resultado.total_fgts), help="Depósito rescisório + multa")
    c3.metric("Total geral", formatar_brl(resultado.total_geral))

    for alerta in resultado.alertas:
        st.warning(_md(alerta))

    aba_demo, aba_memoria, aba_dados = st.tabs(["Demonstrativo", "Memória de cálculo", "Dados apurados"])
    with aba_demo:
        for grupo in Grupo:
            itens = resultado.do_grupo(grupo)
            if not itens:
                continue
            st.markdown(f"**{TITULOS_GRUPO[grupo]}**")
            st.dataframe(
                [{"Rubrica": i.descricao, "Natureza": i.natureza, "Valor": formatar_brl(i.valor)} for i in itens],
                hide_index=True,
                width="stretch",
            )
        st.markdown(
            _md(
                f"Proventos **{formatar_brl(resultado.total_proventos)}** − Descontos "
                f"**{formatar_brl(resultado.total_descontos)}** = Líquido **{formatar_brl(resultado.liquido)}**"
            )
        )
    with aba_memoria:
        st.caption("Como cada valor foi obtido, com o fundamento legal.")
        for item in resultado.lancamentos:
            with st.expander(_md(f"{item.descricao} — {formatar_brl(item.valor)}")):
                st.markdown(_md(f"**Cálculo:** {item.formula}"))
                st.markdown(_md(f"**Fundamento:** {item.fundamento}"))
    with aba_dados:
        for chave, valor in resultado.resumo.items():
            st.markdown(_md(f"**{chave}:** {valor}"))

    st.subheader("Exportar")
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Memória de cálculo (PDF)",
        data=gerar_pdf(resultado),
        file_name="memoria_rescisao.pdf",
        mime="application/pdf",
        width="stretch",
        type="primary",
    )
    c2.download_button(
        "Planilha (Excel)",
        data=gerar_excel(resultado),
        file_name="rescisao.xlsx",
        width="stretch",
    )
    c3.download_button(
        "Salvar caso (.json)",
        data=caso_para_json(resultado.dados),
        file_name="caso_rescisao.json",
        mime="application/json",
        width="stretch",
        help="Guarde este arquivo para reabrir o cálculo depois. Nada é armazenado no servidor.",
    )


def main():
    st.set_page_config(page_title="Tolaris Trabalhista", page_icon="⚖️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    _iniciar_estado()

    st.title("Tolaris Trabalhista")
    st.write(
        "Cálculo de verbas rescisórias com memória de cálculo explicada. "
        "Preencha as etapas abaixo; o resultado aparece assim que os campos essenciais estiverem completos."
    )
    st.caption(
        "Versão de testes. Os dados digitados não são armazenados no servidor. "
        "Confira o resultado antes de usá-lo em juízo."
    )

    dados = _formulario()
    if dados is None:
        return
    try:
        resultado = calcular_rescisao(dados)
    except ErroDeEntrada as erro:
        for mensagem in erro.mensagens:
            st.error(mensagem)
        return
    _resultado(resultado)
