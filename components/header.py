"""Header da aplicação: navbar com brand + tabs + badge de última atualização.

O badge é atualizado por callback conforme a aba ativa, lendo a data dos arquivos
`_meta.json` correspondentes (via data.loader).
"""

from dash import html, dcc
import dash_bootstrap_components as dbc

from components import theme


def header() -> html.Div:
    return html.Div(
        className="app-header",
        children=[
            html.Div(
                className="app-header-top",
                children=[
                    html.Div(
                        className="app-brand",
                        children=[
                            html.Span("PMM-e", className="brand-mark"),
                            html.Span("Análise de Dados", className="brand-tagline"),
                        ],
                    ),
                    html.Div(id="update-badge", className="update-badge"),
                ],
            ),
            dcc.Tabs(
                id="main-tabs",
                value="matriculas",
                className="main-tabs",
                children=[
                    dcc.Tab(
                        label="Matrículas",
                        value="matriculas",
                        className="main-tab",
                        selected_className="main-tab--selected",
                    ),
                    dcc.Tab(
                        label="Logbook",
                        value="logbook",
                        className="main-tab",
                        selected_className="main-tab--selected",
                    ),
                ],
            ),
        ],
    )


def update_badge_content(data_atualizacao: str | None, total_registros: int | None = None):
    """Conteúdo do badge dado o dict _meta.json (ou None se ainda não houver dados)."""
    if not data_atualizacao:
        return [
            html.Span("Última atualização: ", className="badge-label"),
            html.Span("indisponível", className="badge-value badge-value--muted"),
        ]

    pieces = [
        html.Span("Última atualização: ", className="badge-label"),
        html.Span(data_atualizacao, className="badge-value"),
    ]
    if total_registros is not None:
        pieces.append(
            html.Span(
                f"  •  {total_registros:,} registros".replace(",", "."),
                className="badge-meta",
            )
        )
    return pieces
