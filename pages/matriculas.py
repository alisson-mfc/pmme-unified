"""Aba Matrículas — port 1:1 das seções de dashboard.html + mapas.html.

Ordem preservada: KPI/Filtros → Dados Pessoais → Formação Acadêmica → Especialidades
e Títulos → Distribuição Geográfica → Mapas → Apropriação sobre Temas →
Análise Qualitativa.

Novidade: filtro de Ano de Matrícula (extraído de data_matricula). Combinado com a
rede, gera 9 cortes possíveis pra análise Claude.
"""

from __future__ import annotations

from functools import lru_cache

import dash_bootstrap_components as dbc
import requests
from dash import Input, Output, callback, dcc, html, no_update

from components import charts
from data import loader, matriculas_agg
from data.constants import (
    ESTADOS_SIGLAS,
    GEOJSON_BRASIL_ESTADOS,
    SIGLAS_IBGE,
)

# ----------------------------------------------------------------------
# Constantes de UI
# ----------------------------------------------------------------------
TEMAS_TITULOS = {
    "apropriacao_redes": "Organização de Redes de Atenção à Saúde",
    "apropriacao_coordenacao": "Coordenação do Cuidado",
    "apropriacao_gestao": "Gestão da Clínica e do Cuidado",
    "apropriacao_evidencias": "Saúde Baseada em Evidências",
    "apropriacao_economia": "Plataformas Digitais",
}

CAMPOS_QUALITATIVOS = {
    "aptidoes_rotina": "Expectativas em relação ao PMM-e",
    "competencias_fortalecer": "Considera apto para atuação",
    "impressao_servico": "Impressão sobre o serviço",
    "momento_imersao": "Expectativas para imersão",
}

MAPAS_TIPOS = {
    "mapa_estado_vaga": "Estado da Vaga Principal",
    "mapa_estado_nascimento": "Estado de Nascimento",
    "mapa_estado_graduacao": "Estado de Graduação",
    "mapa_estado_crm": "Estado do CRM",
}


# ----------------------------------------------------------------------
# Geojson loader (cached lazily)
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _geojson_brasil() -> dict:
    try:
        r = requests.get(GEOJSON_BRASIL_ESTADOS, timeout=20)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {"features": []}


@lru_cache(maxsize=32)
def _geojson_municipios(uf_sigla: str) -> dict:
    codigo = SIGLAS_IBGE.get(uf_sigla)
    if not codigo:
        return {"features": []}
    url = f"https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-{codigo}-mun.json"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {"features": []}


# ----------------------------------------------------------------------
# Helpers de layout
# ----------------------------------------------------------------------
def _chart_card(title: str, graph_id: str, height: int = 420) -> html.Div:
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


def _section(title: str, *children) -> html.Section:
    return html.Section(
        className="dash-section",
        children=[html.H2(title, className="section-title"), *children],
    )


