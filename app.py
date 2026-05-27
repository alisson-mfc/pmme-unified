"""PMM-e — Dashboard Unificado (Matrículas + Logbook).

Aplicação Dash com duas abas no topo (Matrículas | Logbook). Cada aba carrega
seu layout próprio. O header mostra a data de última atualização correspondente
ao dataset da aba ativa, lido de `_meta.json` no repo pmme-dados.
"""

from __future__ import annotations

import os

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, html
from dotenv import load_dotenv

from components.header import header, update_badge_content
from data.loader import format_data_atualizacao, load_meta
from pages import logbook, matriculas

load_dotenv(override=True)

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    title="PMM-e - Análise de Dados",
    suppress_callback_exceptions=True,
    update_title=None,
)
server = app.server  # expõe pro gunicorn

app.layout = html.Div(
    className="app-root",
    children=[
        header(),
        html.Main(id="page-content", className="page-content"),
    ],
)


# ----------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------
@app.callback(Output("page-content", "children"), Input("main-tabs", "value"))
def render_tab(tab: str):
    if tab == "logbook":
        return logbook.layout()
    return matriculas.layout()


@app.callback(Output("update-badge", "children"), Input("main-tabs", "value"))
def render_update_badge(tab: str):
    dataset = "logbook" if tab == "logbook" else "matriculas"
    meta = load_meta(dataset)
    data_str, total = format_data_atualizacao(meta)
    return update_badge_content(data_str, total)


# ----------------------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
