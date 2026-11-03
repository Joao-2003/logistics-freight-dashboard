#!/usr/bin/env python
# coding: utf-8

# ===========================================================
# 🔵 BLOCO 1 — CONFIGURAÇÃO DE DASHBOARD E CSS
# ===========================================================
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import io
import unicodedata
import re
import os
import requests
from requests.auth import HTTPBasicAuth
import ast
from urllib.parse import urljoin  
import time 

st.set_page_config(page_title="Dashboard de Fretes", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        /* Reduz os espaços em branco nativos do Streamlit */
        .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 98%; }
        h1 { margin-bottom: 0.2rem; font-size: 1.8rem; }
        h2, h3 { margin-top: 0.2rem; margin-bottom: 0.2rem; font-size: 1.2rem; }
        hr { margin-top: 0.5rem; margin-bottom: 0.5rem; }
        
        /* Ajusta as abas para formato mais profissional */
        .stTabs [data-baseweb="tab-list"] { gap: 4px; }
        .stTabs [data-baseweb="tab"] { height: 35px; font-size: 14px; }
        
        /* Melhora o tamanho das métricas numéricas */
        div[data-testid="stMetricValue"] { font-size: 1.6rem; }
        div[data-testid="stMetricLabel"] { font-size: 0.9rem; }
        
        /* Reduz a largura da sidebar em ~30% apenas quando expandida */
        section[data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 240px !important;
            max-width: 240px !important;
        }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------
# CREDENCIAIS PIPEFY, SAP E CAMINHOS LOCAIS
# -----------------------------------------------------------
PIPEFY_TOKEN      = os.getenv("PIPEFY_TOKEN", "")
PIPE_SOLICITACOES = os.getenv("PIPE_SOLICITACOES", "")
PIPE_COTACOES     = os.getenv("PIPE_COTACOES", "")

BASE_SAP_URL = os.getenv("SAP_BASE_URL", "https://myXXXXXX-api.s4hana.cloud.sap") + "/sap/opu/odata4/sap/zb_relatorio_faturamento/srvd/sap/zd_relatorio_faturamento/0001/ZC_REL_FATURAMENTO"
PARAMETROS_ODATA = "?sap-language=PT&$select=NumeroOV,NumeroRemessa,MarcaVolume,PesoBrutoTotalNF,QtdVolumesTransportados,BR_NFSituationCode,NomeTipoDocumento,BR_NFIsCanceled&$filter=BR_NFIsCanceled eq false and BR_NFSituationCode eq '00' and NomeTipoDocumento eq 'Fatura'"

SAP_URL = BASE_SAP_URL + PARAMETROS_ODATA
SAP_USER = os.getenv("SAP_USER", "")
SAP_PASS = os.getenv("SAP_PASS", "")

# API SAP FINANCEIRO (GASTO LÍQUIDO)
SAP_FIN_URL = os.getenv("SAP_BASE_URL", "https://myXXXXXX-api.s4hana.cloud.sap") + "/sap/opu/odata/sap/YY1_ITENS_FORNECEDOR_CDS/YY1_ITENS_FORNECEDOR?$format=json"
SAP_FIN_USER = os.getenv("SAP_FIN_USER", "")
SAP_FIN_PASS = os.getenv("SAP_FIN_PASS", "")

DIRETORIO_DADOS          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
CAMINHO_CACHE_DISTANCIAS = os.path.join(DIRETORIO_DADOS, "distancias_cache.xlsx")

# -----------------------------------------------------------
# CONFIGURAÇÕES DO MOTOR DE DISTÂNCIAS (NOVO)
# -----------------------------------------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
HEADERS_GEO = {"User-Agent": "logistica-dashboard/3.0 (seu-email@exemplo.com)"}

UNIDADES = {
    "Empresa A MATRIZ": ("Anápolis", "GO"),
    "Empresa A SP": ("São Paulo", "SP"),
    "CAMPO MAGRO": ("Campo Magro", "PR"),
    "Empresa A CURITIBA": ("Curitiba", "PR"),
    "MARINGÁ": ("Maringá", "PR"),
}

CACHE_GEO = {}
CACHE_ROTA = {}
HISTORICO_LINHAS = {}

# -----------------------------------------------------------
# NORMALIZAÇÃO DE TRANSPORTADORAS E NÚMEROS
# -----------------------------------------------------------
PADROES_TRANSPORTADORAS = {
    # Exemplo: nome padronizado -> variações digitadas no Pipefy
    "SÃO MIGUEL": ["SAO MIGUEL", "SÃO MIGUEL"],
    "RODONAVES": ["RODONAVES"],
    "BRASPRESS": ["BRASPRESS"],
    "CORREIOS": ["CORREIOS"],
    "DHL": ["DHL"],
    "FEDEX": ["FEDERAL EXPRESS", "FEDEX"],
    "FROTA PRÓPRIA": ["Empresa A MATRIZ", "Empresa A INDUSTRIA"],
}

def normalizar_transportadora(nome):
    if pd.isna(nome) or str(nome).strip() == "": return "Vazio"
    nome_upper = str(nome).upper()
    
    # O dicionário agora dá nome individual limpo para todo mundo!
    for nome_padrao, variacoes in PADROES_TRANSPORTADORAS.items():
        if any(v in nome_upper for v in variacoes): return nome_padrao
        
    return str(nome).strip()

def encurtar_nome_cliente_fornecedor(nome):
    if pd.isna(nome) or str(nome).strip() == "": return "Não Informado"
    nome_str = str(nome).strip()
    palavras = nome_str.split()
    
    # Se tiver mais de 7 palavras, arranca as 3 últimas
    if len(palavras) > 6:
        return " ".join(palavras[:-3])
        
    return nome_str

def tratar_numero(valor):
    if pd.isna(valor): return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    v = str(valor).strip()
    if v == "": return 0.0
    v = re.sub(r'[^\d\.,\-]', '', v)
    if "." in v and "," in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try: return float(v)
    except: return 0.0

def tratar_codigo_cotacao(cod):
    if pd.isna(cod): return ""
    cod = str(cod).replace(" ", "").replace("\n", "").replace("\t", "").replace("\xa0", "").replace(",", "")
    if cod.endswith(".0"): cod = cod[:-2]
    if cod.endswith("."): cod = cod[:-1]
    try:
        if "e" in cod.lower(): cod = str(int(float(cod)))
    except: pass
    return cod.strip()

# ===========================================================
# 🔵 BLOCO 2 — INTEGRAÇÃO APIS E MOTOR DE DISTÂNCIAS
# ===========================================================
def limpar_valor_pipefy(val):
    if isinstance(val, list): return ", ".join([str(i) for i in val])
    if isinstance(val, str) and val.startswith('[') and val.endswith(']'):
        try: 
            parsed = ast.literal_eval(val)
            if isinstance(parsed, list): return ", ".join([str(i) for i in parsed])
        except: pass
    return val

def padronizar_colunas(df, tipo):
    if df.empty: return df
    rename_dict = {}
    for c in df.columns:
        cl = str(c).lower().strip().replace(":", "").replace("?", "")
        if tipo == "solicitacao":
            if cl == "localidade (embarque)": rename_dict[c] = "Localidade (Embarque):"
            elif cl == "uf (embarque)": rename_dict[c] = "UF (Embarque):"
            elif cl == "unidade de embarque": rename_dict[c] = "Unidade de embarque:"
            elif cl == "localidade (desembarque)": rename_dict[c] = "Localidade (Desembarque):"
            elif cl == "uf (desembarque)": rename_dict[c] = "UF (Desembarque):"
            elif cl == "unidade de desembarque": rename_dict[c] = "Unidade de desembarque:"
            elif cl == "qual a cotação selecionada": rename_dict[c] = "Qual a cotação selecionada?"
            elif cl == "tipo de solicitação": rename_dict[c] = "Tipo de solicitação:"
            elif cl == "valor da remessa": rename_dict[c] = "Valor da Remessa:"
            elif cl == "pipe pai": rename_dict[c] = "Pipe Pai:"
            elif cl == "qual a frota utilizada": rename_dict[c] = "Qual a frota utilizada?"
            elif cl == "centro de custo": rename_dict[c] = "Centro de custo:"
            elif cl == "cliente": rename_dict[c] = "Cliente:"
            elif cl == "existe pedido no sap": rename_dict[c] = "Existe pedido no SAP?"
            elif cl == "n° pedido" or cl == "numero do pedido": rename_dict[c] = "N° Pedido:"
            elif cl == "informe aqui as cotações realizadas para este frete": rename_dict[c] = "Informe aqui as cotações realizadas para este frete:"
            elif cl == "valor cte": rename_dict[c] = "Valor CTE:"
            elif cl == "modalidade": rename_dict[c] = "Modalidade"
            elif cl == "responsável pelo frete": rename_dict[c] = "Responsável pelo frete:"
            elif cl == "tipo de local de entrega": rename_dict[c] = "Tipo de local de entrega?"
            elif cl == "fornecedor": rename_dict[c] = "Fornecedor:"
            elif cl == "nome da transportadora": rename_dict[c] = "Nome da transportadora"
        elif tipo == "cotacao":
            if cl == "nº da cotação" or cl == "n da cotacao": rename_dict[c] = "Nº da cotação"
            elif cl == "valor": rename_dict[c] = "Valor:"
            elif cl == "transportadora": rename_dict[c] = "Transportadora:"
            elif "redespacho" in cl: rename_dict[c] = "Necessário redespacho?"
        elif tipo == "centro_custo":
            if cl == "título" or cl == "centro de custo": rename_dict[c] = "Centro de Custo"
            elif cl == "código": rename_dict[c] = "Código"
            elif cl == "status": rename_dict[c] = "Status"

    df = df.rename(columns=rename_dict)
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    if tipo == "cotacao":
        if "Nº da cotação" not in df.columns and "Título" in df.columns: df["Nº da cotação"] = df["Título"]
        if "Nº da cotação" not in df.columns: df["Nº da cotação"] = ""
        if "Valor:" not in df.columns: df["Valor:"] = 0.0
        if "Necessário redespacho?" not in df.columns: df["Necessário redespacho?"] = "Vazio"
        if "Transportadora:" not in df.columns: df["Transportadora:"] = "Vazio"
    elif tipo == "centro_custo":
        if "Centro de Custo" not in df.columns and "Título" in df.columns: df["Centro de Custo"] = df["Título"]
    elif tipo == "solicitacao":
        if "Valor CTE:" not in df.columns: df["Valor CTE:"] = 0.0
        if "Valor da Remessa:" not in df.columns: df["Valor da Remessa:"] = 0.0
    return df

