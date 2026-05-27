"""Paleta de cores, tipografia e tokens de design do PMM-e Dashboard.

Paleta sóbria e profissional: azul-petróleo como cor primária (já presente no header
de matrículas), azul acento para CTAs/seleções, neutros para superfícies e texto.
Sem gradientes.
"""

# ----------------------------------------------------------------------
# CORES
# ----------------------------------------------------------------------
PRIMARY = "#2c3e50"      # azul-petróleo (navbar, títulos)
PRIMARY_DARK = "#1f2d3d"
ACCENT = "#3498db"       # azul (tabs ativas, links, seleções)
ACCENT_DARK = "#217dbb"

BG = "#f7f8fa"           # fundo da aplicação
SURFACE = "#ffffff"      # cards, painéis
BORDER = "#e5e7eb"

TEXT = "#1f2937"
TEXT_MUTED = "#6b7280"

SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#3b82f6"

# Sequência categórica para Plotly (substitui o padrão D3 mais saturado)
CATEGORICAL = [
    "#2c3e50",
    "#3498db",
    "#16a085",
    "#f39c12",
    "#8e44ad",
    "#c0392b",
    "#34495e",
    "#27ae60",
    "#d35400",
    "#7f8c8d",
]

# Sequência divergente para sentimentos (Positivo / Neutro / Negativo)
SENTIMENT = {
    "Positivo": "#10b981",
    "Neutro": "#f59e0b",
    "Negativo": "#ef4444",
}

# ----------------------------------------------------------------------
# TIPOGRAFIA E ESPAÇAMENTO
# ----------------------------------------------------------------------
FONT_FAMILY = (
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)


# ----------------------------------------------------------------------
# PLOTLY TEMPLATE
# ----------------------------------------------------------------------
def plotly_layout_defaults() -> dict:
    """Defaults universais aplicáveis a qualquer figura Plotly do app.

    NÃO inclui margin / xaxis / yaxis — esses variam por tipo de gráfico e cada
    fábrica os define explicitamente. Inclua aqui apenas o que é realmente comum.
    """
    return {
        "font": {"family": FONT_FAMILY, "color": TEXT, "size": 13},
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
        "colorway": CATEGORICAL,
    }
