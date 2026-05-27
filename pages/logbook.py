"""Aba Logbook — port 1:1 das 3 sub-abas do index.html do logbook dashboard.

Sub-abas:
  • Visão Geral — KPIs + 8 gráficos
  • Análise Diagnóstica — progressão, heatmap Nível×Dificuldade, dificuldade por curso,
    institucional comparativo, CIDs de alta complexidade
  • Análise Preditiva — Modelagem de Tópicos (Claude), Trajetória de Aprendizado (perfis),
    Modelo Preditivo de Dificuldade (Random Forest), tabelas detalhadas
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

from components import charts, theme
from data import loader, logbook_agg
from data.constants import ESTADOS_SIGLAS, SIGLAS_ESTADOS
from data.geojson import geojson_brasil, geojson_municipios
from data.logbook_agg import DIF_COLORS


# ----------------------------------------------------------------------
# Helpers de layout
# ----------------------------------------------------------------------
def _kpi_card(label: str, value_id: str, color: str | None = None, subtitle: str | None = None) -> html.Div:
    return html.Div(
        className="kpi-mini-card",
        style={"borderLeft": f"4px solid {color or theme.ACCENT}"},
        children=[
            html.Div(label, className="kpi-mini-label"),
            html.Div("—", id=value_id, className="kpi-mini-value"),
            html.Div(subtitle, className="kpi-mini-sub") if subtitle else None,
        ],
    )


def _help_icon(target_id: str, content) -> list:
    """Retorna um span com '?' que mostra tooltip via CSS no hover/focus.

    `content` pode ser string ou componente. É renderizado dentro de um filho
    `.help-content` que é escondido por CSS até o usuário fazer hover/focus.
    O parâmetro `target_id` é mantido só por compatibilidade (não é usado).
    """
    return [
        html.Span(
            tabIndex=0,
            className="help-trigger",
            **{"aria-label": "Mais informações"},
            children=[
                html.Span("?", className="help-icon"),
                html.Span(content, className="help-content", role="tooltip"),
            ],
        ),
    ]


def _chart_card(title: str, graph_id: str) -> html.Div:
    return html.Div(
        className="chart-card",
        children=[
            html.H3(title, className="chart-card-title"),
            dcc.Graph(
                id=graph_id,
                config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"},
            ),
        ],
    )


# ----------------------------------------------------------------------
# Filter bar
# ----------------------------------------------------------------------
def _filter_bar() -> html.Div:
    return html.Div(
        className="filter-bar filter-bar--logbook",
        children=[
            html.Div(
                className="filter-row",
                children=[
                    html.Div(
                        className="filter-control",
                        children=[
                            html.Label("Rede Formadora", htmlFor="log-filtro-rede"),
                            dcc.Dropdown(
                                id="log-filtro-rede",
                                options=[{"label": x, "value": x}
                                         for x in ("Todas", "EBSERH", "PROADI-SUS")],
                                value="Todas",
                                clearable=False,
                            ),
                        ],
                    ),
                    html.Div(
                        className="filter-summary",
                        children=html.Div(id="log-records-summary", className="records-summary"),
                    ),
                    dbc.Button(
                        "Mais Filtros",
                        id="log-toggle-filters",
                        color="primary",
                        outline=True,
                        size="sm",
                        className="ms-auto",
                    ),
                ],
            ),
            dbc.Collapse(
                id="log-filters-collapse",
                is_open=False,
                children=html.Div(
                    className="filter-grid",
                    children=[
                        html.Div(className="filter-control", children=[
                            html.Label("Data Início", htmlFor="log-data-inicio"),
                            dcc.DatePickerSingle(
                                id="log-data-inicio",
                                display_format="DD/MM/YYYY",
                                placeholder="dd/mm/aaaa",
                                clearable=True,
                            ),
                        ]),
                        html.Div(className="filter-control", children=[
                            html.Label("Data Fim", htmlFor="log-data-fim"),
                            dcc.DatePickerSingle(
                                id="log-data-fim",
                                display_format="DD/MM/YYYY",
                                placeholder="dd/mm/aaaa",
                                clearable=True,
                            ),
                        ]),
                        html.Div(className="filter-control", children=[
                            html.Label("Curso de Aprimoramento", htmlFor="log-filtro-curso"),
                            dcc.Dropdown(
                                id="log-filtro-curso",
                                options=[{"label": c, "value": c} for c in logbook_agg.available_cursos()],
                                value="Todos",
                                clearable=False,
                            ),
                        ]),
                        html.Div(className="filter-control", children=[
                            html.Label("Instituição Formadora", htmlFor="log-filtro-inst"),
                            dcc.Dropdown(
                                id="log-filtro-inst",
                                options=[{"label": c, "value": c} for c in logbook_agg.available_instituicoes()],
                                value="Todas",
                                clearable=False,
                            ),
                        ]),
                        html.Div(className="filter-control", children=[
                            html.Label("Hospital de Atuação", htmlFor="log-filtro-hosp"),
                            dcc.Dropdown(
                                id="log-filtro-hosp",
                                options=[{"label": c, "value": c} for c in logbook_agg.available_hospitais()],
                                value="Todos",
                                clearable=False,
                            ),
                        ]),
                        html.Div(className="filter-control filter-clear", children=[
                            dbc.Button(
                                "Limpar filtros",
                                id="log-clear-filters",
                                color="secondary",
                                outline=True,
                                size="sm",
                            ),
                        ]),
                    ],
                ),
            ),
        ],
    )


# ----------------------------------------------------------------------
# Sub-aba Visão Geral
# ----------------------------------------------------------------------
def _subtab_visao_geral() -> html.Div:
    return html.Div(
        className="dash-section",
        children=[
            html.Div(
                className="kpi-grid kpi-grid--4",
                children=[
                    _kpi_card("Total de Registros", "log-kpi-total", color="#3498db"),
                    _kpi_card("Profissionais Únicos", "log-kpi-profs", color="#8e44ad"),
                    _kpi_card("Instituições Formadoras", "log-kpi-inst", color="#16a085"),
                    _kpi_card("Hospitais de Atuação", "log-kpi-hosp", color="#c0392b"),
                ],
            ),
            html.Div(
                className="kpi-grid kpi-grid--3",
                children=[
                    _kpi_card("Cursos de Aprimoramento", "log-kpi-cursos",
                              color="#4f46e5", subtitle="Diferentes especializações"),
                    _kpi_card("Nível Médio de Desenvolvimento", "log-kpi-dev",
                              color="#f59e0b", subtitle="Escala de 1 a 5"),
                    _kpi_card("Dificuldade Média", "log-kpi-dif",
                              color="#ec4899", subtitle="Escala de 1 a 5"),
                ],
            ),
            dbc.Row([
                dbc.Col(_chart_card("Evolução Temporal dos Atendimentos / Procedimentos", "log-g-temporal"), lg=6),
                dbc.Col(_chart_card("Top 10 Instituições Formadoras", "log-g-instituicoes"), lg=6),
            ]),
            dbc.Row([
                dbc.Col(_chart_card("Distribuição por Nível de Desenvolvimento (Ten Cate)", "log-g-niveis"), lg=6),
                dbc.Col(_chart_card("Distribuição por Dificuldade", "log-g-dificuldade"), lg=6),
            ]),
            dbc.Row([
                dbc.Col(_chart_card("Top 10 Procedimentos Realizados", "log-g-procedimentos"), lg=6),
                dbc.Col(_chart_card("Top 10 CIDs Mais Frequentes", "log-g-cids"), lg=6),
            ]),
            dbc.Row([
                dbc.Col(_chart_card("Top 10 Hospitais de Atuação", "log-g-hospitais"), lg=6),
                dbc.Col(_chart_card("Top 10 Cursos de Aprimoramento", "log-g-cursos"), lg=6),
            ]),
        ],
    )


# ----------------------------------------------------------------------
# Sub-aba Geografia
# ----------------------------------------------------------------------
def _subtab_geografia() -> html.Div:
    return html.Div(
        className="dash-section",
        children=[
            html.Div(
                id="log-mapa-voltar-wrap",
                className="control-row",
                style={"display": "none"},
                children=[
                    dbc.Button(
                        "← Voltar para o mapa do Brasil",
                        id="log-btn-voltar-mapa",
                        color="primary",
                        outline=True,
                        size="sm",
                    ),
                ],
            ),
            html.Div(
                className="chart-card",
                children=[
                    html.H3(id="log-mapa-title", className="chart-card-title"),
                    dcc.Graph(
                        id="log-g-mapa",
                        config={"displayModeBar": False, "responsive": True},
                        style={"width": "100%"},
                    ),
                    html.Div(
                        "Clique num estado para ver os municípios.",
                        id="log-mapa-hint",
                        className="map-hint",
                    ),
                ],
            ),
            dcc.Store(id="log-mapa-estado-selecionado", data=None),
        ],
    )


# ----------------------------------------------------------------------
# Sub-aba Análise Diagnóstica
# ----------------------------------------------------------------------
def _subtab_diagnostica() -> html.Div:
    return html.Div(
        className="dash-section",
        children=[
            html.Div(className="chart-card", children=[
                html.H3("Progressão do Profissional ao Longo do Tempo", className="chart-card-title"),
                html.P("Evolução do nível médio de desenvolvimento (Ten Cate) por mês.",
                       className="chart-card-subtitle"),
                dcc.Graph(id="log-g-progressao",
                          config={"displayModeBar": False, "responsive": True}),
            ]),
            html.Div(className="chart-card", children=[
                html.H3("Análise de Complexidade vs Proficiência (Mapa de Calor)",
                        className="chart-card-title"),
                html.P([
                    "Cruzamento entre Nível de Desenvolvimento (linhas) e Dificuldade dos "
                    "Procedimentos (colunas). ",
                    *_help_icon(
                        "tip-heatmap",
                        html.Span([
                            html.B("Interpretação: "),
                            "Espera-se uma diagonal forte (Nível 1 com Dificuldade Extrema, "
                            "Nível 5 com Dificuldade Fácil). Valores altos fora da diagonal "
                            "podem indicar sobrecarga ou oportunidades de aprendizado "
                            "observacional.",
                        ]),
                    ),
                ], className="chart-card-subtitle"),
                html.Div(id="log-heatmap-table", className="heatmap-table-wrap"),
            ]),
            html.Div(className="chart-card", children=[
                html.H3("Análise por Curso de Aprimoramento", className="chart-card-title"),
                html.P("Top 10 cursos por volume, ordenados por dificuldade média decrescente.",
                       className="chart-card-subtitle"),
                dcc.Graph(id="log-g-curso-dificuldade",
                          config={"displayModeBar": False, "responsive": True}),
            ]),
            html.Div(className="chart-card", children=[
                html.H3("Análise Institucional Comparativa", className="chart-card-title"),
                html.P("Top 10 instituições por volume. Eixo esquerdo: volume. Eixo direito: "
                       "médias de dificuldade e nível.",
                       className="chart-card-subtitle"),
                dcc.Graph(id="log-g-institucional",
                          config={"displayModeBar": False, "responsive": True}),
            ]),
            html.Div(className="chart-card", children=[
                html.H3("Perfil de Atendimento de Alta Complexidade", className="chart-card-title"),
                html.P("Top 10 CIDs mais associados a procedimentos com dificuldade ≥ 3.",
                       className="chart-card-subtitle"),
                dcc.Graph(id="log-g-cids-alta",
                          config={"displayModeBar": False, "responsive": True}),
            ]),
        ],
    )


# ----------------------------------------------------------------------
# Sub-aba Análise Preditiva
# ----------------------------------------------------------------------
def _subtab_preditiva() -> html.Div:
    return html.Div(
        className="dash-section",
        children=[
            # SEÇÃO 1: Modelagem de Tópicos
            html.Div(className="chart-card", children=[
                html.H3("Modelagem de Tópicos - Procedimentos Não Listados", className="chart-card-title"),
                html.P([
                    "Agrupamento de procedimentos não padronizados por temas comuns usando IA "
                    "(Claude). ",
                    *_help_icon(
                        "tip-topicos",
                        html.Span([
                            html.B("Objetivo: "),
                            "entender o que está sendo registrado fora do padrão. "
                            "Procedimentos sem código específico são descritos pelos médicos "
                            "aprimorandos em campo livre de texto. A IA analisa e agrupa esses "
                            "textos por temática comum.",
                        ]),
                    ),
                ], className="chart-card-subtitle"),
                html.Div(id="log-pred-topicos-kpis", className="kpi-grid kpi-grid--3 mb-3"),
                dcc.Graph(id="log-g-topicos",
                          config={"displayModeBar": False, "responsive": True}),
                html.Details(
                    className="expandable",
                    children=[
                        html.Summary("Temas identificados por IA"),
                        html.Div(id="log-pred-topicos-detalhe", className="topics-grid"),
                    ],
                ),
            ]),
            # SEÇÃO 2: Trajetória de Aprendizado
            html.Div(className="chart-card", children=[
                html.H3("Análise de Trajetória de Aprendizado", className="chart-card-title"),
                html.P([
                    "Identificação de perfis de aprimorandos baseado em volume, complexidade, "
                    "variedade de procedimentos e velocidade de evolução. ",
                    *_help_icon(
                        "tip-trajetoria",
                        html.Div([
                            html.Div(html.B("Interpretação dos Perfis"),
                                     style={"marginBottom": "6px"}),
                            html.Div([
                                html.B("Alto volume, baixa complexidade: "),
                                "muitos procedimentos, dificuldade média baixa. Bom para "
                                "consolidação de habilidades básicas.",
                            ], style={"marginBottom": "4px"}),
                            html.Div([
                                html.B("Especialista de alta complexidade: "),
                                "focado em poucos CIDs/procedimentos, mas com alta "
                                "dificuldade. Requer mais supervisão.",
                            ], style={"marginBottom": "4px"}),
                            html.Div([
                                html.B("Evolução rápida: "),
                                "profissionais que rapidamente subiram na escala Ten Cate. "
                                "Excelente potencial de aprendizado.",
                            ], style={"marginBottom": "4px"}),
                            html.Div([
                                html.B("Generalista em desenvolvimento: "),
                                "perfil em transição com desenvolvimento balanceado.",
                            ]),
                        ]),
                    ),
                ], className="chart-card-subtitle"),
                dcc.Graph(id="log-g-trajetoria",
                          config={"displayModeBar": False, "responsive": True}),
                html.Div(id="log-pred-perfis-cards", className="profile-cards-grid"),
            ]),
            # SEÇÃO 3: Modelo Preditivo
            html.Div(className="chart-card", children=[
                html.H3("Modelo Preditivo de Dificuldade", className="chart-card-title"),
                html.P([
                    "Predição de dificuldade (1–5) baseada em CID, procedimento e contexto "
                    "clínico. ",
                    *_help_icon(
                        "tip-modelo-preditivo",
                        html.Div([
                            html.Div([
                                html.B("Interpretação: "),
                                "ajuda a identificar quais CIDs/procedimentos são "
                                "consistentemente classificados como \"difíceis\".",
                            ], style={"marginBottom": "6px"}),
                            html.Div([
                                html.B("Nota: "),
                                "CIDs com dificuldade média ≥ 3,5 podem exigir mais "
                                "supervisão, treinamento específico ou recursos adicionais.",
                            ]),
                        ]),
                    ),
                ], className="chart-card-subtitle"),
                html.Div(id="log-pred-modelo-info", className="model-info"),
                html.H4("CIDs com Maior Dificuldade Predita (Top 15)", className="chart-subsection-title"),
                dcc.Graph(id="log-g-cid-pred",
                          config={"displayModeBar": False, "responsive": True}),
                html.H4("Procedimentos com Maior Dificuldade Predita (Top 15)",
                        className="chart-subsection-title"),
                dcc.Graph(id="log-g-proc-pred",
                          config={"displayModeBar": False, "responsive": True}),
                html.H4("Análise Detalhada de CIDs (Top 10)", className="chart-subsection-title"),
                html.Div(id="log-pred-tabela-cids"),
                html.H4("Análise Detalhada de Procedimentos (Top 10)", className="chart-subsection-title"),
                html.Div(id="log-pred-tabela-procs"),
                html.Details(
                    className="expandable",
                    children=[
                        html.Summary("Geração de Conhecimento"),
                        html.Ul(className="info-list", children=[
                            html.Li([html.B("Modelo de IA (Random Forest):"),
                                     " predições treinadas com histórico de dificuldades reais."]),
                            html.Li([html.B("Confiança da Predição:"),
                                     " ≥80% muito confiável; 60–79% moderada; <60% requer cautela."]),
                            html.Li([html.B("Dificuldade Predita ≥ 2,5:"),
                                     " alta complexidade — supervisão intensiva e preparo prévio recomendados."]),
                            html.Li([html.B("Mínimo de Registros (n ≥ 5):"),
                                     " apenas CIDs/procedimentos com pelo menos 5 registros aparecem nas predições."]),
                        ]),
                    ],
                ),
            ]),
        ],
    )


# ----------------------------------------------------------------------
# LAYOUT principal
# ----------------------------------------------------------------------
def layout() -> html.Div:
    return html.Div(
        className="page page--logbook",
        children=[
            _filter_bar(),
            dcc.Tabs(
                id="log-subtabs",
                value="visao-geral",
                className="sub-tabs",
                children=[
                    dcc.Tab(label="Visão Geral", value="visao-geral",
                            className="sub-tab", selected_className="sub-tab--selected",
                            children=_subtab_visao_geral()),
                    dcc.Tab(label="Geografia", value="geografia",
                            className="sub-tab", selected_className="sub-tab--selected",
                            children=_subtab_geografia()),
                    dcc.Tab(label="Análise Diagnóstica", value="diagnostica",
                            className="sub-tab", selected_className="sub-tab--selected",
                            children=_subtab_diagnostica()),
                    dcc.Tab(label="Análise Preditiva", value="preditiva",
                            className="sub-tab", selected_className="sub-tab--selected",
                            children=_subtab_preditiva()),
                ],
            ),
        ],
    )


# ======================================================================
# CALLBACKS
# ======================================================================
def _fmt(n: int | float, decimals: int = 0) -> str:
    if isinstance(n, float):
        s = f"{n:,.{decimals}f}"
    else:
        s = f"{n:,}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# Toggle de filtros
@callback(
    Output("log-filters-collapse", "is_open"),
    Input("log-toggle-filters", "n_clicks"),
    Input("log-filters-collapse", "is_open"),
    prevent_initial_call=True,
)
def _toggle_filters(n, is_open):
    from dash import ctx
    if ctx.triggered_id == "log-toggle-filters":
        return not is_open
    return is_open


# Botão limpar
@callback(
    Output("log-data-inicio", "date"),
    Output("log-data-fim", "date"),
    Output("log-filtro-curso", "value"),
    Output("log-filtro-inst", "value"),
    Output("log-filtro-hosp", "value"),
    Output("log-filtro-rede", "value"),
    Input("log-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)
def _clear_filters(_n):
    return None, None, "Todos", "Todas", "Todos", "Todas"


# Resumo de registros
@callback(
    Output("log-records-summary", "children"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
)
def _records_summary(rede, di, df, curso, inst, hosp):
    total_all = len(loader.get_logbook_raw())
    agg = logbook_agg.aggregate_for(rede or "Todas", di, df, curso or "Todos",
                                    inst or "Todas", hosp or "Todos")
    active = sum(1 for x in (di, df,
                              (curso and curso != "Todos"),
                              (inst and inst != "Todas"),
                              (hosp and hosp != "Todos"),
                              (rede and rede != "Todas")) if x)
    if active:
        plural = "s" if active > 1 else ""
        return f"{_fmt(agg['total'])} de {_fmt(total_all)} registros ({active} filtro{plural} ativo{plural})"
    return f"{_fmt(total_all)} registros totais"


# ----------------------------------------------------------------------
# VISÃO GERAL
# ----------------------------------------------------------------------
@callback(
    Output("log-kpi-total", "children"),
    Output("log-kpi-profs", "children"),
    Output("log-kpi-inst", "children"),
    Output("log-kpi-hosp", "children"),
    Output("log-kpi-cursos", "children"),
    Output("log-kpi-dev", "children"),
    Output("log-kpi-dif", "children"),
    Output("log-g-temporal", "figure"),
    Output("log-g-instituicoes", "figure"),
    Output("log-g-niveis", "figure"),
    Output("log-g-dificuldade", "figure"),
    Output("log-g-procedimentos", "figure"),
    Output("log-g-cids", "figure"),
    Output("log-g-hospitais", "figure"),
    Output("log-g-cursos", "figure"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
)
def _update_visao_geral(rede, di, df, curso, inst, hosp):
    agg = logbook_agg.aggregate_for(rede or "Todas", di, df, curso or "Todos",
                                    inst or "Todas", hosp or "Todos")

    dificuldade_items = list(agg["dificuldade"])
    dif_cores = [DIF_COLORS.get(k, theme.ACCENT) for k, _ in dificuldade_items]

    return (
        _fmt(agg["total"]),
        _fmt(agg["profissionais"]),
        _fmt(agg["instituicoes_form"]),
        _fmt(agg["hospitais_atu"]),
        _fmt(agg["cursos_unicos"]),
        _fmt(agg["media_dev"], decimals=2),
        _fmt(agg["media_dif"], decimals=2),
        charts.line_chart(agg["temporal"], y_title="Registros", fill=True),
        charts.bar_chart(agg["instituicoes_top"], titulo="", horizontal=True,
                         sort_by_value=False, hover_texts=agg.get("instituicoes_top_hover")),
        charts.bar_chart(agg["niveis"], titulo="", sort_by_value=False, show_percent=False,
                         horizontal=False, color=theme.PRIMARY),
        charts.bar_chart(dificuldade_items, titulo="", sort_by_value=False, show_percent=False,
                         horizontal=False, color=dif_cores),
        charts.bar_chart(agg["procedimentos_top"], titulo="", horizontal=True, sort_by_value=False),
        charts.bar_chart(agg["cids_top"], titulo="", horizontal=True, sort_by_value=False),
        charts.bar_chart(agg["hospitais_top"], titulo="", horizontal=True,
                         sort_by_value=False, hover_texts=agg.get("hospitais_top_hover")),
        charts.bar_chart(agg["cursos_top"], titulo="", horizontal=True, sort_by_value=False),
    )


# ----------------------------------------------------------------------
# DIAGNÓSTICA
# ----------------------------------------------------------------------
def _build_heatmap_table(heatmap: dict) -> html.Table:
    headers = ["Nível / Dificuldade", "Fácil (1)", "Médio (2)", "Difícil (3)",
               "Muito Difícil (4)", "Extremo (5)"]
    # Para cada linha (nível), normalizar pela max DA LINHA
    rows = []
    for n in range(1, 6):
        row_vals = [heatmap[(n, d)] for d in range(1, 6)]
        row_max = max(row_vals) or 1
        cells = [html.Th(f"Nível {n}", className="hm-row-label")]
        for v in row_vals:
            intensity = v / row_max
            if v == 0:
                cls = "hm-cell hm-cell--zero"
            elif intensity > 0.75:
                cls = "hm-cell hm-cell--very-high"
            elif intensity > 0.50:
                cls = "hm-cell hm-cell--high"
            elif intensity > 0.25:
                cls = "hm-cell hm-cell--medium"
            else:
                cls = "hm-cell hm-cell--low"
            cells.append(html.Td(_fmt(v), className=cls))
        rows.append(html.Tr(cells))

    return html.Table(
        className="heatmap-table",
        children=[
            html.Thead(html.Tr([html.Th(h) for h in headers])),
            html.Tbody(rows),
        ],
    )


@callback(
    Output("log-g-progressao", "figure"),
    Output("log-heatmap-table", "children"),
    Output("log-g-curso-dificuldade", "figure"),
    Output("log-g-institucional", "figure"),
    Output("log-g-cids-alta", "figure"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
)
def _update_diagnostica(rede, di, df, curso, inst, hosp):
    agg = logbook_agg.aggregate_for(rede or "Todas", di, df, curso or "Todos",
                                    inst or "Todas", hosp or "Todos")

    inst_data = agg["institucional"]
    if inst_data:
        cats = [x["sigla"] for x in inst_data]
        institucional_fig = charts.dual_axis_bar(
            cats,
            [
                {"name": "Volume de Procedimentos",
                 "values": [x["volume"] for x in inst_data],
                 "axis": "y", "color": theme.ACCENT},
                {"name": "Dificuldade Média",
                 "values": [round(x["media_dificuldade"], 2) for x in inst_data],
                 "axis": "y2", "color": "#ec4899"},
                {"name": "Nível Médio de Desenvolvimento",
                 "values": [round(x["media_nivel"], 2) for x in inst_data],
                 "axis": "y2", "color": "#10b981"},
            ],
        )
    else:
        institucional_fig = charts._empty_fig()

    curso_dif_data = [(c, round(m, 2)) for c, m in agg["dificuldade_por_curso"]]

    return (
        charts.line_chart(agg["progressao"], y_title="Nível Ten Cate",
                          y_range=(0, 5), height=380),
        _build_heatmap_table(agg["heatmap"]),
        charts.bar_chart(curso_dif_data, titulo="", horizontal=True,
                         sort_by_value=False, show_percent=False, color="#3498db"),
        institucional_fig,
        charts.bar_chart(agg["cids_alta_complexidade"], titulo="", horizontal=True,
                         sort_by_value=False, color="#ec4899"),
    )


# ----------------------------------------------------------------------
# PREDITIVA
# ----------------------------------------------------------------------
def _kpi_box(label: str, value: str, color: str) -> html.Div:
    return html.Div(
        className="kpi-mini-card",
        style={"borderLeft": f"4px solid {color}"},
        children=[
            html.Div(label, className="kpi-mini-label"),
            html.Div(value, className="kpi-mini-value"),
        ],
    )


def _profile_card(nome: str, profissionais_ids: list, perfis_detalhados: dict, total: int) -> html.Div:
    n = len(profissionais_ids)
    pct = (n / total * 100) if total else 0
    if n == 0:
        return html.Div(className="profile-card profile-card--empty", children=[
            html.H4(nome, className="profile-card-title"),
            html.Div(f"{n} profissionais (0%)", className="profile-card-count"),
        ])

    # Médias do perfil
    vols, devs, difs, cids = [], [], [], []
    for pid in profissionais_ids:
        d = perfis_detalhados.get(str(pid)) or perfis_detalhados.get(pid)
        if not d:
            continue
        vols.append(d.get("volume", 0))
        devs.append(float(d.get("mediaDesenvolvimento", 0)))
        difs.append(float(d.get("mediaDificuldade", 0)))
        cids.append(d.get("cidUnicos", 0))

    avg_vol = sum(vols) / len(vols) if vols else 0
    avg_dev = sum(devs) / len(devs) if devs else 0
    avg_dif = sum(difs) / len(difs) if difs else 0
    avg_cid = sum(cids) / len(cids) if cids else 0

    return html.Div(className="profile-card", children=[
        html.H4(nome, className="profile-card-title"),
        html.Div([
            html.Span(_fmt(n), className="profile-card-big"),
            html.Span(f" profissionais ({pct:.1f}%)", className="profile-card-count-sub"),
        ], className="profile-card-count"),
        html.Ul(className="profile-stats", children=[
            html.Li([html.B("Volume médio: "), f"{avg_vol:.1f} procedimentos"]),
            html.Li([html.B("Nível médio: "), f"{avg_dev:.2f} (Ten Cate)"]),
            html.Li([html.B("Dificuldade média: "), f"{avg_dif:.2f}"]),
            html.Li([html.B("CIDs únicos: "), f"{avg_cid:.0f}"]),
        ]),
    ])


def _temas_grid(temas: list[dict]) -> list:
    cards = []
    for t in temas:
        ex_proc = ", ".join((t.get("procedimentos") or [])[:2])
        ex_text = f"Ex.: {ex_proc}…" if ex_proc else ""
        cards.append(html.Div(className="topic-card", children=[
            html.Div(t.get("nome", "—"), className="topic-name"),
            html.Div(t.get("descricao", ""), className="topic-desc"),
            html.Div(f"{t.get('frequencia', 0)} ocorrências", className="topic-freq"),
            html.Div(ex_text, className="topic-examples") if ex_text else None,
        ]))
    return cards


def _detail_table(stats: list[dict], key_label: str, has_ml_predictions: bool) -> html.Table:
    headers = [key_label]
    if has_ml_predictions:
        headers += ["Dificuldade Predita", "Confiança ML"]
    else:
        headers += ["Dificuldade Média", "Min–Max", "Desvio Padrão"]
    headers += ["Registros", "Recomendação"]

    rows = []
    for i, s in enumerate(stats[:10]):
        dif_val = s.get("dificuldadePredita") if s.get("dificuldadePredita") is not None else s.get("media")
        dif_num = float(dif_val) if dif_val is not None else 0
        dif_class = ("text-danger" if dif_num >= 2.5
                     else "text-warning" if dif_num >= 1.5
                     else "text-success")
        recomendacao = ("Alta supervisão" if dif_num >= 2.5
                        else "Monitorar" if dif_num >= 1.5
                        else "Rotina")

        cells = [html.Td(s.get(key_label.lower().split()[0], "—"), className="mono")]
        cells.append(html.Td(f"{dif_val}", className=f"strong {dif_class}"))
        if has_ml_predictions:
            conf = s.get("confianca")
            if conf is not None:
                conf_pct = round(conf * 100 if conf <= 1 else conf, 0)
                conf_class = ("text-success" if conf_pct >= 80
                              else "text-warning" if conf_pct >= 60
                              else "text-danger")
                cells.append(html.Td(f"{int(conf_pct)}%", className=conf_class))
            else:
                cells.append(html.Td("—"))
        else:
            cells.append(html.Td(f"{s.get('min', '—')} – {s.get('max', '—')}"))
            cells.append(html.Td(f"{s.get('desvio', '—')}"))
        cells.append(html.Td(_fmt(s.get("count", 0))))
        cells.append(html.Td(recomendacao))
        rows.append(html.Tr(cells, className="row-zebra" if i % 2 else None))

    return html.Table(
        className="detail-table",
        children=[
            html.Thead(html.Tr([html.Th(h) for h in headers])),
            html.Tbody(rows),
        ],
    )


@callback(
    Output("log-pred-topicos-kpis", "children"),
    Output("log-g-topicos", "figure"),
    Output("log-pred-topicos-detalhe", "children"),
    Output("log-g-trajetoria", "figure"),
    Output("log-pred-perfis-cards", "children"),
    Output("log-pred-modelo-info", "children"),
    Output("log-g-cid-pred", "figure"),
    Output("log-g-proc-pred", "figure"),
    Output("log-pred-tabela-cids", "children"),
    Output("log-pred-tabela-procs", "children"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
)
def _update_preditiva(rede, di, df, curso, inst, hosp):
    rede = rede or "Todas"
    agg = logbook_agg.aggregate_for(rede, di, df, curso or "Todos",
                                    inst or "Todas", hosp or "Todos")

    # Análise Claude pré-baked por rede
    analise = loader.get_logbook_analysis(rede)
    ml = loader.get_ml_predictions().get(rede, {})

    # --- TÓPICOS ---
    temas = (analise.get("analiseTopicos") or {}).get("temas") or []
    topicos_kpis = [
        _kpi_box("Procedimentos Não Listados (filtrados)", _fmt(agg["procedimentos_nl_total"]), "#3b82f6"),
        _kpi_box("Procedimentos Únicos (filtrados)", _fmt(agg["procedimentos_nl_unicos"]), "#8e44ad"),
        _kpi_box("Temas Identificados (pré-processado)", _fmt(len(temas)), "#10b981"),
    ]

    if temas:
        temas_sorted = sorted(temas, key=lambda t: t.get("frequencia", 0), reverse=True)
        tema_items = [(t["nome"], t.get("frequencia", 0)) for t in temas_sorted]
        cores_temas = [theme.CATEGORICAL[i % len(theme.CATEGORICAL)]
                       for i in range(len(tema_items))]
        topicos_fig = charts.bar_chart(tema_items, titulo="", horizontal=True,
                                       sort_by_value=False, show_percent=False,
                                       color=cores_temas, max_categorias=40)
        topicos_detalhe = _temas_grid(temas_sorted)
    else:
        topicos_fig = charts._empty_fig()
        topicos_detalhe = [html.Div(
            "Sem temas pré-processados pra esta rede. Execute o pipeline (etapa 5-6) "
            "para gerar análise via Claude.",
            className="muted-note",
        )]

    # --- TRAJETÓRIA ---
    trajetoria = analise.get("analiseTrajetoria") or {}
    perfis = trajetoria.get("perfis") or {}
    perfis_det = trajetoria.get("perfisDetalhados") or {}
    total_profs = sum(len(ids) for ids in perfis.values())

    if perfis:
        traj_items = [(nome, len(ids)) for nome, ids in perfis.items()]
        trajetoria_fig = charts.doughnut(traj_items, height=320)
        perfis_cards = [
            _profile_card(nome, ids, perfis_det, total_profs)
            for nome, ids in perfis.items()
        ]
    else:
        trajetoria_fig = charts._empty_fig()
        perfis_cards = [html.Div("Trajetória indisponível pra esta rede.",
                                  className="muted-note")]

    # --- MODELO PREDITIVO ---
    modelo_usado = ml.get("modelo_usado", "")
    acuracia = ml.get("acuracia")
    MODEL_LABELS = {
        "random_forest": "Random Forest",
        "gradient_boosting": "Gradient Boosting",
    }
    info_parts = []
    if modelo_usado:
        rotulo = MODEL_LABELS.get(modelo_usado, modelo_usado.replace("_", " ").title())
        info_parts.append(html.Span([html.B("Modelo: "), rotulo], className="me-3"))
    if acuracia is not None:
        info_parts.append(html.Span([html.B("Acurácia: "), f"{float(acuracia) * 100:.1f}%"]))
    modelo_info = info_parts if info_parts else html.Span(
        "Modelo ML não disponível — usando análise estatística do analiseModelo.",
        className="muted-note",
    )

    # Stats vêm do analiseModelo (com média/desvio) ou de ml['cids'/'procedimentos']
    cid_stats_raw = (analise.get("analiseModelo") or {}).get("cidStats") or []
    proc_stats_raw = (analise.get("analiseModelo") or {}).get("procedimentoStats") or []

    # Há predições ML quando há um modelo treinado (RF ou GB)
    has_ml_predictions = bool(modelo_usado) and bool(ml.get("cids") or ml.get("procedimentos"))

    # Se houver predições ML, mesclar dificuldade_predita + confianca
    if has_ml_predictions:
        ml_cids = ml.get("cids", {})
        ml_procs = ml.get("procedimentos", {})
        for s in cid_stats_raw:
            pred = ml_cids.get(s.get("cid"))
            if pred:
                s["dificuldadePredita"] = pred.get("dificuldade_predita")
                s["confianca"] = pred.get("confianca")
        for s in proc_stats_raw:
            pred = ml_procs.get(s.get("procedimento"))
            if pred:
                s["dificuldadePredita"] = pred.get("dificuldade_predita")
                s["confianca"] = pred.get("confianca")

    # Ordenar por dificuldade (predita > média) decrescente, pegar top 15 para gráfico
    def _dif_key(s):
        return float(s.get("dificuldadePredita") if s.get("dificuldadePredita") is not None
                     else s.get("media", 0))

    cid_sorted = sorted(cid_stats_raw, key=_dif_key, reverse=True)
    proc_sorted = sorted(proc_stats_raw, key=_dif_key, reverse=True)

    def _to_bar(stats, key):
        items = [(s.get(key, "—"), _dif_key(s)) for s in stats[:15]]
        cores = []
        for _, v in items:
            if v >= 2.5:
                cores.append("#ef4444")
            elif v >= 1.5:
                cores.append("#f59e0b")
            else:
                cores.append("#10b981")
        return charts.bar_chart(items, titulo="", horizontal=True,
                                sort_by_value=False, show_percent=False,
                                color=cores, max_categorias=15,
                                truncate_labels=35, x_max=5.5)

    cid_pred_fig = _to_bar(cid_sorted, "cid")
    proc_pred_fig = _to_bar(proc_sorted, "procedimento")

    cid_tabela = _detail_table(cid_sorted, "CID", has_ml_predictions)
    proc_tabela = _detail_table(proc_sorted, "Procedimento", has_ml_predictions)

    return (
        topicos_kpis, topicos_fig, topicos_detalhe,
        trajetoria_fig, perfis_cards,
        modelo_info, cid_pred_fig, proc_pred_fig,
        cid_tabela, proc_tabela,
    )


# ----------------------------------------------------------------------
# GEOGRAFIA — mapa coroplético com drilldown estado → municípios
# ----------------------------------------------------------------------
@callback(
    Output("log-g-mapa", "figure"),
    Output("log-mapa-title", "children"),
    Output("log-mapa-hint", "style"),
    Output("log-mapa-voltar-wrap", "style"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
    Input("log-mapa-estado-selecionado", "data"),
)
def _update_log_mapa(rede, di, df, curso, inst, hosp, estado_sel):
    agg = logbook_agg.aggregate_for(
        rede or "Todas", di, df, curso or "Todos", inst or "Todas", hosp or "Todos",
    )
    hint_show = {"display": "block"} if not estado_sel else {"display": "none"}
    voltar_show = {"display": "block"} if estado_sel else {"display": "none"}

    if estado_sel:
        sigla = ESTADOS_SIGLAS.get(estado_sel)
        if not sigla:
            return (charts._empty_fig(), f"Estado não reconhecido: {estado_sel}",
                    hint_show, voltar_show)
        geo = geojson_municipios(sigla)
        if not geo.get("features"):
            return (charts._empty_fig(), f"Falha ao carregar municípios de {estado_sel}",
                    hint_show, voltar_show)

        cidades_count = agg["geo_municipios"].get(sigla, {})
        locations, z_values, hover_text = [], [], []
        for feat in geo["features"]:
            nome = feat.get("properties", {}).get("name")
            if not nome:
                continue
            count = cidades_count.get(nome, 0)
            locations.append(nome)
            z_values.append(count)
            if count > 0:
                hover_text.append(f"<b>{nome}</b><br>{count:,} registros".replace(",", "."))
            else:
                hover_text.append(f"<b>{nome}</b><br>Sem registros")

        import plotly.graph_objects as go
        fig = go.Figure(go.Choropleth(
            geojson=geo,
            locations=locations,
            z=z_values,
            featureidkey="properties.name",
            colorscale=[
                [0.0, "#E0E0E0"], [0.000001, "#dbe9f6"], [1.0, theme.ACCENT_DARK],
            ],
            showscale=True,
            text=hover_text,
            hoverinfo="text",
            marker={"line": {"color": "rgba(0,0,0,0.3)", "width": 0.5}},
        ))
        fig.update_layout(
            **theme.plotly_layout_defaults(),
            height=600,
            margin={"l": 0, "r": 0, "t": 20, "b": 0},
            geo={"fitbounds": "locations", "visible": False, "bgcolor": theme.SURFACE},
        )
        total = sum(z_values)
        return (fig, f"Registros por município — {estado_sel} ({total:,} registros)".replace(",", "."),
                hint_show, voltar_show)

    # Mapa nacional: contagem por estado (converte sigla → nome do estado pra match geojson)
    estados_count = {
        SIGLAS_ESTADOS.get(s, s): c for s, c in agg["geo_estados"].items()
    }
    total = sum(estados_count.values())
    fig = charts.choropleth_brasil(
        estados_count,
        "",
        geojson_brasil(),
    )
    return (fig, f"Registros por estado ({total:,} registros)".replace(",", "."),
            hint_show, voltar_show)


@callback(
    Output("log-mapa-estado-selecionado", "data"),
    Input("log-g-mapa", "clickData"),
    Input("log-btn-voltar-mapa", "n_clicks"),
    Input("log-filtro-rede", "value"),
    Input("log-data-inicio", "date"),
    Input("log-data-fim", "date"),
    Input("log-filtro-curso", "value"),
    Input("log-filtro-inst", "value"),
    Input("log-filtro-hosp", "value"),
    prevent_initial_call=True,
)
def _on_log_mapa_interaction(click_data, _n_voltar, *_filters):
    from dash import ctx
    triggered = ctx.triggered_id
    # Qualquer mudança de filtro ou clique no botão "Voltar" → limpa estado
    if triggered != "log-g-mapa":
        return None
    if click_data:
        try:
            return click_data["points"][0]["location"]
        except (KeyError, IndexError, TypeError):
            pass
    from dash import no_update
    return no_update
