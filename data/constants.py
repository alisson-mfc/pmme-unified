"""Constantes geográficas e mapeamentos reutilizados em várias páginas/agregações."""

ESTADOS_REGIOES = {
    "Acre": "Norte", "Amapá": "Norte", "Amazonas": "Norte", "Pará": "Norte",
    "Rondônia": "Norte", "Roraima": "Norte", "Tocantins": "Norte",
    "Alagoas": "Nordeste", "Bahia": "Nordeste", "Ceará": "Nordeste",
    "Maranhão": "Nordeste", "Paraíba": "Nordeste", "Pernambuco": "Nordeste",
    "Piauí": "Nordeste", "Rio Grande do Norte": "Nordeste", "Sergipe": "Nordeste",
    "Espírito Santo": "Sudeste", "Minas Gerais": "Sudeste",
    "Rio de Janeiro": "Sudeste", "São Paulo": "Sudeste",
    "Paraná": "Sul", "Rio Grande do Sul": "Sul", "Santa Catarina": "Sul",
    "Distrito Federal": "Centro-Oeste", "Goiás": "Centro-Oeste",
    "Mato Grosso": "Centro-Oeste", "Mato Grosso do Sul": "Centro-Oeste",
}

SIGLAS_ESTADOS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}

ESTADOS_SIGLAS = {v: k for k, v in SIGLAS_ESTADOS.items()}

# Códigos IBGE de cada estado (usado pra carregar geojson de municípios)
SIGLAS_IBGE = {
    "AC": "12", "AM": "13", "AP": "16", "PA": "15", "RO": "11", "RR": "14", "TO": "17",
    "AL": "27", "BA": "29", "CE": "23", "MA": "21", "PB": "25", "PE": "26", "PI": "22",
    "RN": "24", "SE": "28", "ES": "32", "MG": "31", "RJ": "33", "SP": "35", "PR": "41",
    "RS": "43", "SC": "42", "DF": "53", "GO": "52", "MT": "51", "MS": "50",
}

GEOJSON_BRASIL_ESTADOS = (
    "https://raw.githubusercontent.com/codeforamerica/click_that_hood/"
    "master/public/data/brazil-states.geojson"
)


def extrair_uf_de_municipio(municipio: str | None) -> str | None:
    """Extrai a sigla UF do formato 'CIDADE - UF'."""
    if not municipio:
        return None
    s = str(municipio).rstrip()
    if len(s) >= 4 and s[-3] == " " and s[-4] == "-":
        sigla = s[-2:]
        if sigla.isupper() and sigla.isalpha():
            return sigla
    # Fallback regex-free: procura " - XX" no final
    if " - " in s:
        tail = s.rsplit(" - ", 1)[1].strip()
        if len(tail) == 2 and tail.isalpha() and tail.isupper():
            return tail
    return None
