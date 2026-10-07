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