def extrair_pipefy_paginado(query_base, node_type, id_alvo, token):
    url = "https://api.pipefy.com/graphql"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    linhas, has_next_page, after = [], True, None
    
    while has_next_page:
        after_str = f', after: "{after}"' if after else ""
        query = query_base.replace("{AFTER}", after_str).replace("{ID}", str(id_alvo))
        response = requests.post(url, json={"query": query}, headers=headers)
        if response.status_code != 200: break
        dados = response.json()
        if 'errors' in dados: break
            
        secao = dados['data'][node_type]
        for edge in secao['edges']:
            node = edge['node']
            linha = {'ID_Pipefy': node['id'], 'Título': node.get('title', '')}
            if 'created_at' in node: linha['Criado em'] = node['created_at']
            if 'current_phase' in node and node['current_phase']: linha['Fase atual'] = node['current_phase']['name']
            if 'createdBy' in node and node['createdBy']: linha['Criador'] = node['createdBy']['name']
            if 'late' in node: linha['Vencido'] = "Sim" if node['late'] else "Não"
            
            if 'phases_history' in node and node['phases_history']:
                for ph in node['phases_history']:
                    if ph and ph.get('phase') and ph.get('duration') is not None:
                        linha[f"Tempo na fase {ph['phase']['name']} (Dias)"] = ph['duration'] / 86400.0
            
            for field in node.get('fields', node.get('record_fields', [])):
                linha[field['name']] = limpar_valor_pipefy(field['value'])
            linhas.append(linha)
            
        page_info = secao['pageInfo']
        has_next_page = page_info['hasNextPage']
        after = page_info['endCursor']
    return pd.DataFrame(linhas)

@st.cache_data(ttl="1d")
def carregar_dados_pipefy():
    query_solic = """{ allCards(pipeId: {ID}, first: 50 {AFTER}) { pageInfo { hasNextPage endCursor } edges { node { id title created_at late current_phase { name } createdBy { name } phases_history { phase { name } duration } fields { name value } } } } }"""
    df_solicitacoes = extrair_pipefy_paginado(query_solic, "allCards", PIPE_SOLICITACOES, PIPEFY_TOKEN)
    df_solicitacoes = padronizar_colunas(df_solicitacoes, "solicitacao")

    query_cot = """{ table_records(table_id: "{ID}", first: 50 {AFTER}) { pageInfo { hasNextPage endCursor } edges { node { id title record_fields { name value } } } } }"""
    df_cotacoes = extrair_pipefy_paginado(query_cot, "table_records", PIPE_COTACOES, PIPEFY_TOKEN)
    df_cotacoes = padronizar_colunas(df_cotacoes, "cotacao")

    if not df_solicitacoes.empty:
        if "Criado em" in df_solicitacoes.columns:
            df_solicitacoes["Criado em"] = pd.to_datetime(df_solicitacoes["Criado em"], errors="coerce").dt.tz_localize(None)
        if "Fase atual" in df_solicitacoes.columns:
            df_solicitacoes = df_solicitacoes[df_solicitacoes["Fase atual"].astype(str).str.upper() != "DESCONTINUADO"]
        for col in ["Valor da Remessa:", "Valor Fatura", "Valor CTE:"]:
            if col in df_solicitacoes.columns: df_solicitacoes[col] = df_solicitacoes[col].apply(tratar_numero)
            
    return df_solicitacoes, df_cotacoes

@st.cache_data(ttl="1d")
def carregar_dados_sap():
    auth = HTTPBasicAuth(SAP_USER, SAP_PASS)
    linhas = []
    url = SAP_URL
    try:
        while url:
            response = requests.get(url, auth=auth)
            if response.status_code != 200: break
            dados = response.json()
            if 'value' in dados: linhas.extend(dados['value'])
            next_link = dados.get('@odata.nextLink')
            url = urljoin(BASE_SAP_URL, next_link) if next_link else None
        return pd.DataFrame(linhas)
    except:
        return pd.DataFrame()

@st.cache_data(ttl="1d")
def carregar_dados_sap_financeiro():
    auth = HTTPBasicAuth(SAP_FIN_USER, SAP_FIN_PASS)
    linhas = []
    url = SAP_FIN_URL
    try:
        while url:
            response = requests.get(url, auth=auth, timeout=30)
            if response.status_code != 200: break
            dados = response.json()
            if 'd' in dados:
                if 'results' in dados['d']: linhas.extend(dados['d']['results'])
                url = dados['d'].get('__next')
                if not url: break
            else: break
        df = pd.DataFrame(linhas)
        if not df.empty:
            df['AmountInCompanyCodeCurrency'] = pd.to_numeric(df['AmountInCompanyCodeCurrency'], errors='coerce')
        return df
    except:
        return pd.DataFrame()

# ===========================================================
# 🔵 FUNÇÕES DO MOTOR DE DISTÂNCIAS (ENCAPSULADAS)
# ===========================================================
def resolver_localizacao(row, tipo):
    if tipo == "origem":
        cidade, uf, unidade = row.get("Localidade (Embarque):"), row.get("UF (Embarque):"), row.get("Unidade de embarque:")
        endereco, cep = row.get("Endereço de embarque:"), row.get("CEP de embarque:")
    else:
        cidade, uf, unidade = row.get("Localidade (Desembarque):"), row.get("UF (Desembarque):"), row.get("Unidade de desembarque:")
        endereco, cep = row.get("Endereço de desembarque:"), row.get("CEP de desembarque:")

    if pd.notna(cidade) and pd.notna(uf): return str(cidade).strip(), str(uf).strip(), "CIDADE"
    if pd.notna(unidade) and unidade in UNIDADES: return UNIDADES[unidade][0], UNIDADES[unidade][1], "UNIDADE"
    
    # NOVO PLANO C: Fallback para Endereço ou CEP
    if pd.notna(endereco) and str(endereco).strip() != "":
        return str(endereco).strip().replace("\n", ", "), "", "ENDERECO"
    if pd.notna(cep) and str(cep).strip() != "" and str(cep).strip() != "0.0":
        return str(cep).strip(), "", "CEP"
        
    return None, None, "SEM_INFO"

def geocodificar_cidade(cidade, uf):
    if not cidade: return None, None, "SEM_DADOS"
    
    chave_cache = f"{str(cidade).upper()}-{str(uf).upper()}"
    if chave_cache in CACHE_GEO: return CACHE_GEO[chave_cache][0], CACHE_GEO[chave_cache][1], "CACHE"

    try:
        q_param = f"{cidade}, {uf}, Brasil" if uf else f"{cidade}, Brasil"
        r = requests.get(NOMINATIM_URL, params={"q": q_param, "format": "json", "limit": 1}, headers=HEADERS_GEO, timeout=10)
        data = r.json()
        if not data:
            CACHE_GEO[chave_cache] = (None, None)
            time.sleep(1.2) # Intervalo para não dar ban
            return None, None, "NAO_ENCONTRADO"
        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        CACHE_GEO[chave_cache] = (lat, lon)
        time.sleep(1.2) # Intervalo para não dar ban
        return lat, lon, "OK"
    except Exception as e:
        CACHE_GEO[chave_cache] = (None, None) # Guarda a falha na sessão para não entrar em looping
        time.sleep(1.2) # Desacelera requisições em caso de instabilidade
        return None, None, f"ERRO_{e}"

