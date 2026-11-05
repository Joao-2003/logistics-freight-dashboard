"""Configuração do dashboard de frete: credenciais, caminhos e tabelas fixas.

As credenciais ficam em .streamlit/secrets.toml (veja secrets.toml.example), fora do código.
Variáveis de ambiente com o mesmo nome têm prioridade.

Sem credenciais (ou rodando no navegador com stlite), o painel entra sozinho no modo de
demonstração e lê os arquivos fictícios da pasta demo/.
"""
import os
import sys
import tomllib

AQUI = os.path.dirname(os.path.abspath(__file__))

CHAVES = ["PIPEFY_TOKEN", "PIPE_SOLICITACOES", "PIPE_COTACOES", "SAP_HOST",
          "SAP_FAT_USER", "SAP_FAT_PASS", "SAP_FIN_USER", "SAP_FIN_PASS",
          "SAP_FRETE_USER", "SAP_FRETE_PASS"]


def _segredos():
    caminho = os.path.join(AQUI, ".streamlit", "secrets.toml")
    s = {}
    if os.path.exists(caminho):
        with open(caminho, "rb") as fh:
            s = tomllib.load(fh)
    for k in CHAVES:
        if os.environ.get(k):
            s[k] = os.environ[k]
    s.setdefault("SAP_HOST", "https://myXXXXXX-api.s4hana.cloud.sap")
    return s


SEG = _segredos()

# Modo de demonstração: lê CSVs e planilhas locais em vez das APIs.
# Liga sozinho no navegador (Pyodide) ou quando não há token do Pipefy configurado.
NO_NAVEGADOR = sys.platform == "emscripten"
DEMO_DIR = os.environ.get("FRETE_DEMO_DIR") or (
    os.path.join(AQUI, "demo") if NO_NAVEGADOR or not SEG.get("PIPEFY_TOKEN") else "")

# Pasta de dados (cache de distâncias e status da rodada diária)
DIR_DADOS = os.environ.get("FRETE_DADOS") or (DEMO_DIR if DEMO_DIR else os.path.join(AQUI, "dados"))
CACHE_DISTANCIAS = os.path.join(DIR_DADOS, "distancias_cache.xlsx")

# Quem entra no Total Gasto com Frete: a lista real fica fora do repositório
ARQ_FORNECEDORES = os.path.join(AQUI, "fornecedores_frete.csv")
if not os.path.exists(ARQ_FORNECEDORES):
    ARQ_FORNECEDORES = os.path.join(AQUI, "fornecedores_frete_exemplo.csv")

DATA_INICIAL_PADRAO = (2025, 6, 1)

# Unidades da empresa com coordenadas fixas (o motor não precisa geocodificá-las).
# Valores de exemplo: troque pelos nomes usados no Pipefy.
UNIDADE_MATRIZ = "MATRIZ"
UNIDADES = {
    "MATRIZ": ("Anápolis", "GO", -16.3281, -48.9534),
    "FILIAL SP": ("São Paulo", "SP", -23.5505, -46.6333),
    "FILIAL CURITIBA": ("Curitiba", "PR", -25.4284, -49.2733),
    "FILIAL CURITBA": ("Curitiba", "PR", -25.4284, -49.2733),  # grafia errada que aparece nos cards
    "CD MARINGÁ": ("Maringá", "PR", -23.4205, -51.9333),
}

FROTAS_PROPRIAS = {"CAMINHONETE INTERNA", "CAMINHÃO INTERNO", "CAMINHAO INTERNO"}

# Agrupa nomes digitados de formas diferentes no Pipefy e na nota (exibição).
# Nomes fictícios: na empresa a lista tem as transportadoras reais.
PADROES_TRANSPORTADORAS = {
    "RODOVIA EXPRESS": ["RODOVIA EXP"], "TRANSLESTE": ["TRANSLESTE", "TRANS LESTE"],
    "ALFA SUL": ["ALFA SUL"], "CERRADO CARGAS": ["CERRADO"], "SERRA AZUL": ["SERRA AZUL"],
    "NORTE RÁPIDO": ["NORTE RAPIDO", "NORTE RÁPIDO"], "PAMPA LOG": ["PAMPA"], "VALE LOG": ["VALE LOG"],
    "ROTA CENTRAL": ["ROTA CENTRAL"], "ECO ENTREGAS": ["ECO ENTREGAS"], "CORREIOS": ["CORREIOS"],
    "GLOBAL EXPRESS": ["GLOBAL EXPRESS"], "AUTÔNOMO A": ["AUTONOMO A", "AUTÔNOMO A"],
    "AUTÔNOMO B": ["AUTONOMO B", "AUTÔNOMO B"], "AUTÔNOMO C": ["AUTONOMO C", "AUTÔNOMO C"],
    "FROTA PRÓPRIA": ["EMPRESA MATRIZ", "FROTA PROPRIA", "FROTA PRÓPRIA"],
}

UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}
