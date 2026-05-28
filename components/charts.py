"""Fábricas de gráficos Plotly com o tema PMM-e aplicado.

Mantém a mesma lógica visual dos dashboards originais (orientação horizontal pra
legendas longas, anotações de média/mediana em histogramas, etc.) mas usa a paleta
sóbria do components.theme em vez do default Plotly.
"""

from __future__ import annotations

import plotly.graph_objects as go

from components import theme


# ----------------------------------------------------------------------
def _empty_fig(_titulo: str = "") -> go.Figure:
    """Figura vazia uniforme. O título fica a cargo do card que a contém."""
    fig = go.Figure()
    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=320,
        margin={"t": 20, "b": 20, "l": 20, "r": 20},
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": "Sem dados para o filtro selecionado",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "xanchor": "center",
                "showarrow": False, "font": {"color": theme.TEXT_MUTED, "size": 14},
            }
        ],
    )
    return fig


# ----------------------------------------------------------------------
def bar_chart(
    dados: dict[str, int] | list[tuple[str, int]],
    titulo: str,
    max_categorias: int = 25,
    height: int = 420,
    color: str | list[str] | None = None,
    horizontal: bool | None = None,
    sort_by_value: bool = True,
    show_percent: bool = True,
    hover_texts: list[str] | None = None,
    truncate_labels: int | None = None,
    x_max: float | None = None,
) -> go.Figure:
    """Bar chart com escolha automática de orientação (horizontal se rótulos longos).

    `color` aceita string única ou lista de cores (mesmo length de items).
    `horizontal=None` decide automaticamente; passe True/False pra forçar.
    `sort_by_value=False` preserva ordem original de items.
    `hover_texts` (opcional): se fornecido, sobrescreve o hover padrão por item.
        Deve ter mesmo comprimento de `dados` ANTES do truncamento por max_categorias.
    """
    if isinstance(dados, dict):
        items = list(dados.items())
    else:
        items = list(dados)
    if not items:
        return _empty_fig(titulo)

    # Combina items + hover_texts antes de sort/truncate, pra manter alinhados
    indexed = list(zip(range(len(items)), items, hover_texts or [None] * len(items)))
    if sort_by_value:
        indexed.sort(key=lambda x: x[1][1], reverse=True)
    indexed = indexed[:max_categorias]

    items = [x[1] for x in indexed]
    hovers = [x[2] for x in indexed]
    categorias_full = [str(k) for k, _ in items]

    # Trunca labels com '...' se solicitado, e usa nome completo no hover.
    if truncate_labels and truncate_labels > 0:
        categorias = [
            (c[: truncate_labels - 1] + "…") if len(c) > truncate_labels else c
            for c in categorias_full
        ]
        # Se não havia hover customizado, usa o nome completo
        if not any(hovers):
            hovers = [f"<b>{c}</b>" for c in categorias_full]
    else:
        categorias = categorias_full

    quantidades = [v for _, v in items]
    total = sum(quantidades) or 1
    percentuais = [f"{(q / total) * 100:.1f}%" for q in quantidades] if show_percent else [str(q) for q in quantidades]

    media_len = sum(len(c) for c in categorias) / len(categorias)
    max_len = max(len(c) for c in categorias)
    if horizontal is None:
        horizontal = media_len > 12 or max_len > 20

    if isinstance(color, list):
        bar_color = color
    else:
        bar_color = color or theme.ACCENT
    layout_defaults = theme.plotly_layout_defaults()

    if horizontal:
        cat_rev = list(reversed(categorias))
        qty_rev = list(reversed(quantidades))
        pct_rev = list(reversed(percentuais))
        cor_rev = list(reversed(bar_color)) if isinstance(bar_color, list) else bar_color
        hov_rev = list(reversed(hovers)) if any(hovers) else None

        if hov_rev is not None:
            trace = go.Bar(
                x=qty_rev, y=cat_rev, orientation="h",
                text=pct_rev, textposition="outside",
                marker_color=cor_rev,
                customdata=hov_rev,
                hovertemplate="%{customdata}<br>Quantidade: %{x}<br>%{text}<extra></extra>",
            )
        else:
            trace = go.Bar(
                x=qty_rev, y=cat_rev, orientation="h",
                text=pct_rev, textposition="outside",
                marker_color=cor_rev,
                hovertemplate="<b>%{y}</b><br>Quantidade: %{x}<br>%{text}<extra></extra>",
            )

        # Após truncar, max_len reflete o tamanho exibido. Margens caem.
        eff_max_len = max(len(c) for c in categorias)
        margem_esq = min(300, eff_max_len * 8)
        valor_max = max(quantidades)
        if eff_max_len > 60:
            margem_dir = 160
        elif valor_max > 500:
            margem_dir = 140
        else:
            margem_dir = 120

        if x_max is not None:
            x_range = [0, x_max]
        else:
            if valor_max <= 10:
                mult = 2.0
            elif valor_max <= 30:
                mult = 1.5
            elif valor_max <= 100:
                mult = 1.35
            else:
                mult = 1.25
            x_range = [0, valor_max * mult]

        altura_calc = max(height, len(categorias) * 30 + 100)
        fig = go.Figure(trace)
        fig.update_layout(
            **layout_defaults,
            height=altura_calc,
            margin={"t": 20, "b": 50, "l": margem_esq, "r": margem_dir},
            xaxis={"title": "Quantidade", "range": x_range,
                   "gridcolor": theme.BORDER, "automargin": True},
            yaxis={"automargin": True, "tickfont": {"size": 11}, "ticksuffix": "  "},
            bargap=0.3,
        )
    else:
        trace = go.Bar(
            x=categorias, y=quantidades,
            text=percentuais, textposition="outside",
            marker_color=bar_color,
            hovertemplate="<b>%{x}</b><br>Quantidade: %{y}<br>%{text}<extra></extra>",
        )
        fig = go.Figure(trace)
        fig.update_layout(
            **layout_defaults,
            height=height,
            margin={"t": 20, "b": 80, "l": 60, "r": 40},
            yaxis={"title": "Quantidade", "range": [0, max(quantidades) * 1.25],
                   "gridcolor": theme.BORDER},
            xaxis={"automargin": True, "tickangle": -20, "tickfont": {"size": 11}},
        )

    return fig


