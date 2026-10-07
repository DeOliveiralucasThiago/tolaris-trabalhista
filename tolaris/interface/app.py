"""Interface Streamlit: coleta os dados, chama o motor e mostra o resultado.

Nenhuma regra de cálculo fica aqui; tudo vem de `tolaris.motor`.
"""

import streamlit as st

from tolaris.datas import formatar_data
from tolaris.dinheiro import formatar_brl
from tolaris.interface import formularios as f
from tolaris.interface.caso import CAMPOS, TABELAS, formulario_de_json, formulario_para_json
from tolaris.motor.atualizacao import ResultadoAtualizacao, atualizar
from tolaris.motor.horas_extras import calcular_pedidos
from tolaris.motor.modelos import ErroDeEntrada, Grupo, ResultadoCalculo, ResultadoPedidos
from tolaris.motor.rescisao import calcular_rescisao
from tolaris.relatorios.excel import gerar_excel
from tolaris.relatorios.mensal import colunas_ativas, formatar
from tolaris.relatorios.pdf import TITULOS_GRUPO, gerar_pdf

MODO_RESCISAO = "Verbas rescisórias"
MODO_PEDIDOS = "Horas extras e adicionais"

CSS = """
<style>
h1, h2, h3, h4 { color: #002B5B; }
div[data-testid="stMetricValue"] { font-size: 1.6rem; }
</style>
"""


def _md(texto: str) -> str:
    """Escapa o cifrão: no Markdown do Streamlit, "R$ ... R$" vira fórmula matemática."""
    return str(texto).replace("$", "\\$")


def _abrir_caso():
    arquivo = st.session_state.get("arquivo_caso")
    if arquivo is None:
        return
    try:
        campos, tabelas = formulario_de_json(arquivo.getvalue().decode("utf-8"))
    except (ValueError, KeyError) as erro:
        st.session_state["erro_caso"] = f"Não foi possível abrir o caso: {erro}"
        return
    st.session_state["erro_caso"] = None
    for chave, valor in campos.items():
        st.session_state[chave] = valor
    for nome, linhas in tabelas.items():
        st.session_state[f"{nome}_inicial"] = linhas
        st.session_state[f"{nome}_atual"] = linhas
        st.session_state[f"{nome}_versao"] += 1


def _caso_atual() -> str:
    estado = st.session_state
    campos = {chave: estado[chave] for chave in CAMPOS if chave in estado}
    tabelas = {nome: estado.get(f"{nome}_atual", []) for nome in TABELAS}
    return formulario_para_json(campos, tabelas)


def _metricas(resultado: ResultadoCalculo, atualizado: ResultadoAtualizacao | None):
    c1, c2, c3, c4 = st.columns(4)
    if isinstance(resultado, ResultadoPedidos):
        c1.metric("Parcelas e reflexos", formatar_brl(resultado.total_proventos))
        c2.metric("FGTS + multa", formatar_brl(resultado.total_fgts))
        c3.metric("Total dos pedidos", formatar_brl(resultado.total_geral))
    else:
        c1.metric("Líquido rescisório", formatar_brl(resultado.liquido))
        c2.metric("FGTS a depositar", formatar_brl(resultado.total_fgts), help="Depósito rescisório + multa")
        c3.metric("Total geral", formatar_brl(resultado.total_geral))
    if atualizado:
        c4.metric(
            "Total atualizado",
            formatar_brl(atualizado.total),
            help=f"Com correção monetária e juros até {formatar_data(atualizado.atualizado_ate)}.",
        )


def _tabela_atualizacao(atualizado: ResultadoAtualizacao):
    linhas = [
        {
            "Rubrica": linha.descricao,
            "Original": formatar_brl(linha.valores.original),
            "Correção": formatar_brl(linha.valores.correcao),
            "SELIC": formatar_brl(linha.valores.selic),
            "Juros": formatar_brl(linha.valores.juros),
            "Atualizado": formatar_brl(linha.valores.total),
        }
        for linha in atualizado.linhas
    ]
    total = atualizado.soma()
    linhas.append(
        {
            "Rubrica": "Total (proventos e FGTS)",
            "Original": formatar_brl(total.original),
            "Correção": formatar_brl(total.correcao),
            "SELIC": formatar_brl(total.selic),
            "Juros": formatar_brl(total.juros),
            "Atualizado": formatar_brl(total.total),
        }
    )
    st.dataframe(linhas, hide_index=True, width="stretch")