# ----------------------------------------------------------------------
# LAYOUT
# ----------------------------------------------------------------------
def layout() -> html.Div:
    anos = matriculas_agg.available_anos()  # ["Todos", "2025", "2026"]

    filter_bar = html.Div(
        className="filter-bar",
        children=[
            html.Div(
                className="kpi-counter",
                children=[
                    html.Div("Matriculados", className="kpi-counter-label"),
                    html.Div(id="mat-total", className="kpi-counter-value", children="—"),
                ],
            ),
            html.Div(
                className="filter-group",
                children=[
                    html.Div(
                        className="filter-control",
                        children=[
                            html.Label("Rede Formadora", htmlFor="mat-filtro-rede"),
                            dcc.Dropdown(
                                id="mat-filtro-rede",
                                options=[{"label": x, "value": x}
                                         for x in ("Todas", "EBSERH", "PROADI-SUS")],
                                value="Todas",
                                clearable=False,
                            ),
                        ],
                    ),
                    html.Div(
                        className="filter-control",
                        children=[
                            html.Label("Ano de Matrícula", htmlFor="mat-filtro-ano"),
                            dcc.Dropdown(
                                id="mat-filtro-ano",
                                options=[{"label": a, "value": a} for a in anos],
                                value="Todos",
                                clearable=False,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    sec_dados_pessoais = _section(
        "Dados Pessoais",
        dbc.Row([
            dbc.Col(_chart_card("Distribuição por Raça", "mat-g-raca"), md=6),
            dbc.Col(_chart_card("Distribuição por Sexo", "mat-g-sexo"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Distribuição de Idade", "mat-g-idade"), md=6),
            dbc.Col(_chart_card("Estado Civil", "mat-g-estado-civil"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Identidade de Gênero", "mat-g-genero"), md=6),
            dbc.Col(_chart_card("Orientação Sexual", "mat-g-orientacao"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Profissionais com Nome Social", "mat-g-nome-social"), md=6),
            dbc.Col(_chart_card("Ações Afirmativas", "mat-g-aa"), md=6),
        ]),
    )

    sec_formacao = _section(
        "Formação Acadêmica",
        dbc.Row([
            dbc.Col(_chart_card("Tempo de Graduado (anos)", "mat-g-tempo-graduado"), md=6),
            dbc.Col(_chart_card("País de Formação", "mat-g-pais-formacao"), md=6),
        ]),
    )

    sec_especialidades = _section(
        "Especialidades e Títulos",
        dbc.Row([
            dbc.Col(_chart_card("Residências Médicas", "mat-g-residencias"), md=6),
            dbc.Col(_chart_card("Título de Especialista", "mat-g-titulo-especialista"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Área — RM Primária", "mat-g-rm-primaria"), md=6),
            dbc.Col(_chart_card("Área — RM Secundária", "mat-g-rm-secundaria"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Área — Título Especialista Primário", "mat-g-titulo-primario"), md=6),
            dbc.Col(_chart_card("Área — Título Especialista Secundário", "mat-g-titulo-secundario"), md=6),
        ]),
        dbc.Row([
            dbc.Col(_chart_card("Cursos de Aprimoramento", "mat-g-cursos"), md=12),
        ]),
    )

    sec_geografica = _section(
        "Distribuição Geográfica",
        _chart_card("Distribuição Regional por Momento", "mat-g-regioes"),
        dbc.Row([
            dbc.Col(_chart_card("Região de Nascimento", "mat-g-regiao-nascimento"), md=6),
            dbc.Col(_chart_card("Região da Vaga Principal", "mat-g-regiao-vaga"), md=6),
        ]),
    )

    sec_mapas = _section(
        "Mapas",
        html.Div(
            className="control-row",
            children=[
                html.Label("Tipo de mapa", htmlFor="mat-tipo-mapa"),
                dcc.Dropdown(
                    id="mat-tipo-mapa",
                    options=[{"label": v, "value": k} for k, v in MAPAS_TIPOS.items()],
                    value="mapa_estado_vaga",
                    clearable=False,
                ),
            ],
        ),
        html.Div(
            id="mat-mapa-voltar-wrap",
            className="control-row",
            style={"display": "none"},
            children=[
                dbc.Button(
                    "← Voltar para o mapa do Brasil",
                    id="mat-btn-voltar-mapa",
                    color="primary",
                    outline=True,
                    size="sm",
                ),
            ],
        ),
        html.Div(
            className="chart-card",
            children=[
                html.H3(id="mat-mapa-title", className="chart-card-title"),
                dcc.Graph(
                    id="mat-mapa",
                    config={"displayModeBar": False, "responsive": True},
                    style={"width": "100%"},
                ),
                html.Div(
                    "Dica: selecione \"Estado da Vaga Principal\" e clique num estado para ver os municípios com vagas.",
                    id="mat-mapa-hint",
                    className="map-hint",
                ),
            ],
        ),
        dcc.Store(id="mat-mapa-estado-selecionado", data=None),
    )

    sec_apropriacao = _section(
        "Apropriação sobre Temas",
        html.Div(
            className="control-row",
            children=[
                html.Label("Selecione o tema", htmlFor="mat-dropdown-apropriacao"),
                dcc.Dropdown(
                    id="mat-dropdown-apropriacao",
                    options=[{"label": v, "value": k} for k, v in TEMAS_TITULOS.items()],
                    value="apropriacao_redes",
                    clearable=False,
                ),
            ],
        ),
        html.Div(
            className="chart-card",
            children=[
                html.H3(id="mat-apropriacao-title", className="chart-card-title"),
                dcc.Graph(
                    id="mat-g-apropriacao",
                    config={"displayModeBar": False, "responsive": True},
                    style={"width": "100%"},
                ),
            ],
        ),
    )

    sec_qualitativa = _section(
        "Análise Qualitativa",
        html.Div(
            className="control-row",
            children=[
                html.Label("Selecione o campo textual", htmlFor="mat-dropdown-qualitativo"),
                dcc.Dropdown(
                    id="mat-dropdown-qualitativo",
                    options=[{"label": v, "value": k} for k, v in CAMPOS_QUALITATIVOS.items()],
                    value="aptidoes_rotina",
                    clearable=False,
                ),
            ],
        ),
        html.Div(
            className="chart-card",
            children=[
                html.H3("Nuvem de Palavras", className="chart-card-title"),
                html.Div(id="mat-nuvem-wrap", className="nuvem-wrap"),
            ],
        ),
        _chart_card("Análise de Sentimentos", "mat-g-sentimentos", height=380),
        html.Div(
            className="chart-card",
            children=[
                html.H3("Resumo dos Textos", className="chart-card-title"),
                dcc.Markdown(
                    id="mat-resumo",
                    children="*Selecione um campo para visualizar o resumo.*",
                    className="resumo-markdown",
                ),
            ],
        ),
    )

    return html.Div(
        className="page page--matriculas",
        children=[
            filter_bar,
            sec_dados_pessoais,
            sec_formacao,
            sec_especialidades,
            sec_geografica,
            sec_mapas,
            sec_apropriacao,
            sec_qualitativa,
        ],
    )


# ----------------------------------------------------------------------
# CALLBACKS
# ----------------------------------------------------------------------
def _fmt_total(n: int) -> str:
    return f"{n:,}".replace(",", ".")


@callback(
    Output("mat-total", "children"),
    Output("mat-g-raca", "figure"),
    Output("mat-g-sexo", "figure"),
    Output("mat-g-idade", "figure"),
    Output("mat-g-estado-civil", "figure"),
    Output("mat-g-genero", "figure"),
    Output("mat-g-orientacao", "figure"),
    Output("mat-g-nome-social", "figure"),
    Output("mat-g-aa", "figure"),
    Output("mat-g-tempo-graduado", "figure"),
    Output("mat-g-pais-formacao", "figure"),
    Output("mat-g-residencias", "figure"),
    Output("mat-g-titulo-especialista", "figure"),
    Output("mat-g-rm-primaria", "figure"),
    Output("mat-g-rm-secundaria", "figure"),
    Output("mat-g-titulo-primario", "figure"),
    Output("mat-g-titulo-secundario", "figure"),
    Output("mat-g-cursos", "figure"),
    Output("mat-g-regioes", "figure"),
    Output("mat-g-regiao-nascimento", "figure"),
    Output("mat-g-regiao-vaga", "figure"),
    Input("mat-filtro-rede", "value"),
    Input("mat-filtro-ano", "value"),
)
def _update_static_charts(rede: str, ano: str):
    rede = rede or "Todas"
    ano = ano or "Todos"
    agg = matriculas_agg.aggregate_for(rede, ano)

    return (
        _fmt_total(agg["total"]),
        charts.bar_chart(agg["raca_ds"], "Distribuição por Raça"),
        charts.bar_chart(agg["sexo_ds"], "Distribuição por Sexo"),
        charts.histogram(agg["idade"], "Distribuição de Idade"),
        charts.bar_chart(agg["estado_civil_ds"], "Estado Civil"),
        charts.bar_chart(agg["ident_genero_ds"], "Identidade de Gênero"),
        charts.bar_chart(agg["orientacao_sexual_ds"], "Orientação Sexual"),
        charts.bar_chart(agg["tem_nome_social"], "Profissionais com Nome Social"),
        charts.bar_chart(agg["aa_tipo_ds"], "Ações Afirmativas"),
        charts.histogram(agg["tempo_graduado"], "Tempo de Graduado (anos)"),
        charts.bar_chart(agg["pais_formacao_ds"], "País de Formação"),
        charts.bar_chart(agg["rm_rec_cnrm_ds"], "Residências Médicas"),
        charts.bar_chart(agg["tit_esp_amb_ds"], "Título de Especialista"),
        charts.bar_chart(agg["rm_1_esp_medica_ds"], "Área — RM Primária"),
        charts.bar_chart(agg["rm_2_esp_medica_ds"], "Área — RM Secundária"),
        charts.bar_chart(agg["amb_1_esp_medica_ds"], "Área — Título Especialista Primário"),
        charts.bar_chart(agg["amb_2_esp_medica_ds"], "Área — Título Especialista Secundário"),
        charts.bar_chart(agg["curso_nome_limpo"], "Cursos de Aprimoramento", height=550),
        charts.line_regioes(agg["fluxo_regional"]),
        charts.bar_chart(agg["regiao_nascimento"], "Região de Nascimento"),
        charts.bar_chart(agg["regiao_vaga"], "Região da Vaga Principal"),
    )


@callback(
    Output("mat-g-apropriacao", "figure"),
    Output("mat-apropriacao-title", "children"),
    Input("mat-filtro-rede", "value"),
    Input("mat-filtro-ano", "value"),
    Input("mat-dropdown-apropriacao", "value"),
)
def _update_apropriacao(rede: str, ano: str, tema: str):
    rede = rede or "Todas"
    ano = ano or "Todos"
    tema = tema or "apropriacao_redes"
    agg = matriculas_agg.aggregate_for(rede, ano)
    return charts.apropriacao_bar(agg.get(tema, {})), TEMAS_TITULOS.get(tema, tema)


# ----------------------------------------------------------------------
# Mapas — choropleth Brasil + drilldown estado→municípios
# ----------------------------------------------------------------------
@callback(
    Output("mat-mapa", "figure"),
    Output("mat-mapa-title", "children"),
    Output("mat-mapa-hint", "style"),
    Output("mat-mapa-voltar-wrap", "style"),
    Input("mat-filtro-rede", "value"),
    Input("mat-filtro-ano", "value"),
    Input("mat-tipo-mapa", "value"),
    Input("mat-mapa-estado-selecionado", "data"),
)
def _update_mapa(rede: str, ano: str, tipo: str, estado_sel: str | None):
    rede = rede or "Todas"
    ano = ano or "Todos"
    tipo = tipo or "mapa_estado_vaga"
    agg = matriculas_agg.aggregate_for(rede, ano)

    hint_show = {"display": "block"} if (tipo == "mapa_estado_vaga" and not estado_sel) else {"display": "none"}
    voltar_show = {"display": "block"} if estado_sel else {"display": "none"}

    # Drilldown: mostra municípios com vagas no estado selecionado
    if estado_sel and tipo == "mapa_estado_vaga":
        sigla = ESTADOS_SIGLAS.get(estado_sel)
        if not sigla:
            return charts._empty_fig(), f"Estado não reconhecido: {estado_sel}", hint_show, voltar_show
        geo = _geojson_municipios(sigla)
        if not geo.get("features"):
            return charts._empty_fig(), f"Falha ao carregar municípios de {estado_sel}", hint_show, voltar_show

        vagas = [v for v in agg["vagas_por_municipio"] if v["vaga_uf"] == estado_sel]
        vagas_map = {v["vaga_municipio"]: v["cursos"] for v in vagas}

        locations = []
        z_values = []
        hover_text = []
        for feat in geo["features"]:
            nome = feat.get("properties", {}).get("name")
            if not nome:
                continue
            locations.append(nome)
            if nome in vagas_map:
                z_values.append(1)
                cursos_html = "<br>".join(f"• {c}" for c in vagas_map[nome])
                hover_text.append(f"<b>{nome}</b><br>— Áreas —<br>{cursos_html}")
            else:
                z_values.append(0)
                hover_text.append(f"<b>{nome}</b><br>Sem vagas")

        import plotly.graph_objects as go
        from components import theme

        fig = go.Figure(go.Choropleth(
            geojson=geo,
            locations=locations,
            z=z_values,
            featureidkey="properties.name",
            colorscale=[[0, "#e8eef5"], [1, theme.SUCCESS]],
            showscale=False,
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
        return fig, f"Municípios com Vagas — {estado_sel}", hint_show, voltar_show

    # Mapa nacional
    return (
        charts.choropleth_brasil(agg[tipo], MAPAS_TIPOS[tipo], _geojson_brasil()),
        MAPAS_TIPOS[tipo],
        hint_show,
        voltar_show,
    )


@callback(
    Output("mat-mapa-estado-selecionado", "data"),
    Input("mat-mapa", "clickData"),
    Input("mat-btn-voltar-mapa", "n_clicks"),
    Input("mat-tipo-mapa", "value"),
    Input("mat-filtro-rede", "value"),
    Input("mat-filtro-ano", "value"),
    prevent_initial_call=True,
)
def _on_mapa_interaction(click_data, n_voltar, tipo, _rede, _ano):
    from dash import ctx
    triggered = ctx.triggered_id

    # Qualquer mudança que não seja clique no mapa → reseta drilldown
    if triggered in ("mat-btn-voltar-mapa", "mat-tipo-mapa", "mat-filtro-rede", "mat-filtro-ano"):
        return None

    if triggered == "mat-mapa" and click_data and tipo == "mapa_estado_vaga":
        try:
            return click_data["points"][0]["location"]
        except (KeyError, IndexError, TypeError):
            return no_update

    return no_update


# ----------------------------------------------------------------------
# Análise Qualitativa (Claude)
# ----------------------------------------------------------------------
@callback(
    Output("mat-nuvem-wrap", "children"),
    Output("mat-g-sentimentos", "figure"),
    Output("mat-resumo", "children"),
    Input("mat-filtro-rede", "value"),
    Input("mat-filtro-ano", "value"),
    Input("mat-dropdown-qualitativo", "value"),
)
def _update_qualitativo(rede: str, ano: str, campo: str):
    rede = rede or "Todas"
    ano = ano or "Todos"
    campo = campo or "aptidoes_rotina"

    analise = loader.get_matriculas_analysis(rede, ano)
    campos = (analise or {}).get("campos", {})
    dados_campo = campos.get(campo)

    if not dados_campo:
        nuvem = html.Div(
            "Análise indisponível para este corte. "
            "Execute o pipeline (etapa 5-6) pra gerar.",
            className="nuvem-empty",
        )
        sent_fig = charts.sentiment_bar({}, "Análise de Sentimentos")
        resumo = "*Análise indisponível para este corte.*"
        return nuvem, sent_fig, resumo

    src = loader.get_nuvem_palavras_src(rede, ano, campo)
    if src:
        nuvem = html.Img(src=src, alt=f"Nuvem de palavras — {campo}", className="nuvem-img")
    else:
        nuvem = html.Div("Nuvem de palavras indisponível.", className="nuvem-empty")

    distribuicao = (dados_campo.get("sentimentos") or {}).get("distribuicao") or {}
    sent_fig = charts.sentiment_bar(distribuicao)

    resumo_txt = dados_campo.get("resumo") or "*Resumo não disponível.*"
    return nuvem, sent_fig, resumo_txt