def histogram(valores: list[float], titulo: str, height: int = 420) -> go.Figure:
    """Histograma com linhas de média e mediana."""
    if not valores:
        return _empty_fig(titulo)

    media = sum(valores) / len(valores)
    s = sorted(valores)
    n = len(s)
    mediana = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    fig = go.Figure(
        go.Histogram(x=valores, nbinsx=20, marker_color=theme.ACCENT, opacity=0.85)
    )

    # Posicionar labels: o MAIOR valor à direita (xanchor=left), o MENOR à esquerda
    # (xanchor=right). Assim as labels se afastam mesmo quando os valores estão
    # próximos, evitando sobreposição.
    if media >= mediana:
        anchor_media, anchor_mediana = "left", "right"
    else:
        anchor_media, anchor_mediana = "right", "left"

    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=height,
        margin={"t": 20, "b": 50, "l": 60, "r": 40},
        shapes=[
            {"type": "line", "x0": media, "x1": media, "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": theme.DANGER, "width": 2, "dash": "dash"}},
            {"type": "line", "x0": mediana, "x1": mediana, "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": theme.PRIMARY, "width": 2, "dash": "dash"}},
        ],
        annotations=[
            {"x": media, "y": 1, "yref": "paper", "text": f" Média: {media:.1f} ",
             "showarrow": False, "xanchor": anchor_media, "yanchor": "top",
             "font": {"color": theme.DANGER, "size": 12}},
            {"x": mediana, "y": 1, "yref": "paper", "text": f" Mediana: {mediana:.1f} ",
             "showarrow": False, "xanchor": anchor_mediana, "yanchor": "top",
             "font": {"color": theme.PRIMARY, "size": 12}},
        ],
    )
    return fig


