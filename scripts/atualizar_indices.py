#!/usr/bin/env python3
"""Baixa do Banco Central (SGS) os índices mensais da atualização trabalhista.

Grava `tolaris/tabelas/indices.json`. Roda todo mês pelo GitHub Actions
(.github/workflows/indices.yml) e pode ser executado à mão: `python scripts/atualizar_indices.py`.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "tolaris" / "tabelas" / "indices.json"
INICIO = 2015
SERIES_MENSAIS = {
    "ipca_e": (10764, "IPCA-E (IBGE), variação mensal %"),
    "ipca": (433, "IPCA (IBGE), variação mensal %"),
    "selic": (4390, "Taxa SELIC acumulada no mês, % a.m."),
    "taxa_legal": (29543, "Taxa legal (art. 406 do Código Civil; Resolução CMN 5.171/2024), % a.m."),
}
TR_DIARIA = (226, "TR do período iniciado no 1º dia de cada mês, % (série diária 226)")
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={inicio}&dataFinal={fim}"


def baixar(codigo: int) -> list[dict]:
    """Baixa em blocos de 5 anos (a API limita o período das séries diárias)."""
    registros = []
    hoje = date.today()
    for ano in range(INICIO, hoje.year + 1, 5):
        inicio = f"01/01/{ano}"
        fim = f"31/12/{min(ano + 4, hoje.year)}"
        url = URL.format(codigo=codigo, inicio=inicio, fim=fim)
        for tentativa in range(4):
            try:
                pedido = urllib.request.Request(
                    url, headers={"User-Agent": "tolaris-trabalhista", "Accept": "application/json"}
                )
                with urllib.request.urlopen(pedido, timeout=60) as resposta:
                    registros += json.load(resposta)
                break
            except urllib.error.HTTPError as erro:
                if erro.code == 404:  # o SGS responde 404 quando não há dados no período
                    break
                if tentativa == 3:
                    raise RuntimeError(f"Falha ao baixar a série {codigo} ({inicio} a {fim}): {erro}") from erro
                time.sleep(2 ** (tentativa + 1))
            except Exception as erro:  # noqa: BLE001 - rede instável: tenta de novo
                if tentativa == 3:
                    raise RuntimeError(f"Falha ao baixar a série {codigo} ({inicio} a {fim}): {erro}") from erro
                time.sleep(2 ** (tentativa + 1))
    return registros


def por_mes(registros: list[dict], so_primeiro_dia: bool = False) -> dict[str, str]:
    meses = {}
    for registro in registros:
        dia, mes, ano = registro["data"].split("/")
        if so_primeiro_dia and dia != "01":
            continue
        meses[f"{ano}-{mes}"] = registro["valor"].strip()
    return dict(sorted(meses.items()))


def acumulado(serie: dict[str, str], ano: int, composto: bool = True) -> float:
    valores = [float(v) / 100 for k, v in serie.items() if k.startswith(f"{ano}-")]
    if composto:
        fator = 1.0
        for v in valores:
            fator *= 1 + v
        return (fator - 1) * 100
    return sum(valores) * 100


def main():
    series = {}
    descricoes = {}
    for nome, (codigo, descricao) in SERIES_MENSAIS.items():
        series[nome] = por_mes(baixar(codigo))
        descricoes[nome] = f"SGS {codigo}: {descricao}"
    codigo, descricao = TR_DIARIA
    series["tr"] = por_mes(baixar(codigo), so_primeiro_dia=True)
    descricoes["tr"] = f"SGS {codigo}: {descricao}"

    conteudo = {
        "descricao": "Índices mensais em % para a atualização dos créditos trabalhistas. Fonte: Banco Central (SGS).",
        "atualizado_em": date.today().isoformat(),
        "series_descricao": descricoes,
        "series": series,
    }
    DESTINO.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # Conferência: acumulados anuais para comparar com os números oficiais divulgados
    vazias = [nome for nome, serie in series.items() if not serie]
    if vazias:
        raise SystemExit(f"Séries sem nenhum dado: {', '.join(vazias)}")
    for nome, serie in series.items():
        ultimo = max(serie) if serie else "-"
        composto = nome in ("ipca_e", "ipca", "tr")
        anos = ", ".join(
            f"{ano}: {acumulado(serie, ano, composto):.2f}%" for ano in range(date.today().year - 4, date.today().year)
        )
        print(f"{nome:10} {len(serie):4} meses, último {ultimo} | {anos}")


if __name__ == "__main__":
    main()