def calcular_distancia_osrm(lat_o, lon_o, lat_d, lon_d):
    if None in [lat_o, lon_o, lat_d, lon_d]: return None
    chave_cache = f"{lat_o},{lon_o}_{lat_d},{lon_d}"
    if chave_cache in CACHE_ROTA: return CACHE_ROTA[chave_cache]
    try:
        r = requests.get(f"{OSRM_URL}/{lon_o},{lat_o};{lon_d},{lat_d}?overview=false", timeout=10)
        data = r.json()
        if data.get("code") != "Ok": return None
        km = round(data["routes"][0]["distance"] / 1000, 2)
        CACHE_ROTA[chave_cache] = km
        return km
    except: return None

def carregar_historico(arquivo_cache):
    if not os.path.exists(arquivo_cache): return
    df_cache = pd.read_excel(arquivo_cache)
    for _, row in df_cache.iterrows():
        km = row.get("KM_RODADO")
        if pd.notna(km):
            id_card = str(row.get("ID_Pipefy", "")).strip()
            if id_card and id_card != "nan":
                HISTORICO_LINHAS[id_card] = {
                    "LAT_O": row.get("LAT_O"), "LON_O": row.get("LON_O"),
                    "LAT_D": row.get("LAT_D"), "LON_D": row.get("LON_D"),
                    "KM_RODADO": km, "FONTE_O": row.get("FONTE_O"), "FONTE_D": row.get("FONTE_D")
                }
            c_o, uf_o, _ = resolver_localizacao(row, "origem")
            if c_o and pd.notna(row.get("LAT_O")):
                CACHE_GEO[f"{str(c_o).upper()}-{str(uf_o).upper()}"] = (row["LAT_O"], row["LON_O"])
            c_d, uf_d, _ = resolver_localizacao(row, "destino")
            if c_d and pd.notna(row.get("LAT_D")):
                CACHE_GEO[f"{str(c_d).upper()}-{str(uf_d).upper()}"] = (row["LAT_D"], row["LON_D"])
            if pd.notna(row.get("LAT_O")) and pd.notna(row.get("LAT_D")):
                CACHE_ROTA[f"{row['LAT_O']},{row['LON_O']}_{row['LAT_D']},{row['LON_D']}"] = km

@st.cache_data(ttl="1d")
def atualizar_motor_distancias(df_entrada):
    os.makedirs(os.path.dirname(CAMINHO_CACHE_DISTANCIAS), exist_ok=True)
    df = df_entrada.copy()
    
    carregar_historico(CAMINHO_CACHE_DISTANCIAS)
    
    for col in ["LAT_O", "LON_O", "LAT_D", "LON_D", "KM_RODADO", "FONTE_O", "FONTE_D"]:
        if col not in df.columns: df[col] = None

    for i, row in df.iterrows():
        id_card = str(row.get("ID_Pipefy", "")).strip()
        if id_card and id_card in HISTORICO_LINHAS:
            for k, v in HISTORICO_LINHAS[id_card].items():
                df.at[i, k] = v

    novos_salvamentos = 0
    for i, row in df.iterrows():
        if pd.notna(row.get("KM_RODADO")): continue

        cidade_o, uf_o, fonte_o = resolver_localizacao(row, "origem")
        lat_o, lon_o, st_o = geocodificar_cidade(cidade_o, uf_o)

        cidade_d, uf_d, fonte_d = resolver_localizacao(row, "destino")
        lat_d, lon_d, st_d = geocodificar_cidade(cidade_d, uf_d)

        km = calcular_distancia_osrm(lat_o, lon_o, lat_d, lon_d)

        if km:
            df.at[i, "LAT_O"], df.at[i, "LON_O"] = lat_o, lon_o
            df.at[i, "LAT_D"], df.at[i, "LON_D"] = lat_d, lon_d
            df.at[i, "KM_RODADO"] = km
            df.at[i, "FONTE_O"], df.at[i, "FONTE_D"] = fonte_o, fonte_d
            
            novos_salvamentos += 1
            if novos_salvamentos % 20 == 0:
                df.to_excel(CAMINHO_CACHE_DISTANCIAS, index=False)

    df.to_excel(CAMINHO_CACHE_DISTANCIAS, index=False)
    return True # Retorna True apenas para sinalizar sucesso pro cache

# ===========================================================
# 🔧 FUNÇÕES DE GRÁFICOS COMPACTOS
# ===========================================================
def gerar_top_n(df_local, coluna, titulo, top=7, cor="Blues"):
    if df_local.empty or coluna not in df_local.columns: return
    df_temp = df_local.copy()
    valores_invalidos = ["VAZIO", "NAN", "NONE", ""]
    df_temp = df_temp[~df_temp[coluna].astype(str).str.strip().str.upper().isin(valores_invalidos)]
    contagem = df_temp[coluna].value_counts().reset_index()
    contagem.columns = [coluna, "Quantidade"]
    if contagem.empty: return
    fig = px.bar(contagem.head(top), x="Quantidade", y=coluna, orientation="h", text="Quantidade", color="Quantidade", color_continuous_scale=cor, title=titulo)
    fig.update_layout(height=280, margin=dict(l=10, r=60, t=30, b=10), yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, xaxis_title=None, yaxis_title=None, title_font_size=14)
    fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)

def gerar_pizza(df_local, coluna, titulo):
    if df_local.empty or coluna not in df_local.columns: return
    df_temp = df_local.copy()
    valores_invalidos = ["VAZIO", "NAN", "NONE", ""]
    df_temp = df_temp[~df_temp[coluna].astype(str).str.strip().str.upper().isin(valores_invalidos)]
    contagem = df_temp[coluna].value_counts().reset_index()
    contagem.columns = [coluna, "Quantidade"]
    if contagem.empty: return
    fig = px.pie(contagem, names=coluna, values="Quantidade", title=titulo)
    fig.update_traces(textinfo="percent", hovertemplate="%{label}: %{value} reg. (%{percent})")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), title_font_size=14, legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================
# CABEÇALHO DO DASHBOARD
# ===========================================================
st.title("Dashboard de Logística e Fretes")

if "admin" in st.query_params:
    st.cache_data.clear()
    st.query_params.clear() # Apaga o rastro da URL
    st.rerun()

st.sidebar.markdown("---")

# ===========================================================
# PROCESSAMENTO PRINCIPAL DAS 3 APIs + MOTOR DISTÂNCIAS
# ===========================================================
with st.spinner("Buscando dados das APIs (Pipefy, SAP) e Atualizando Distâncias... Isso pode levar alguns minutos na primeira vez do dia."):
    df_principal, df_cot= carregar_dados_pipefy()
    df_sap = carregar_dados_sap()
    df_sap_fin = carregar_dados_sap_financeiro()
    
    # Executa o motor em background (será instantâneo se vier do cache)
    if not df_principal.empty:
        atualizar_motor_distancias(df_principal)