def line_regioes(pontos: list[dict], titulo: str = "Distribuição Regional por Momento") -> go.Figure:
    """Linha multi-série (uma por região) ao longo de 4 momentos."""
    if not pontos:
        return _empty_fig(titulo)

    por_regiao: dict[str, dict[str, int]] = {}
    for p in pontos:
        por_regiao.setdefault(p["regiao"], {})[p["momento"]] = p["quantidade"]

    momentos_ordem = ["Nascimento", "Graduação", "CRM", "Vaga"]
    fig = go.Figure()
    for i, (regiao, valores) in enumerate(sorted(por_regiao.items())):
        fig.add_trace(go.Scatter(
            x=momentos_ordem,
            y=[valores.get(m, 0) for m in momentos_ordem],
            mode="lines+markers",
            name=regiao,
            line={"color": theme.CATEGORICAL[i % len(theme.CATEGORICAL)], "width": 2.5},
            marker={"size": 8},
        ))
    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=500,
        margin={"t": 20, "b": 50, "l": 60, "r": 40},
        xaxis={"title": "Momento"},
        yaxis={"title": "Quantidade"},
    )
    return fig


def sentiment_bar(distribuicao: dict[str, int], titulo: str = "Análise de Sentimentos") -> go.Figure:
    """Bar chart de sentimentos com cores do tema."""
    if not distribuicao:
        return _empty_fig(titulo)

    ordem = ["Positivo", "Neutro", "Negativo"]
    chaves = [k for k in ordem if k in distribuicao] + [k for k in distribuicao if k not in ordem]
    valores = [distribuicao[k] for k in chaves]
    cores = [theme.SENTIMENT.get(k, theme.TEXT_MUTED) for k in chaves]

    fig = go.Figure(go.Bar(
        x=chaves, y=valores, marker_color=cores,
        text=valores, textposition="outside",
        hovertemplate="<b>%{x}</b><br>Quantidade: %{y}<extra></extra>",
    ))
    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=380,
        margin={"t": 20, "b": 50, "l": 50, "r": 40},
        showlegend=False,
        yaxis={"range": [0, max(valores) * 1.25 if valores else 1]},
    )
    return fig


def apropriacao_bar(dados: dict[str, int]) -> go.Figure:
    """Bar chart para tema de apropriação. A/E/N reclassificados pra rótulos descritivos.

    Cores semânticas: verde p/ Maior (apropriação positiva), vermelho p/ Menor
    (apropriação negativa), amarelo p/ Não Avaliado.
    """
    mapping = {"A": "Maior (A)", "E": "Menor (E)", "N": "Não Avaliado (N)"}
    color_map = {
        "Maior (A)": theme.SUCCESS,
        "Menor (E)": theme.DANGER,
        "Não Avaliado (N)": theme.WARNING,
    }
    # Pré-ordena por valor desc pra alinhar com bar_chart (sort_by_value=False)
    items = sorted(
        ((mapping.get(k, k), v) for k, v in dados.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    cores = [color_map.get(label, theme.PRIMARY) for label, _ in items]
    return bar_chart(items, titulo="", color=cores, sort_by_value=False)


def choropleth_brasil(
    valores_por_estado: dict[str, int],
    titulo: str,
    geojson: dict,
) -> go.Figure:
    """Mapa coroplético dos estados brasileiros."""
    locations = []
    z_values = []
    for feat in geojson.get("features", []):
        nome = feat.get("properties", {}).get("name")
        if nome:
            locations.append(nome)
            z_values.append(valores_por_estado.get(nome, 0))

    if not locations or sum(z_values) == 0:
        return _empty_fig(titulo)

    colorscale = [
        [0.0, "#E0E0E0"],
        [0.000001, "#dbe9f6"],
        [1.0, theme.ACCENT_DARK],
    ]

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=locations,
        z=z_values,
        featureidkey="properties.name",
        colorscale=colorscale,
        showscale=True,
        marker={"line": {"color": "rgba(0,0,0,0.3)", "width": 0.5}},
    ))
    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=600,
        margin={"l": 0, "r": 0, "t": 20, "b": 0},
        geo={"fitbounds": "locations", "visible": False, "bgcolor": theme.SURFACE},
    )
    return fig


