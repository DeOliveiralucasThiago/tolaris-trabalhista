"""Teste de fumaça da interface: abre o app, preenche o essencial e confere o resultado."""

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "streamlit_app.py")


def test_app_abre_e_pede_campos_essenciais():
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    assert any("preencha" in info.value for info in app.info)


def test_app_calcula_rescisao():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.date_input(key="admissao").set_value(date(2023, 3, 1))
    app.date_input(key="desligamento").set_value(date(2026, 5, 15))
    app.number_input(key="salario").set_value(3000.0)
    app.run()
    assert not app.exception
    assert not app.error
    metricas = {m.label: m.value for m in app.metric}
    assert metricas["Líquido rescisório"] == "R$ 8.008,33"


def test_app_calcula_horas_extras():
    app = AppTest.from_file(APP, default_timeout=30)
    app.session_state["periodos_inicial"] = [
        {
            "Início (vazio = admissão)": None,
            "Fim (vazio = desligamento)": None,
            "HE 1º adicional (h/mês)": 20.0,
            "HE 2º adicional (h/mês)": 0.0,
            "Horas noturnas (h/mês)": 0.0,
        }
    ]
    app.run()
    app.radio(key="modo").set_value("Horas extras e adicionais").run()
    app.date_input(key="admissao").set_value(date(2022, 1, 1))
    app.date_input(key="desligamento").set_value(date(2022, 3, 31))
    app.number_input(key="salario").set_value(2200.0)
    app.checkbox(key="considerar_prescricao").uncheck()
    app.run()
    assert not app.exception
    assert not app.error
    metricas = {m.label: m.value for m in app.metric}
    # 900 + 166,44 + 100 + 133,33 + 300 (tests/test_horas_extras.py) + FGTS 117,32 + multa 46,93
    assert metricas["Total dos pedidos"] == "R$ 1.764,02"


def test_trocar_de_modo_preserva_os_campos():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.radio(key="modo").set_value("Horas extras e adicionais").run()
    app.number_input(key="adicional_he_1").set_value(60.0).run()
    app.radio(key="modo").set_value("Verbas rescisórias").run()
    app.number_input(key="ferias_vencidas").set_value(1).run()
    app.radio(key="modo").set_value("Horas extras e adicionais").run()
    assert app.number_input(key="adicional_he_1").value == 60.0
    app.radio(key="modo").set_value("Verbas rescisórias").run()
    assert app.number_input(key="ferias_vencidas").value == 1


def test_campos_de_data_aceitam_datas_antigas():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.radio(key="modo").set_value("Horas extras e adicionais").run()
    app.checkbox(key="prescricao_interrompida").check().run()
    app.selectbox(key="adicional_ocupacional").set_value(list(app.selectbox(key="adicional_ocupacional").options)[1])
    app.run()
    app.checkbox(key="adicional_todo_contrato").uncheck().run()
    chaves = {d.key for d in app.date_input}
    assert {"admissao", "desligamento", "data_ajuizamento", "data_interrupcao", "adicional_inicio"} <= chaves
    for campo in app.date_input:
        assert campo.proto.min <= "1960-01-01", (campo.key, campo.proto.min)