if not df_principal.empty:
    # Sidebar: Filtros
    st.sidebar.markdown("### 📅 Filtro de Data")
    
    # 1. Tratamento da coluna de data do SAP (mantido para o filtro funcionar depois)
    if not df_sap_fin.empty:
        if 'PostingDate' in df_sap_fin.columns:
            col_data = 'PostingDate'
        elif 'ClearingDate' in df_sap_fin.columns:
            col_data = 'ClearingDate'
        else:
            col_data = None
            
        if col_data:
            df_sap_fin['Data_Filtro'] = pd.to_datetime(
                df_sap_fin[col_data].astype(str).str.extract(r'(\d+)')[0], 
                unit='ms', errors='coerce'
            ).dt.normalize()
        else:
            df_sap_fin['Data_Filtro'] = pd.NaT

    # 2. Construção do Calendário
    if "Criado em" in df_principal.columns and not df_principal["Criado em"].isna().all():
        
        # --- DATA INICIAL HARDCODED ---
        data_min_geral = datetime(2025, 6, 1).date()
        
        # Garante que o fim do calendário pegue até o dia de hoje, independente do Pipefy
        data_max_pipe = df_principal["Criado em"].max().date()
        data_max_geral = max(data_max_pipe, datetime.now().date())
        
        data_inicial = st.sidebar.date_input("Início", data_min_geral, format="DD/MM/YYYY")
        data_final = st.sidebar.date_input("Fim", data_max_geral, format="DD/MM/YYYY")
        
        df_principal = df_principal[
            (df_principal["Criado em"] >= datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0)) & 
            (df_principal["Criado em"] <= datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59))
        ]
        
    st.sidebar.markdown("### 🚚 Redespacho")
    opcao_redespacho = st.sidebar.radio("", ["Considerar todos", "Somente Redespacho", "Excluir Redespacho"], label_visibility="collapsed")
    
    # Pre-processamento Global
    df_filtrado_global = df_principal.copy()
    
    if not df_cot.empty:
        if "Nº da cotação" in df_cot.columns:
            df_cot["Nº da cotação"] = df_cot["Nº da cotação"].astype(str).apply(tratar_codigo_cotacao)
        
        if "Qual a cotação selecionada?" in df_filtrado_global.columns:
            df_filtrado_global["Cotacao_Normalizada"] = df_filtrado_global["Qual a cotação selecionada?"].fillna("").astype(str).apply(tratar_codigo_cotacao)
        else:
            df_filtrado_global["Cotacao_Normalizada"] = ""
            
        if "Nº da cotação" in df_cot.columns and "Necessário redespacho?" in df_cot.columns:
            df_cot_lookup = df_cot[df_cot["Nº da cotação"] != ""].drop_duplicates(subset=["Nº da cotação"])
            df_filtrado_global = df_filtrado_global.merge(df_cot_lookup[["Nº da cotação", "Necessário redespacho?"]], how="left", left_on="Cotacao_Normalizada", right_on="Nº da cotação")
            
            def limpar_campo_redespacho(v):
                if pd.isna(v): return "Vazio"
                val_str = str(v).upper()
                if "SIM" in val_str: return "Somente Redespacho"
                return "Vazio"
                
            df_filtrado_global["Redespacho"] = df_filtrado_global["Necessário redespacho?"].apply(limpar_campo_redespacho)
            df_filtrado_global.drop(columns=["Nº da cotação", "Necessário redespacho?"], inplace=True, errors="ignore")
        else:
            df_filtrado_global["Redespacho"] = "Vazio"

        # Trazendo o KM direto da planilha local que acabou de ser atualizada (MUDANÇA PARA ID_PIPEFY)
        if os.path.exists(CAMINHO_CACHE_DISTANCIAS):
            df_km = pd.read_excel(CAMINHO_CACHE_DISTANCIAS)
            if "ID_Pipefy" in df_km.columns:
                df_km["ID_Pipefy_Str"] = df_km["ID_Pipefy"].astype(str).str.strip()
                df_filtrado_global["ID_Pipefy_Str"] = df_filtrado_global.get("ID_Pipefy", pd.Series()).astype(str).str.strip()
                df_km_lookup = df_km[df_km["ID_Pipefy_Str"] != ""].drop_duplicates(subset=["ID_Pipefy_Str"])
                df_filtrado_global = df_filtrado_global.merge(df_km_lookup[["ID_Pipefy_Str", "KM_RODADO"]], how="left", on="ID_Pipefy_Str")
            else:
                df_filtrado_global["KM_RODADO"] = None
        else:
            df_filtrado_global["KM_RODADO"] = None
    else:
        df_filtrado_global["Redespacho"], df_filtrado_global["KM_RODADO"] = "Vazio", None

    if opcao_redespacho == "Somente Redespacho": 
        df_filtrado_global = df_filtrado_global[df_filtrado_global["Redespacho"] == "Somente Redespacho"]
    elif opcao_redespacho == "Excluir Redespacho": 
        df_filtrado_global = df_filtrado_global[df_filtrado_global["Redespacho"] != "Somente Redespacho"]

    # ===========================================================
    # 🔵 ABAS DO DASHBOARD
    # ===========================================================
    aba_resumo, aba_vendas, aba_compras, aba_filial_fabrica, aba_mkt, aba_cotacoes, aba_peso_vol, aba_slas = st.tabs([
        " 📌 Resumo Geral ", "  💰 Vendas ", "  🛒 Compras ", "  📦 Filial & Fábrica ", "  🎯 Marketing ", "  📄 Cotações ", "  ⚖️ Peso/Vol ", "  ⏱️ SLAs "
    ])

    # -----------------------------------------------------------
    # 📌 RESUMO GERAL
    # -----------------------------------------------------------
    with aba_resumo:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Solicitações", len(df_filtrado_global))
        c2.metric("Criadores Únicos", df_filtrado_global.get("Criador", pd.Series()).nunique())
        c3.metric("Tipos de Solicitação", df_filtrado_global.get("Tipo de solicitação:", pd.Series()).nunique())
        
        # --- CÁLCULO DO TOTAL PAGO COM FRETE (SAP) ---
        total_pago_sap = 0.0
        df_sap_pago = pd.DataFrame() # Inicializa vazio

        if not df_sap_fin.empty and 'Data_Filtro' in df_sap_fin.columns:
            # Lista mestre atualizada sem UPS
            keywords_transp = list(PADROES_TRANSPORTADORAS.keys())  # transportadoras consideradas no gasto
            padrao = '|'.join(keywords_transp)
            
            if 'SupplierName' in df_sap_fin.columns and 'PostingKey' in df_sap_fin.columns:
                
                # --- A BLINDAGEM DEFINITIVA CONTRA DATAS ---
                # 1. Força a coluna inteira a ser Timestamp (corrige se tiver sobrado algum .date() lá na sidebar)
                df_sap_fin['Data_Filtro'] = pd.to_datetime(df_sap_fin['Data_Filtro'], errors='coerce')
                
                # 2. Converte os limites do calendário também para Timestamp
                filtro_inicio = pd.Timestamp(data_inicial)
                filtro_fim = pd.Timestamp(data_final)

                # 3. Agora o filtro compara Laranja com Laranja
                df_sap_pago = df_sap_fin[
                    (df_sap_fin['SupplierName'].astype(str).str.upper().str.contains(padrao, na=False)) &
                    (df_sap_fin['PostingKey'].astype(str).isin(['25'])) &
                    (df_sap_fin['Data_Filtro'].notna()) & 
                    (df_sap_fin['Data_Filtro'] >= filtro_inicio) & 
                    (df_sap_fin['Data_Filtro'] <= filtro_fim)
                ].copy()
                
                total_pago_sap = df_sap_pago['AmountInCompanyCodeCurrency'].sum()
                
        # --- EXIBIÇÃO INTELIGENTE DO KPI ---
        if opcao_redespacho == "Considerar todos":
            c4.metric("Total Gasto com Frete", f"R$ {total_pago_sap:,.2f}")
        else:
            c4.metric("Total Gasto com Frete", "N/A", help="O valor financeiro do SAP não pode ser segmentado pelo filtro de Redespacho.")
        # ------------------------------------------------

        if "Criado em" in df_filtrado_global.columns:
            df_tempo = df_filtrado_global.copy()
            df_tempo["Data"] = df_tempo["Criado em"].dt.date
            cont_tempo = df_tempo.groupby("Data").size().reset_index(name="Volume")
            if not cont_tempo.empty:
                fig_line = px.area(cont_tempo, x="Data", y="Volume", title="📈 Evolução de Solicitações por Dia")
                fig_line.update_layout(height=260, margin=dict(l=10, r=40, t=30, b=10), xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig_line, use_container_width=True)

        # --- ENCURTANDO O NOME DA FROTA ---
        if "Qual a frota utilizada?" in df_filtrado_global.columns:
            df_filtrado_global["Qual a frota utilizada?"] = df_filtrado_global["Qual a frota utilizada?"].replace(
                "Retirado por terceiros (vendedor, cliente ou outros.)", 
                "Retirado por terceiros"
            )

        # --- LINHA DE 4 GRÁFICOS TOP N ---
        st.markdown("---")
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: gerar_top_n(df_filtrado_global, "Tipo de solicitação:", "Top Tipos de Solicitação", cor="Blues")
        with r1c2: gerar_top_n(df_filtrado_global, "Criador", "Top Criadores (Solicitantes)", cor="Teal")
        with r1c3: gerar_top_n(df_filtrado_global, "Qual a frota utilizada?", "Frota Utilizada", cor="Purples")
        
        with r1c4:
            if opcao_redespacho == "Considerar todos":
                if not df_sap_pago.empty:
                    # Normaliza e SOMA os valores (Motivo de não usarmos a gerar_top_n)
                    df_sap_pago['Transportadora'] = df_sap_pago['SupplierName'].apply(normalizar_transportadora)
                    df_pago_transp = df_sap_pago.groupby('Transportadora')['AmountInCompanyCodeCurrency'].sum().nlargest(7).sort_values(ascending=True).reset_index()

                    fig_fin = px.bar(
                        df_pago_transp, 
                        x='AmountInCompanyCodeCurrency', 
                        y='Transportadora',
                        orientation='h',
                        title="Gastos por Transportadora",
                        color='AmountInCompanyCodeCurrency',
                        color_continuous_scale='Greens'
                    )
                    
                    fig_fin.update_layout(
                        height=280, margin=dict(l=10, r=60, t=30, b=10), 
                        yaxis={'categoryorder':'total ascending'}, 
                        coloraxis_showscale=False, xaxis_title=None, yaxis_title=None, 
                        title_font_size=14
                    )
                    fig_fin.update_traces(texttemplate="R$ %{x:.2s}", textposition="outside", cliponaxis=False)
                    st.plotly_chart(fig_fin, use_container_width=True)
                else:
                    st.info("Sem pagamentos para o período.")
            else:
                st.warning("Gráfico indisponível (Filtro ativo).")

    # -----------------------------------------------------------
    # 💰 VENDAS
    # -----------------------------------------------------------
    with aba_vendas:
        if "Tipo de solicitação:" in df_filtrado_global.columns:
            df_vendas = df_filtrado_global[df_filtrado_global["Tipo de solicitação:"].str.upper() == "VENDA"].copy()
            
            # --- APLICANDO A REGRA DE ENCURTAR NOMES ---
            if "Cliente:" in df_vendas.columns:
                df_vendas["Cliente:"] = df_vendas["Cliente:"].apply(encurtar_nome_cliente_fornecedor)
            
            if "Pipe Pai:" in df_vendas.columns:
                mask_pipe = df_vendas["Pipe Pai:"].astype(str).str.strip().isin(["Pedido de Garantia", "Solicitações Itens Fábrica"])
                mask_mod = df_vendas["Modalidade"].astype(str).str.strip() == "Garantias" if "Modalidade" in df_vendas.columns else pd.Series(False, index=df_vendas.index)
                if "Unidade de embarque:" in df_vendas.columns:
                    df_vendas.loc[mask_pipe | mask_mod, "Unidade de embarque:"] = "Empresa A MATRIZ"

            c1, c2 = st.columns(2)
            c1.metric("Total de Vendas", len(df_vendas))
            c2.metric("Valor Total da Remessa", f"R$ {df_vendas.get('Valor da Remessa:', pd.Series([0])).sum(skipna=True):,.2f}")
            
            st.markdown("---")
            if not df_vendas.empty:
                r1c1, r1c2, r1c3, r1c4 = st.columns(4)
                with r1c1: gerar_pizza(df_vendas, "Modalidade", "Percentual por Modalidade")
                with r1c2: gerar_pizza(df_vendas, "Responsável pelo frete:", "Responsável Frete")
                with r1c3: gerar_pizza(df_vendas, "Tipo de local de entrega?", "Local de Entrega")
                with r1c4: gerar_pizza(df_vendas, "Unidade de embarque:", "Unidade Embarque")

                r2c1, r2c2, r2c3 = st.columns(3)
                with r2c1: gerar_top_n(df_vendas, "Cliente:", "Top Clientes")
                with r2c2: gerar_top_n(df_vendas, "Localidade (Desembarque):", "Cidades de Destino")
                with r2c3: gerar_top_n(df_vendas, "UF (Desembarque):", "UFs de Destino")

    # -----------------------------------------------------------
    # 🛒 COMPRAS
    # -----------------------------------------------------------
    with aba_compras:
        if "Tipo de solicitação:" in df_filtrado_global.columns:
            # Adicionado .copy() aqui por segurança
            df_compras = df_filtrado_global[df_filtrado_global["Tipo de solicitação:"].str.upper() == "COMPRA"].copy()
            
            # --- APLICANDO A REGRA DE ENCURTAR NOMES ---
            if "Fornecedor:" in df_compras.columns:
                df_compras["Fornecedor:"] = df_compras["Fornecedor:"].apply(encurtar_nome_cliente_fornecedor)
                
            c1, c2 = st.columns(2)
            c1.metric("Total de Compras", len(df_compras))
            c2.metric("Valor Total da Remessa", f"R$ {df_compras.get('Valor da Remessa:', pd.Series([0])).sum(skipna=True):,.2f}")
            
            st.markdown("---")
            if not df_compras.empty:
                r1c1, r1c2 = st.columns(2)
                with r1c1: gerar_pizza(df_compras, "Unidade de desembarque:", "Unidade de Desembarque")
                with r1c2: gerar_top_n(df_compras, "Fornecedor:", "Top Fornecedores")
                
                r2c1, r2c2 = st.columns(2)
                with r2c1: gerar_top_n(df_compras, "Localidade (Embarque):", "Cidades de Embarque")
                with r2c2: gerar_top_n(df_compras, "UF (Embarque):", "UFs de Embarque")

    # -----------------------------------------------------------
    # 📦 FILIAL E FÁBRICA (UNIFICADO NA MESMA ABA)
    # -----------------------------------------------------------
    with aba_filial_fabrica:
        
        # ==========================================
        # 1. SEÇÃO: ENVIO PARA A FILIAL
        # ==========================================
        st.markdown("### 📦 Envio para a Filial")
        if "Tipo de solicitação:" in df_filtrado_global.columns:
            df_filial = df_filtrado_global[df_filtrado_global["Tipo de solicitação:"].str.upper() == "ENVIO PARA A FILIAL"].copy()
            c1, c2 = st.columns(2)
            c1.metric("Total p/ Filial", len(df_filial))
            c2.metric("Valor Total", f"R$ {df_filial.get('Valor da Remessa:', pd.Series([0])).sum(skipna=True):,.2f}")

            if not df_filial.empty:
                if "Pipe Pai:" in df_filial.columns:
                    df_filial["Origem"] = df_filial["Pipe Pai:"].astype(str).str.strip().replace({"": "Solicitação Comum", "nan": "Solicitação Comum"})
                if "Unidade de embarque:" in df_filial.columns and "Unidade de desembarque:" in df_filial.columns:
                    df_filial["Fluxo"] = df_filial["Unidade de embarque:"].fillna("Não Inf.").astype(str) + " → " + df_filial["Unidade de desembarque:"].fillna("Não Inf.").astype(str)

                r1c1, r1c2 = st.columns(2)
                with r1c1: gerar_pizza(df_filial, "Origem", "Origem (Pipe Pai)")
                with r1c2: gerar_top_n(df_filial, "Fluxo", "Principais Fluxos")

        st.markdown("---")

        # ==========================================
        # 2. SEÇÃO: ENVIO PARA A FÁBRICA E DEVOLUÇÕES
        # ==========================================
        st.markdown("### 🏭 Envio para a Fábrica & Devolução")
        if "Tipo de solicitação:" in df_filtrado_global.columns:
            
            mask_fabrica = df_filtrado_global["Tipo de solicitação:"].str.upper().isin(["ENVIO PARA A FÁBRICA", "DEVOLUÇÃO COMERCIAL"])
            df_fabrica = df_filtrado_global[mask_fabrica].copy()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total p/ Fábrica", len(df_fabrica))
            c2.metric("Valor Total Remessa", f"R$ {df_fabrica.get('Valor da Remessa:', pd.Series([0])).sum(skipna=True):,.2f}")
            
            if not df_fabrica.empty:
                if "Pipe Pai:" in df_fabrica.columns and "Valor da Remessa:" in df_fabrica.columns:
                    
                    mask_dev_velha = df_fabrica['Pipe Pai:'].astype(str).str.upper() == 'DEVOLUÇÃO COMERCIAL'
                    mask_dev_nova = df_fabrica['Tipo de solicitação:'].astype(str).str.upper() == 'DEVOLUÇÃO COMERCIAL'
                    val_dev = df_fabrica[mask_dev_velha | mask_dev_nova]["Valor da Remessa:"].sum(skipna=True)
                    
                    c3.metric("Devolução Comercial", f"R$ {val_dev:,.2f}")
                    
                    def ajustar_origem(row):
                        tipo = str(row.get("Tipo de solicitação:", "")).upper()
                        pai = str(row.get("Pipe Pai:", "")).strip()
                        
                        if tipo == 'DEVOLUÇÃO COMERCIAL' or pai.upper() == 'DEVOLUÇÃO COMERCIAL': 
                            return 'Devolução Comercial'
                            
                        if pai and pai.lower() != "nan": 
                            return pai
                            
                        return "Solicitação Comum"
                        
                    df_fabrica["Origem"] = df_fabrica.apply(ajustar_origem, axis=1)

                def deduzir_embarque(row):
                    emb = str(row.get("Unidade de embarque:", "")).strip()
                    if emb and emb.lower() != "nan": return emb
                    cc = str(row.get("Centro de custo:", "")).strip()
                    if "-" in cc and len(cc.split("-")) >= 2: return cc.split("-")[1].strip()
                    return "Não Informado"
                
                df_fabrica["Fluxo"] = df_fabrica.apply(deduzir_embarque, axis=1).astype(str) + " → Empresa A MATRIZ"

                r1c1, r1c2 = st.columns(2)
                with r1c1: gerar_pizza(df_fabrica, "Origem", "Origem (Pipe Pai / Tipo)")
                with r1c2: gerar_top_n(df_fabrica, "Fluxo", "Principais Fluxos", cor="Greens")

    # -----------------------------------------------------------
    # 🎯 MARKETING
    # -----------------------------------------------------------
    with aba_mkt:
        if "Tipo de solicitação:" in df_filtrado_global.columns:
            df_marketing = df_filtrado_global[df_filtrado_global["Tipo de solicitação:"].str.upper() == "AÇÕES MARKETING"].copy()
            st.metric("Total de Ações de Marketing", len(df_marketing))
            
            if not df_marketing.empty:
                frotas_proprias = ["CAMINHONETE INTERNA", "CAMINHÃO INTERNO"]
                df_marketing["Transportadora"] = df_marketing.apply(
                    lambda r: "Transporte Próprio" if (pd.isna(r.get("Nome da transportadora")) or str(r.get("Nome da transportadora")).strip() == "") 
                    and str(r.get("Qual a frota utilizada?")).strip().upper() in frotas_proprias 
                    else normalizar_transportadora(r.get("Nome da transportadora")), axis=1
                )
                
                st.markdown("---")
                r1c1, r1c2, r1c3, r1c4 = st.columns(4)
                with r1c1: gerar_top_n(df_marketing, "Localidade (Embarque):", "Cidades Origem")
                with r1c2: gerar_top_n(df_marketing, "UF (Embarque):", "UFs Origem")
                with r1c3: gerar_top_n(df_marketing, "Localidade (Desembarque):", "Cidades Destino")
                with r1c4: gerar_top_n(df_marketing, "UF (Desembarque):", "UFs Destino")
                
                st.markdown("---")
                gerar_top_n(df_marketing, "Transportadora", "Transportadoras Utilizadas")

    # -----------------------------------------------------------
    # 📄 COTAÇÕES 
    # -----------------------------------------------------------
    with aba_cotacoes:
        if df_cot.empty:
            st.info("A API não retornou dados de cotações para ativar os KPIs.")
        else:
            df_cot["Valor:"] = df_cot["Valor:"].apply(tratar_numero)

            fases_validas = ["Aguardando Despacho", "Aguardando Fatura", "Aguardando Entrega", "Concluído"]
            incluir_concluido = st.checkbox("Incluir registros 'Concluído'", value=True)
            
            df_temp = df_filtrado_global.copy()
            if "Fase atual" in df_temp.columns:
                df_temp = df_temp[df_temp["Fase atual"].isin(fases_validas)]
                if not incluir_concluido: df_temp = df_temp[df_temp["Fase atual"] != "Concluído"]

            if "Informe aqui as cotações realizadas para este frete:" in df_temp.columns:
                df_temp["Lista Cotações"] = df_temp["Informe aqui as cotações realizadas para este frete:"].fillna("").astype(str).apply(lambda x: [tratar_codigo_cotacao(i) for i in x.split(",")])
            if "Qual a cotação selecionada?" in df_temp.columns:
                df_temp["Cotacao_Normalizada"] = df_temp["Qual a cotação selecionada?"].fillna("").astype(str).apply(tratar_codigo_cotacao)
            
            df_temp_sel = df_temp[df_temp.get("Cotacao_Normalizada", "") != ""].copy() if "Cotacao_Normalizada" in df_temp.columns else pd.DataFrame()

            if df_temp_sel.empty:
                st.warning("Nenhum registro possui Cotação Selecionada nesta filtragem.")
            else:
                valores_aprovados, savings = [], []
                for _, row in df_temp_sel.iterrows():
                    lista_cod = row.get("Lista Cotações", [])
                    cod_selected = row.get("Cotacao_Normalizada", "")
                    valores_lista = df_cot[df_cot["Nº da cotação"].isin(lista_cod)]["Valor:"].tolist() if "Nº da cotação" in df_cot.columns else []
                    match_selected = df_cot[df_cot["Nº da cotação"] == cod_selected] if "Nº da cotação" in df_cot.columns else pd.DataFrame()
                    valor_selected = float(match_selected["Valor:"].iloc[0]) if not match_selected.empty and "Valor:" in match_selected.columns else None
                    
                    valores_aprovados.append(valor_selected)
                    savings.append(0 if not valores_lista or valor_selected is None else max(max(valores_lista) - valor_selected, 0))

                df_temp_sel["Valor Selecionado"] = valores_aprovados
                df_temp_sel["Saving"] = savings
                
                def calcular_desvio(row):
                    selecionado = row.get("Valor Selecionado", 0)
                    cte = row.get("Valor CTE:", 0)
                    if pd.isna(selecionado) or pd.isna(cte) or selecionado == 0 or cte == 0:
                        return None
                    desvio = ((cte - selecionado) / selecionado) * 100
                    return round(desvio, 2) if desvio > 0 else 0

                df_temp_sel["Desvio %"] = df_temp_sel.apply(calcular_desvio, axis=1)

                df_cot_lookup2 = df_cot[df_cot["Nº da cotação"] != ""].drop_duplicates(subset=["Nº da cotação"]) if "Nº da cotação" in df_cot.columns else pd.DataFrame()
                merge_cols = [c for c in ["Nº da cotação", "Valor:", "Transportadora:"] if c in df_cot_lookup2.columns]
                
                df_merge_frete = df_temp_sel.merge(df_cot_lookup2[merge_cols], how="left", left_on="Cotacao_Normalizada", right_on="Nº da cotação") if not df_cot_lookup2.empty else df_temp_sel.copy()
                df_merge_frete["Transportadora_Normalizada"] = df_merge_frete.get("Transportadora:", pd.Series("Vazio")).fillna("Vazio").apply(normalizar_transportadora)

                # MUDANÇA PARA ID_PIPEFY
                if os.path.exists(CAMINHO_CACHE_DISTANCIAS):
                    df_km = pd.read_excel(CAMINHO_CACHE_DISTANCIAS)
                    if "ID_Pipefy" in df_km.columns:
                        df_km["ID_Pipefy_Str"] = df_km["ID_Pipefy"].astype(str).str.strip()
                        df_km["KM_RODADO"] = df_km.get("KM_RODADO", pd.Series()).apply(tratar_numero)
                        df_km_lookup2 = df_km[df_km["ID_Pipefy_Str"] != ""].drop_duplicates(subset=["ID_Pipefy_Str"])
                        df_merge_frete["ID_Pipefy_Str"] = df_merge_frete["ID_Pipefy"].astype(str).str.strip()
                        df_merge_frete = df_merge_frete.merge(df_km_lookup2[["ID_Pipefy_Str", "KM_RODADO"]], how="left", on="ID_Pipefy_Str")
                        if "KM_RODADO_y" in df_merge_frete.columns:
                            df_merge_frete["KM_RODADO"] = df_merge_frete["KM_RODADO_y"]
                            df_merge_frete.drop(columns=[c for c in ["KM_RODADO_x", "KM_RODADO_y"] if c in df_merge_frete.columns], inplace=True)
                    else:
                        if "KM_RODADO" not in df_merge_frete.columns: df_merge_frete["KM_RODADO"] = None
                else:
                    if "KM_RODADO" not in df_merge_frete.columns: df_merge_frete["KM_RODADO"] = None

                df_merge_frete["KM_RODADO"] = pd.to_numeric(df_merge_frete["KM_RODADO"], errors="coerce")
                df_merge_frete["RS_KM"] = df_merge_frete.apply(lambda r: r.get("Valor:", 0) / r["KM_RODADO"] if pd.notna(r["KM_RODADO"]) and r["KM_RODADO"] > 0 else None, axis=1)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Fretes Analisados", len(df_temp_sel))
                
                sum_frete = df_merge_frete.get('Valor:', pd.Series([0])).sum()
                sum_rem = df_merge_frete.get('Valor da Remessa:', pd.Series([0])).sum()
                c2.metric("Frete / Remessa (%)", f"{(sum_frete / sum_rem * 100) if sum_rem > 0 else 0 :.2f}%")
                c3.metric("Saving Total", f"R$ {df_temp_sel['Saving'].sum():,.2f}")
                c4.metric("Saving Médio", f"R$ {df_temp_sel['Saving'].mean():,.2f}")

                st.markdown("---")
                r1c1, r1c2 = st.columns(2)
                with r1c1:
                    df_validos_desvio = df_temp_sel[(~df_temp_sel["Desvio %"].isna()) & (df_temp_sel["Valor Selecionado"] > 0) & (df_temp_sel.get("Valor CTE:", 0) > 0)].copy()
                    if not df_validos_desvio.empty:
                        def classificar_desvio(v):
                            if v <= 5: return "🟢 Verde — até 5%"
                            if v <= 10: return "🟡 Amarelo — 5% a 10%"
                            return "🔴 Vermelho — acima de 10%"

                        df_validos_desvio["Classificação"] = df_validos_desvio["Desvio %"].apply(classificar_desvio)
                        cont = df_validos_desvio["Classificação"].value_counts().reset_index()
                        cont.columns = ["Classificação", "Quantidade"]
                        
                        fig_d = px.bar(cont, x="Classificação", y="Quantidade", color="Classificação", 
                                       title="Classificação dos Desvios — CTe vs Cotação Selecionada", 
                                       text="Quantidade", 
                                       color_discrete_map={"🟢 Verde — até 5%": "green", "🟡 Amarelo — 5% a 10%": "yellow", "🔴 Vermelho — acima de 10%": "red"})
                        fig_d.update_layout(height=350, margin=dict(l=10, r=40, t=40, b=10), showlegend=False)
                        fig_d.update_traces(textposition="outside", cliponaxis=False)
                        st.plotly_chart(fig_d, use_container_width=True)
                        st.caption("🟢 Verde = CTe até 5% acima da cotação | 🟡 Amarelo = 5% a 10% acima | 🔴 Vermelho = mais de 10% acima")
                        st.caption(f"Registros válidos contabilizados: **{len(df_validos_desvio)}**")
                    else:
                        st.warning("Nenhum registro válido para desvio.")

                with r1c2:
                    if "Transportadora_Normalizada" in df_merge_frete.columns:
                        grupo_transp = df_merge_frete.groupby("Transportadora_Normalizada").agg(Frete_Total=("Valor:", "sum"), Quant=("Valor:", "count"), KM_Total=("KM_RODADO", "sum"), RS_KM_Medio=("RS_KM", "mean")).reset_index()
                        grupo_transp["Frete_Medio"] = grupo_transp["Frete_Total"] / grupo_transp["Quant"]
                        
                        if not grupo_transp.empty:
                            c_t1, c_t2 = st.columns(2)
                            min_pedidos_t = c_t1.slider("Mínimo Pedidos", 1, int(grupo_transp["Quant"].max()), 3, key="slider_transp_cot")
                            op_t = c_t2.radio("Métrica:", ["Frete Total", "Quantidade", "Frete Médio", "R$/KM"], horizontal=True, label_visibility="collapsed")
                            
                            df_plot_t = grupo_transp[(grupo_transp["Quant"] >= min_pedidos_t) & (grupo_transp["Transportadora_Normalizada"].str.upper() != "VAZIO")].copy()
                            
                            col_map = {"Frete Total": "Frete_Total", "Quantidade": "Quant", "Frete Médio": "Frete_Medio", "R$/KM": "RS_KM_Medio"}
                            x_col = col_map[op_t]
                            
                            if not df_plot_t.empty:
                                fig_t = px.bar(df_plot_t.sort_values(x_col, ascending=False).head(10), x=x_col, y="Transportadora_Normalizada", orientation="h", text=x_col, title=f"Top Transportadoras ({op_t})")
                                fig_t.update_layout(height=350, margin=dict(l=10, r=80, t=30, b=10), yaxis={'categoryorder':'total ascending'})
                                if op_t == "Quantidade": fig_t.update_traces(texttemplate="%{x:,.0f}", textposition="outside", cliponaxis=False)
                                else: fig_t.update_traces(texttemplate="R$ %{x:,.2f}", textposition="outside", cliponaxis=False)
                                st.plotly_chart(fig_t, use_container_width=True)

                # Exportação
                st.markdown("---")
                cd1, cd2 = st.columns(2)
                with cd1:
                    col_seguras = [c for c in ["Cotação Selecionada", "Transportadora_Normalizada", "Valor:", "KM_RODADO", "RS_KM"] if c in df_merge_frete.columns]
                    if col_seguras: st.download_button("📥 Baixar Tabela com KM (XLSX)", data=io.BytesIO(df_merge_frete[col_seguras].to_csv(index=False).encode('utf-8')), file_name="fretes_km.csv", mime="text/csv")
                with cd2:
                    st.download_button("📥 Baixar Cotações Analisadas (CSV)", data=io.BytesIO(df_temp_sel.to_csv(index=False).encode('utf-8')), file_name="cotacoes.csv", mime="text/csv")

    # ===========================================================
    # ⚖️ PESO & VOLUME (COM API ODATA SAP)
    # ===========================================================
    with aba_peso_vol:
        if df_sap.empty:
            st.info("A API do SAP não retornou faturas válidas para análise de Peso e Volume ou a conexão falhou.")
        else:
            df_fat = df_sap.copy()
            
            def normalizar_volume_letras(valor):
                if pd.isna(valor): return "OUTRO"
                txt = re.sub(r'[^A-Z]', '', ''.join(c for c in unicodedata.normalize('NFD', str(valor).upper().strip()) if unicodedata.category(c) != 'Mn'))
                if any(x in txt for x in ["EMPRESA", "CX", "CAIX"]): return "CAIXA"
                if any(x in txt for x in ["PAL", "PALT"]): return "PALETE"
                if any(x in txt for x in ["PAC", "PCT"]): return "PACOTE"
                return "OUTRO"
            
            if "MarcaVolume" in df_fat.columns: df_fat["Volume_Normalizado"] = df_fat["MarcaVolume"].apply(normalizar_volume_letras)
            if "PesoBrutoTotalNF" in df_fat.columns: df_fat["Peso Bruto (Total NF)"] = df_fat["PesoBrutoTotalNF"].apply(tratar_numero)
            if "QtdVolumesTransportados" in df_fat.columns: df_fat["Qtd Volumes (Total)"] = df_fat["QtdVolumesTransportados"].apply(tratar_numero)

            if "NumeroOV" in df_fat.columns and "Volume_Normalizado" in df_fat.columns:
                df_remessa = df_fat.groupby(["NumeroOV", "NumeroRemessa", "Volume_Normalizado"], as_index=False).agg(Peso_Total_KG=("Peso Bruto (Total NF)", "max"), Qtd_Volumes=("Qtd Volumes (Total)", "max"))
            else:
                df_remessa = pd.DataFrame()

            def norm_pedido(v):
                v = re.sub(r'\s+', '', str(v))
                if "." in v: v = v.split(".")[0]
                return "".join(c for c in v if c.isdigit()).lstrip("0")

            df_merge = df_merge_frete.copy() if 'df_merge_frete' in locals() else df_filtrado_global.copy()
            for req_col in ["Valor:", "KM_RODADO", "Transportadora_Normalizada"]:
                if req_col not in df_merge.columns: df_merge[req_col] = None
                
            df_merge["Pedido_Normalizado"] = df_merge.get("N° Pedido:", pd.Series("")).apply(norm_pedido)
            df_remessa["Pedido_Normalizado"] = df_remessa.get("NumeroOV", pd.Series()).apply(norm_pedido)
            df_merge = df_merge.merge(df_remessa[df_remessa["Pedido_Normalizado"] != ""], how="left", on="Pedido_Normalizado")

            for req_col in ["Peso_Total_KG", "Qtd_Volumes"]:
                if req_col not in df_merge.columns: df_merge[req_col] = None

            # Controladores Visuais da Aba Peso/Volume
            c_slider, c_min, c_rank = st.columns([2, 1, 1.5])
            with c_slider:
                km_max = int(df_merge["KM_RODADO"].max()) if df_merge["KM_RODADO"].notna().any() else 3000
                km_min, km_max_sel = st.slider("📏 Faixa de KM:", 0, km_max, (0, km_max), step=10)
            
            df_merge["Registro_Valido"] = df_merge["Valor:"].notna() & df_merge["KM_RODADO"].notna() & (df_merge["KM_RODADO"] > 0) & df_merge["Peso_Total_KG"].notna() & df_merge["Qtd_Volumes"].notna()
            df_validos = df_merge[df_merge["Registro_Valido"] & (df_merge["KM_RODADO"] >= km_min) & (df_merge["KM_RODADO"] <= km_max_sel)].copy()

            if not df_validos.empty:
                df_validos["kg_km"] = df_validos["Peso_Total_KG"] * df_validos["KM_RODADO"]
                df_validos["volume_km"] = df_validos["Qtd_Volumes"] * df_validos["KM_RODADO"]
                
                df_transp = df_validos.groupby("Transportadora_Normalizada", as_index=False).agg(Frete_Total=("Valor:", "sum"), Peso_Total=("Peso_Total_KG", "sum"), Volume_Total=("Qtd_Volumes", "sum"), KM_Total=("KM_RODADO", "sum"), Quantidade=("Pedido_Normalizado", "count"))
                df_transp["kg_km"] = df_validos.groupby("Transportadora_Normalizada")["kg_km"].sum().values
                df_transp["volume_km"] = df_validos.groupby("Transportadora_Normalizada")["volume_km"].sum().values
                df_transp["rs_kg_km"] = df_transp["Frete_Total"] / df_transp["kg_km"]
                df_transp["rs_volume_km"] = df_transp["Frete_Total"] / df_transp["volume_km"]

                with c_min:
                    min_pedidos = st.slider("📦 Mín. Pedidos:", 1, int(df_transp["Quantidade"].max()) if not df_transp.empty else 1, 5, step=1)
                with c_rank:
                    opcao_rank = st.radio("Métrica Ranking:", ["Frete Total (R$)", "Custo Médio (R$/kg·km)", "Custo Médio (R$/volume·km)"], label_visibility="collapsed")

                # Filtro extra para excluir "Vazio" do Ranking
                df_transp_filtrado = df_transp[(df_transp["Quantidade"] >= min_pedidos) & (df_transp["Transportadora_Normalizada"].str.upper() != "VAZIO")].copy()

                st.markdown("---")
                # Gráfico Ranking Geral
                if not df_transp_filtrado.empty:
                    x_col_rank = "Frete_Total" if "Frete" in opcao_rank else ("rs_kg_km" if "kg" in opcao_rank else "rs_volume_km")
                    fig_rank = px.bar(df_transp_filtrado.sort_values(x_col_rank, ascending=False).head(10), x=x_col_rank, y="Transportadora_Normalizada", orientation="h", text=x_col_rank, color=x_col_rank, color_continuous_scale="Blues", title=f"Ranking: {opcao_rank}")
                    fig_rank.update_layout(height=280, margin=dict(l=10, r=80, t=30, b=10), yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
                    fmt = "R$ %{x:,.2f}" if "Frete" in opcao_rank else "R$ %{x:,.4f}"
                    fig_rank.update_traces(texttemplate=fmt, textposition="outside", cliponaxis=False)
                    st.plotly_chart(fig_rank, use_container_width=True)

                st.markdown("---")
                
                # Gráficos Custo por Tipo de Volume Normalizado
                df_tipo = df_validos.groupby(["Transportadora_Normalizada", "Volume_Normalizado"], as_index=False).agg(Frete_Total=("Valor:", "sum"), Peso_Total=("Peso_Total_KG", "sum"), Volume_Total=("Qtd_Volumes", "sum"), KM_Total=("KM_RODADO", "sum"), Quant=("Pedido_Normalizado", "count"))
                
                # Filtro extra para excluir "Vazio"
                df_tipo = df_tipo[(df_tipo["Quant"] >= min_pedidos) & (df_tipo["Transportadora_Normalizada"].str.upper() != "VAZIO")].copy()
                
                if not df_tipo.empty and "Frete_Total" in df_tipo.columns:
                    df_tipo["kg_km"] = df_tipo["Peso_Total"] * df_tipo["KM_Total"]
                    df_tipo["volume_km"] = df_tipo["Volume_Total"] * df_tipo["KM_Total"]
                    df_tipo["rs_kg_km"] = df_tipo["Frete_Total"] / df_tipo["kg_km"]
                    df_tipo["rs_volume_km"] = df_tipo["Frete_Total"] / df_tipo["volume_km"]

                    cm1, cm2 = st.columns(2)
                    cm1.metric("💰 Média Global (R$/kg·km)", f"R$ {df_tipo['rs_kg_km'].mean():,.4f}")
                    cm2.metric("📦 Média Global (R$/vol·km)", f"R$ {df_tipo['rs_volume_km'].mean():,.4f}")

                    r1c1, r1c2 = st.columns(2)
                    with r1c1:
                        fig1 = px.bar(df_tipo, x="rs_kg_km", y="Transportadora_Normalizada", color="Volume_Normalizado", barmode="group", orientation="h", title="Custo Médio (R$/kg·km) por Tipo")
                        fig1.update_layout(height=320, margin=dict(l=10, r=80, t=30, b=10), yaxis_title=None)
                        fig1.update_traces(texttemplate="R$ %{x:,.4f}", textposition="outside", cliponaxis=False)
                        st.plotly_chart(fig1, use_container_width=True)
                    with r1c2:
                        fig2 = px.bar(df_tipo, x="rs_volume_km", y="Transportadora_Normalizada", color="Volume_Normalizado", barmode="group", orientation="h", title="Custo Médio (R$/vol·km) por Tipo")
                        fig2.update_layout(height=320, margin=dict(l=10, r=80, t=30, b=10), yaxis_title=None)
                        fig2.update_traces(texttemplate="R$ %{x:,.4f}", textposition="outside", cliponaxis=False)
                        st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.warning("Após os filtros, não há registros suficientes para calcular médias comparativas de volume.")
            else:
                st.warning("Nenhum registro com informações financeiras e de peso válidas para esta faixa de KM.")

    # ===========================================================
    # ⏱️ SLAS E ATRASOS 
    # ===========================================================
    with aba_slas:
        if "Fase atual" in df_filtrado_global.columns:
            df_slas_ativo = df_filtrado_global[~df_filtrado_global["Fase atual"].astype(str).str.upper().isin(["CONCLUÍDO", "FINALIZADO", "CANCELADO", "DESCONTINUADO"])].copy()

            if not df_slas_ativo.empty:
                c1, c2, c3 = st.columns(3)
                with c1:
                    contagem_fase = df_slas_ativo["Fase atual"].value_counts().reset_index()
                    contagem_fase.columns = ["Fase", "Qtd"]
                    fig_f = px.bar(contagem_fase.head(10), x="Qtd", y="Fase", orientation="h", title="Cards Parados por Fase", text="Qtd", color="Qtd", color_continuous_scale="Reds")
                    fig_f.update_layout(height=350, margin=dict(l=10, r=50, t=30, b=10), yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, yaxis_title=None)
                    fig_f.update_traces(textposition="outside", cliponaxis=False)
                    st.plotly_chart(fig_f, use_container_width=True)

                with c2:
                    tempo_cols = [c for c in df_slas_ativo.columns if isinstance(c, str) and any(x in c.upper() for x in ["(TEMPO", "(DIA", "(DURA", "(LEAD"])]
                    if tempo_cols:
                        df_tempo = df_slas_ativo[tempo_cols].copy()
                        for col in tempo_cols: df_tempo[col] = pd.to_numeric(df_tempo[col], errors='coerce')
                        media_tempo = df_tempo.mean().reset_index()
                        media_tempo.columns = ["Fase", "Tempo"]
                        
                        def limpa_fase(nome):
                            n = re.sub(r'\s*\([^)]*(tempo|dia|dura|lead)[^)]*\)', '', str(nome), flags=re.IGNORECASE)
                            return re.sub(r'(?i)\s*-?\s*tempo (total )?na fase', '', n).strip()
                        
                        media_tempo["Fase"] = media_tempo["Fase"].apply(limpa_fase)
                        media_tempo = media_tempo[~media_tempo["Fase"].str.upper().isin(["CONCLUÍDO", "FINALIZADO", "CANCELADO", "DESCONTINUADO"])]
                        media_tempo = media_tempo[media_tempo["Tempo"] > 0].sort_values("Tempo", ascending=False).head(10)

                        fig_t = px.bar(media_tempo, x="Tempo", y="Fase", orientation="h", title="Tempo Médio na Fase", text="Tempo", color="Tempo", color_continuous_scale="Oranges")
                        fig_t.update_layout(height=350, margin=dict(l=10, r=60, t=30, b=10), yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, yaxis_title=None)
                        fig_t.update_traces(texttemplate="%{text:.1f} d", textposition="outside", cliponaxis=False)
                        st.plotly_chart(fig_t, use_container_width=True)
                    else:
                        st.info("Sem dados de SLA na base.")

                with c3:
                    if "Vencido" in df_slas_ativo.columns:
                        df_v = df_slas_ativo.copy()
                        df_v["Status"] = df_v["Vencido"].astype(str).str.upper().replace({"TRUE": "Atrasado", "SIM": "Atrasado", "YES": "Atrasado", "1": "Atrasado", "1.0": "Atrasado", "FALSE": "No Prazo", "NÃO": "No Prazo", "NAO": "No Prazo", "0": "No Prazo", "NAN": "S/ Info"})
                        cont_v = df_v["Status"].value_counts().reset_index()
                        cont_v.columns = ["Status", "Qtd"]
                        fig_v = px.pie(cont_v, names="Status", values="Qtd", title="Status de Vencimento", color="Status", color_discrete_map={"Atrasado": "#EF553B", "No Prazo": "#00CC96", "S/ Info": "#B6E880"})
                        fig_v.update_traces(textinfo="percent+value")
                        fig_v.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.2))
                        st.plotly_chart(fig_v, use_container_width=True)

                if tempo_cols:
                    with st.expander("🔍 Ver tabela detalhada com o tempo médio de todas as fases"):
                        media_completa = df_tempo.mean().reset_index()
                        media_completa.columns = ["Fase Original", "Tempo Médio (Dias)"]
                        st.dataframe(media_completa.style.format({"Tempo Médio (Dias)": "{:.2f}"}), use_container_width=True)
            else:
                st.warning("Não há cards ativos no momento na base.")
        else:
            st.info("A coluna de 'Fase atual' não foi encontrada.")