# ----------------------------------------------------------------------
# Adicionais para a aba Logbook
# ----------------------------------------------------------------------
def line_chart(
    pontos: list[tuple[str, float]],
    titulo: str = "",
    y_title: str = "",
    y_range: tuple[float, float] | None = None,
    fill: bool = False,
    height: int = 360,
) -> go.Figure:
    """Linha simples com pontos. Espera lista de (label, valor)."""
    if not pontos:
        return _empty_fig(titulo)

    x_vals = [p[0] for p in pontos]
    y_vals = [p[1] for p in pontos]

    trace = go.Scatter(
        x=x_vals, y=y_vals,
        mode="lines+markers",
        line={"color": theme.ACCENT, "width": 2.5, "shape": "spline"},
        marker={"size": 6, "color": theme.ACCENT},
        fill="tozeroy" if fill else None,
        fillcolor="rgba(52, 152, 219, 0.12)" if fill else None,
    )
    fig = go.Figure(trace)
    layout = dict(
        **theme.plotly_layout_defaults(),
        height=height,
        margin={"t": 20, "b": 50, "l": 60, "r": 40},
        xaxis={"automargin": True, "tickangle": -20},
        yaxis={"title": y_title, "gridcolor": theme.BORDER, "rangemode": "tozero"},
        showlegend=False,
    )
    if y_range:
        layout["yaxis"]["range"] = list(y_range)
    fig.update_layout(**layout)
    return fig


def doughnut(items: list[tuple[str, int]], titulo: str = "", height: int = 320) -> go.Figure:
    """Doughnut chart com paleta sóbria."""
    items = [(k, v) for k, v in items if v > 0]
    if not items:
        return _empty_fig(titulo)
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    cores = [theme.CATEGORICAL[i % len(theme.CATEGORICAL)] for i in range(len(labels))]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5,
        marker={"colors": cores, "line": {"color": theme.SURFACE, "width": 2}},
        textposition="outside",
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=height,
        margin={"t": 20, "b": 20, "l": 20, "r": 20},
        showlegend=True,
        legend={"orientation": "h", "y": -0.1, "x": 0.5, "xanchor": "center"},
    )
    return fig


def dual_axis_bar(
    categorias: list[str],
    series: list[dict],
    titulo: str = "",
    height: int = 440,
    hover_texts: list[str] | None = None,
) -> go.Figure:
    """Bar chart com dois eixos Y. `series` é lista de dicts:
        {name, values, axis ('y' ou 'y2'), color}

    `hover_texts` (opcional): lista de string HTML por categoria — substitui o
    cabeçalho `<b>%{x}</b>` do hover. Útil pra mostrar nome completo + cidade/UF
    no lugar da sigla.
    """
    if not categorias or not series:
        return _empty_fig(titulo)

    fig = go.Figure()
    for s in series:
        if hover_texts:
            fig.add_trace(go.Bar(
                x=categorias,
                y=s["values"],
                name=s["name"],
                marker_color=s.get("color", theme.ACCENT),
                yaxis=s.get("axis", "y"),
                customdata=hover_texts,
                hovertemplate=f"%{{customdata}}<br>{s['name']}: %{{y:.2f}}<extra></extra>",
            ))
        else:
            fig.add_trace(go.Bar(
                x=categorias,
                y=s["values"],
                name=s["name"],
                marker_color=s.get("color", theme.ACCENT),
                yaxis=s.get("axis", "y"),
                hovertemplate=f"<b>%{{x}}</b><br>{s['name']}: %{{y:.2f}}<extra></extra>",
            ))

    fig.update_layout(
        **theme.plotly_layout_defaults(),
        height=height,
        margin={"t": 40, "b": 80, "l": 60, "r": 60},
        xaxis={"automargin": True, "tickangle": -30, "tickfont": {"size": 10}},
        yaxis={"title": "Volume de Procedimentos", "gridcolor": theme.BORDER, "side": "left"},
        yaxis2={
            "title": "Médias (1–5)", "overlaying": "y", "side": "right",
            "range": [0, 5], "showgrid": False,
        },
        barmode="group",
        legend={"orientation": "h", "y": 1.12, "x": 0.5, "xanchor": "center"},
    )
    return fig