def _resultado(resultado: ResultadoCalculo, atualizado: ResultadoAtualizacao | None, nome_arquivo: str):
    st.divider()
    st.header("Resultado")
    _metricas(resultado, atualizado)
    for alerta in resultado.alertas + (atualizado.alertas if atualizado else []):
        st.warning(_md(alerta))

    abas = ["Demonstrativo"]
    if isinstance(resultado, ResultadoPedidos):
        abas.insert(0, "Valor por pedido")
        abas.append("Mês a mês")
    if atualizado:
        abas.append("Atualização")
    abas += ["Memória de cálculo", "Dados apurados"]
    guias = dict(zip(abas, st.tabs(abas), strict=True))

    if "Valor por pedido" in guias:
        with guias["Valor por pedido"]:
            st.caption("Valor de cada pedido com reflexos e FGTS, para a liquidação na inicial (art. 840, § 1º, CLT).")
            atualizados = atualizado.por_pedido() if atualizado else {}
            linhas = []
            for pedido, valor in resultado.por_pedido().items():
                linha = {"Pedido": pedido, "Valor histórico": formatar_brl(valor)}
                if atualizado:
                    linha["Valor atualizado"] = formatar_brl(atualizados[pedido].total)
                linhas.append(linha)
            total = {"Pedido": "Total", "Valor histórico": formatar_brl(resultado.total_geral)}
            if atualizado:
                total["Valor atualizado"] = formatar_brl(atualizado.total)
            st.dataframe(linhas + [total], hide_index=True, width="stretch")
    with guias["Demonstrativo"]:
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
        for rotulo, valor, destaque in resultado.totais():
            texto = f"{rotulo}: {formatar_brl(valor)}"
            st.markdown(_md(f"**{texto}**" if destaque else texto))
    if "Mês a mês" in guias:
        with guias["Mês a mês"]:
            colunas = colunas_ativas(resultado.mensal)
            st.dataframe(
                [{c.titulo: formatar(c, linha) for c in colunas} for linha in resultado.mensal],
                hide_index=True,
                width="stretch",
            )
    if "Atualização" in guias:
        with guias["Atualização"]:
            for linha in atualizado.criterio:
                st.markdown(_md(f"- {linha}"))
            _tabela_atualizacao(atualizado)
            if atualizado.descontos:
                st.markdown(
                    _md(
                        f"Descontos (não atualizados): {formatar_brl(atualizado.descontos)} · "
                        f"**Total atualizado: {formatar_brl(atualizado.total)}**"
                    )
                )
    with guias["Memória de cálculo"]:
        st.caption("Como cada valor foi obtido, com o fundamento legal.")
        for item in resultado.lancamentos:
            with st.expander(_md(f"{item.descricao} — {formatar_brl(item.valor)}")):
                st.markdown(_md(f"**Cálculo:** {item.formula}"))
                st.markdown(_md(f"**Fundamento:** {item.fundamento}"))
    with guias["Dados apurados"]:
        for chave, valor in resultado.resumo.items():
            st.markdown(_md(f"**{chave}:** {valor}"))

    st.subheader("Exportar")
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Memória de cálculo (PDF)",
        data=gerar_pdf(resultado, atualizado),
        file_name=f"memoria_{nome_arquivo}.pdf",
        mime="application/pdf",
        width="stretch",
        type="primary",
    )
    c2.download_button(
        "Planilha (Excel)", data=gerar_excel(resultado, atualizado), file_name=f"{nome_arquivo}.xlsx", width="stretch"
    )
    c3.download_button(
        "Salvar caso (.json)",
        data=_caso_atual(),
        file_name="caso_tolaris.json",
        mime="application/json",
        width="stretch",
        help="Guarde este arquivo para reabrir o cálculo depois. Nada é armazenado no servidor.",
    )


def main():
    st.set_page_config(page_title="Tolaris Trabalhista", page_icon="⚖️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    f.iniciar_estado()

    st.title("Tolaris Trabalhista")
    st.write(
        "Cálculos trabalhistas com memória de cálculo explicada. "
        "Preencha as etapas abaixo; o resultado aparece assim que os campos essenciais estiverem completos."
    )
    st.caption(
        "Versão de testes. Os dados digitados não são armazenados no servidor. "
        "Confira o resultado antes de usá-lo em juízo."
    )

    with st.expander("Abrir um caso salvo"):
        st.file_uploader("Arquivo .json do caso", type="json", key="arquivo_caso", on_change=_abrir_caso)
        if st.session_state.get("erro_caso"):
            st.error(st.session_state["erro_caso"])

    modo = st.radio("O que você quer calcular?", [MODO_RESCISAO, MODO_PEDIDOS], horizontal=True, key="modo")
    rescisao = modo == MODO_RESCISAO

    f.secao_contrato(modo_rescisao=rescisao)
    f.secao_extincao()
    if rescisao:
        f.secoes_rescisao()
    else:
        f.secoes_pedidos()

    pendencias = f.pendencias_contrato()
    if pendencias:
        st.info(f"Para calcular, preencha: {', '.join(pendencias)}.")
        return
    try:
        if rescisao:
            resultado = calcular_rescisao(f.dados_rescisao())
        else:
            resultado = calcular_pedidos(f.dados_pedidos())
    except ErroDeEntrada as erro:
        for mensagem in erro.mensagens:
            st.error(_md(mensagem))
        return
    atualizado = None
    parametros = f.parametros_atualizacao()
    if parametros:
        try:
            dados = resultado.dados
            atualizado = atualizar(resultado, parametros, dados.desligamento.replace(day=1))
        except ErroDeEntrada as erro:
            for mensagem in erro.mensagens:
                st.warning(_md(f"Atualização não realizada: {mensagem}"))
    _resultado(resultado, atualizado, "rescisao" if rescisao else "horas_extras")
