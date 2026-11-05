#!/usr/bin/env python
# coding: utf-8
"""Dashboard de Logística e Fretes (v2).

Pipefy (solicitações e cotações de frete) + SAP S/4HANA (notas, CT-e e pagamentos) + distâncias
(Nominatim + OSRM). Rodar: streamlit run Dashboard.py

Mudanças da v2 em relação à primeira versão:
- visual escuro, o mesmo do dashboard de vendas (Playfair Display + JetBrains Mono);
- credenciais em .streamlit/secrets.toml; leitura das APIs separada em fontes.py;
- Total Gasto com Frete pela lista de fornecedores (código no SAP), separado por categoria;
- KPIs que vinham zerados corrigidos (dois campos do Pipefy com o mesmo nome);
- motor de distâncias corrigido (motor_distancias.py) e rodando todo dia, independente de visitas;
- nova aba Transportadoras por Estado (mapa do Brasil com 5 critérios).
"""
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (ARQ_FORNECEDORES, CACHE_DISTANCIAS, DATA_INICIAL_PADRAO, DEMO_DIR, DIR_DADOS,  # noqa: E402
                    FROTAS_PROPRIAS, UNIDADE_MATRIZ)
from fontes import (carregar_pipefy, carregar_sap_faturamento, carregar_sap_financeiro,  # noqa: E402
                    carregar_sap_frete_nf, encurtar_nome_cliente_fornecedor, normalizar_transportadora,
                    tratar_codigo_cotacao, tratar_numero)
import mapa_estados  # noqa: E402
import motor_distancias  # noqa: E402

st.set_page_config(page_title="Dashboard de Fretes", page_icon="🚚", layout="wide", initial_sidebar_state="expanded")

# ===========================================================
# VISUAL (mesma paleta e fontes do dashboard de vendas)
# ===========================================================
COR = {"bg": "#0c1810", "sur": "#101e14", "card": "#141f17", "card2": "#192419", "bdr": "#1d2f20", "bdr2": "#253828",
       "G": "#3ecf6e", "G2": "#22a854", "Gd": "#1a6b37", "A": "#f5a623", "R": "#f06060", "B": "#5ba4cf",
       "t": "#dff0e4", "t2": "#8aab94", "t3": "#4a6652"}
PALETA = ["#3ecf6e", "#5ba4cf", "#f5a623", "#f06060", "#b48ef0", "#4fd1c5", "#e8c547", "#ef8fb6", "#8fbf5a", "#7aa7ff"]
ESCALAS = {"Blues": ["#16303f", "#5ba4cf"], "Greens": ["#163a24", "#3ecf6e"], "Teal": ["#123a36", "#4fd1c5"],
           "Purples": ["#2d2340", "#b48ef0"], "Reds": ["#3d1a1a", "#f06060"], "Oranges": ["#3d2a0e", "#f5a623"]}

pio.templates["frete"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=PALETA,
    font=dict(family="JetBrains Mono, monospace", color=COR["t"], size=11),
    title=dict(font=dict(family="Playfair Display, Georgia, serif", size=15, color=COR["t"]), x=0.01),
    xaxis=dict(gridcolor=COR["bdr"], zerolinecolor=COR["bdr2"], linecolor=COR["bdr2"], tickfont=dict(color=COR["t2"])),
    yaxis=dict(gridcolor=COR["bdr"], zerolinecolor=COR["bdr2"], linecolor=COR["bdr2"], tickfont=dict(color=COR["t2"])),
    legend=dict(font=dict(color=COR["t2"]), bgcolor="rgba(0,0,0,0)"),
    separators=",.",
    hoverlabel=dict(bgcolor="#06100a", bordercolor=COR["bdr2"], font=dict(family="JetBrains Mono", color=COR["t"])),
))
pio.templates.default = "plotly_dark+frete"

st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=JetBrains+Mono:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"], .stMarkdown, .stText, label, input, textarea, select, button {{ font-family: 'JetBrains Mono', monospace !important; }}
  .stApp {{ background: {COR['bg']}; color: {COR['t']}; }}
  .block-container {{ padding-top: 1rem; padding-bottom: 1rem; max-width: 98%; }}
  h1, h2, h3 {{ font-family: 'Playfair Display', Georgia, serif !important; font-weight: 600 !important; color: {COR['t']}; }}
  h1 {{ font-size: 1.55rem !important; margin-bottom: .1rem; }}
  h2, h3 {{ font-size: 1.1rem !important; margin: .2rem 0 .4rem 0; }}
  hr {{ margin: .6rem 0; border-color: {COR['bdr']} !important; }}
  section[data-testid="stSidebar"] {{ background: {COR['sur']}; border-right: 1px solid {COR['bdr']}; }}
  section[data-testid="stSidebar"][aria-expanded="true"] {{ min-width: 250px !important; max-width: 250px !important; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid {COR['bdr']}; }}
  .stTabs [data-baseweb="tab"] {{ height: 36px; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: {COR['t2']}; background: none; }}
  .stTabs [aria-selected="true"] {{ color: {COR['G']} !important; }}
  div[data-testid="stTab"] p {{ font-size: 11px; letter-spacing: 1px; text-transform: uppercase; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background: {COR['G']}; }}
  div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {{ background: {COR['card']}; border: 1px solid {COR['bdr']}; border-radius: 6px; padding: 6px 8px; }}
  div[data-testid="stExpander"] {{ background: {COR['card']}; border: 1px solid {COR['bdr']}; border-radius: 6px; }}
  .kp {{ background: {COR['card']}; border: 1px solid {COR['bdr']}; border-radius: 6px; padding: 13px 16px 12px; min-height: 96px; box-sizing: border-box; position: relative; overflow: hidden; margin-bottom: 10px; }}
  .kp::before {{ content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--kc), transparent); }}
  .kl {{ font-size: 9px; letter-spacing: 1.3px; text-transform: uppercase; color: {COR['t2']}; margin-bottom: 6px; }}
  .kv {{ font-family: 'Playfair Display', Georgia, serif; font-size: 1.45rem; font-weight: 600; color: {COR['t']}; line-height: 1.1; }}
  .ks {{ font-size: 10px; color: {COR['t3']}; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .sec {{ font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase; color: {COR['t2']}; margin: 14px 0 8px; display: flex; align-items: center; gap: 8px; }}
  .sec::before {{ content: ""; width: 3px; height: 12px; background: {COR['G']}; border-radius: 2px; }}
  .nota {{ font-size: 10.5px; color: {COR['t2']}; }}
</style>
""", unsafe_allow_html=True)


def kpi(col, rotulo, valor, sub=None, cor="G"):
    # a linha de baixo existe sempre (vazia se não houver texto) para todos os cartões terem a mesma altura
    col.markdown(f'<div class="kp" style="--kc:{COR[cor]}"><div class="kl">{rotulo}</div><div class="kv">{valor}</div>'
                 f'<div class="ks">{sub or "&nbsp;"}</div></div>', unsafe_allow_html=True)


def secao(titulo):
    st.markdown(f'<div class="sec">{titulo}</div>', unsafe_allow_html=True)


def brl(v, casas=2):
    return ("R$ {:,.%df}" % casas).format(v or 0).replace(",", "X").replace(".", ",").replace("X", ".")


def curto(v):
    v = v or 0
    if abs(v) >= 1e6:
        return f"R$ {v / 1e6:.1f} mi".replace(".", ",")
    if abs(v) >= 1e3:
        return f"R$ {v / 1e3:.1f} mil".replace(".", ",")
    return brl(v, 0)


def num(v):
    return f"{v:,.0f}".replace(",", ".")


# ===========================================================
# GRÁFICOS COMPACTOS
# ===========================================================
INVALIDOS = ["VAZIO", "NAN", "NONE", ""]


def gerar_top_n(df_local, coluna, titulo, top=7, cor="Greens"):
    if df_local.empty or coluna not in df_local.columns:
        return
    df_t = df_local[~df_local[coluna].astype(str).str.strip().str.upper().isin(INVALIDOS)]
    cont = df_t[coluna].value_counts().reset_index()
    cont.columns = [coluna, "Quantidade"]
    if cont.empty:
        return
    fig = px.bar(cont.head(top), x="Quantidade", y=coluna, orientation="h", text="Quantidade", color="Quantidade",
                 color_continuous_scale=ESCALAS.get(cor, ESCALAS["Greens"]), title=titulo)
    fig.update_layout(height=280, margin=dict(l=10, r=50, t=36, b=10), yaxis={"categoryorder": "total ascending"},
                      coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0)
    st.plotly_chart(fig, width="stretch")


def gerar_pizza(df_local, coluna, titulo):
    if df_local.empty or coluna not in df_local.columns:
        return
    df_t = df_local[~df_local[coluna].astype(str).str.strip().str.upper().isin(INVALIDOS)]
    cont = df_t[coluna].value_counts().reset_index()
    cont.columns = [coluna, "Quantidade"]
    if cont.empty:
        return
    fig = px.pie(cont, names=coluna, values="Quantidade", title=titulo, hole=0.55)
    fig.update_traces(textinfo="percent", hovertemplate="%{label}: %{value} reg. (%{percent})",
                      marker=dict(line=dict(color=COR["bg"], width=2)))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=36, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")


def barras_valor(df, x, y, titulo, cor="Greens", fmt="R$ %{x:,.2s}", altura=300):
    fig = px.bar(df, x=x, y=y, orientation="h", title=titulo, color=x, color_continuous_scale=ESCALAS[cor], text=x)
    fig.update_layout(height=altura, margin=dict(l=10, r=70, t=36, b=10), yaxis={"categoryorder": "total ascending"},
                      coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
    fig.update_traces(texttemplate=fmt, textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, width="stretch")


# ===========================================================
# DADOS (com cache do Streamlit)
# ===========================================================
@st.cache_data(ttl="12h", show_spinner=False)
def dados_pipefy():
    return carregar_pipefy()


@st.cache_data(ttl="12h", show_spinner=False)
def dados_sap():
    try:
        return carregar_sap_faturamento()
    except Exception as e:  # noqa: BLE001
        st.session_state["erro_sap"] = str(e)
        return pd.DataFrame()


@st.cache_data(ttl="12h", show_spinner=False)
def dados_sap_fin():
    try:
        return carregar_sap_financeiro("2025-06-01")
    except Exception as e:  # noqa: BLE001
        st.session_state["erro_fin"] = str(e)
        return pd.DataFrame()


@st.cache_data(ttl="12h", show_spinner=False)
def dados_frete_nf():
    try:
        return carregar_sap_frete_nf("2025-06-01")
    except Exception as e:  # noqa: BLE001
        st.session_state["erro_frete_nf"] = str(e)
        return pd.DataFrame()


@st.cache_data(ttl="10m", show_spinner=False)
def km_cache(mtime):
    if not os.path.exists(CACHE_DISTANCIAS):
        return pd.DataFrame(columns=["ID_Pipefy_Str", "KM_RODADO"])
    df = pd.read_excel(CACHE_DISTANCIAS, usecols=lambda c: c in ("ID_Pipefy", "KM_RODADO"))
    df["ID_Pipefy_Str"] = df["ID_Pipefy"].astype(str).str.strip()
    df["KM_RODADO"] = pd.to_numeric(df["KM_RODADO"], errors="coerce")
    return df[df["ID_Pipefy_Str"] != ""].drop_duplicates("ID_Pipefy_Str")[["ID_Pipefy_Str", "KM_RODADO"]]


def fornecedores_frete():
    df = pd.read_csv(ARQ_FORNECEDORES, sep=";", dtype=str, encoding="utf-8-sig")
    df["Supplier"] = df["Supplier"].astype(str).str.strip().str.lstrip("0")
    df["Nome_exibicao"] = df["Nome_exibicao"].fillna(df["Nome_SAP"])
    return df


# ===========================================================
# CABEÇALHO E SIDEBAR
# ===========================================================
st.title("Dashboard de Logística e Fretes")

if "admin" in st.query_params:
    st.cache_data.clear()
    st.query_params.clear()
    st.rerun()

with st.sidebar:
    st.markdown("### 🚚 Fretes")
    if DEMO_DIR:
        st.info("Demonstração com dados fictícios. Filtros, abas, mapa e motor de distâncias funcionam como no painel real.")
    if st.button("♻️ Recarregar dados (APIs)", width="stretch"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Buscando dados do Pipefy e do SAP... Na primeira vez do dia pode levar alguns minutos."):
    try:
        df_principal, df_cot = dados_pipefy()
    except Exception as e:  # noqa: BLE001
        st.error(f"Não foi possível ler o Pipefy: {e}")
        st.stop()
    df_sap = dados_sap()
    df_sap_fin = dados_sap_fin()

if df_principal.empty:
    st.warning("O Pipefy não retornou solicitações.")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Período")
    data_min_geral = datetime(*DATA_INICIAL_PADRAO).date()
    data_max_geral = max(df_principal["Criado em"].max().date(), datetime.now().date())
    data_inicial = st.date_input("Início", data_min_geral, format="DD/MM/YYYY")
    data_final = st.date_input("Fim", data_max_geral, format="DD/MM/YYYY")
    st.markdown("### 🔁 Redespacho")
    opcao_redespacho = st.radio("Redespacho", ["Considerar todos", "Somente Redespacho", "Excluir Redespacho"],
                                label_visibility="collapsed")

    # status do motor de distâncias
    st.markdown("### 📏 Distâncias")
    status_path = os.path.join(DIR_DADOS, "distancias_status.json")
    if os.path.exists(status_path):
        s = json.load(open(status_path, encoding="utf-8"))
        st.caption(f"Última atualização: {s.get('quando')} · {s.get('novos_km', 0)} novas · {s.get('sem_km', 0)} sem km"
                   + (f" · parou: {s['parou_por']}" if s.get("parou_por") else ""))
    elif os.path.exists(CACHE_DISTANCIAS):
        st.caption("Cache gravado em " + datetime.fromtimestamp(os.path.getmtime(CACHE_DISTANCIAS)).strftime("%d/%m/%Y %H:%M"))
    if st.button("Calcular distâncias pendentes", width="stretch",
                 help="Roda o motor agora (até 60 consultas). O cálculo completo roda todo dia (timer)."):
        with st.spinner("Calculando distâncias..."):
            r = motor_distancias.atualizar(df_principal, CACHE_DISTANCIAS, max_consultas=60, log=lambda *_: None)
        st.success(f"{r['novos_km']} novas distâncias; {r['sem_km']} cards sem km.")

inicio_dt = datetime(data_inicial.year, data_inicial.month, data_inicial.day)
fim_dt = datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59)
df_principal = df_principal[(df_principal["Criado em"] >= inicio_dt) & (df_principal["Criado em"] <= fim_dt)]

# ===========================================================
# PRÉ-PROCESSAMENTO GLOBAL
# ===========================================================
df_filtrado_global = df_principal.copy()
df_filtrado_global["Cotacao_Normalizada"] = df_filtrado_global.get(
    "Qual a cotação selecionada?", pd.Series("", index=df_filtrado_global.index)).fillna("").astype(str).apply(tratar_codigo_cotacao)
df_filtrado_global["Redespacho"] = "Vazio"
if not df_cot.empty:
    lookup = df_cot[df_cot["Nº da cotação"] != ""].drop_duplicates(subset=["Nº da cotação"])
    redesp = lookup.set_index("Nº da cotação")["Necessário redespacho?"]
    df_filtrado_global["Redespacho"] = df_filtrado_global["Cotacao_Normalizada"].map(redesp).apply(
        lambda v: "Somente Redespacho" if pd.notna(v) and "SIM" in str(v).upper() else "Vazio")
df_filtrado_global["ID_Pipefy_Str"] = df_filtrado_global["ID_Pipefy"].astype(str).str.strip()
df_km = km_cache(os.path.getmtime(CACHE_DISTANCIAS) if os.path.exists(CACHE_DISTANCIAS) else 0)
df_filtrado_global = df_filtrado_global.merge(df_km, how="left", on="ID_Pipefy_Str")

if opcao_redespacho == "Somente Redespacho":
    df_filtrado_global = df_filtrado_global[df_filtrado_global["Redespacho"] == "Somente Redespacho"]
elif opcao_redespacho == "Excluir Redespacho":
    df_filtrado_global = df_filtrado_global[df_filtrado_global["Redespacho"] != "Somente Redespacho"]

if "Qual a frota utilizada?" in df_filtrado_global.columns:
    df_filtrado_global["Qual a frota utilizada?"] = df_filtrado_global["Qual a frota utilizada?"].replace(
        "Retirado por terceiros (vendedor, cliente ou outros.)", "Retirado por terceiros")


def frete_cte(df):
    return float(df.get("Valor CTE:", pd.Series([0.0])).fillna(0).sum())


def remessa(df):
    return float(pd.to_numeric(df.get("Valor da Remessa:", pd.Series([0.0])), errors="coerce").fillna(0).sum())


def sub_frete(df):
    r, f = remessa(df), frete_cte(df)
    return f"{f / r * 100:.1f}% do valor da remessa".replace(".", ",") if r > 0 and f > 0 else None


def tipo(df, *tipos):
    if "Tipo de solicitação:" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["Tipo de solicitação:"].astype(str).str.upper().isin([t.upper() for t in tipos])].copy()


# ===========================================================
# ABAS
# ===========================================================
(aba_resumo, aba_vendas, aba_compras, aba_filial_fabrica, aba_mkt, aba_cotacoes, aba_estados,
 aba_peso_vol, aba_slas) = st.tabs([
    "📌 Resumo Geral", "💰 Vendas", "🛒 Compras", "📦 Filial & Fábrica", "🎯 Marketing", "📄 Cotações",
    "🗺️ Transportadoras por Estado", "⚖️ Peso/Vol", "⏱️ SLAs"])

# -----------------------------------------------------------
# 📌 RESUMO GERAL
# -----------------------------------------------------------
with aba_resumo:
    # --- Total gasto com frete: pagamentos (chave 25) aos fornecedores da lista fornecedores_frete.csv ---
    forn = fornecedores_frete()
    cat_total = ["Transportadora", "Autônomo", "Mudança", "Internacional"]
    df_sap_pago = pd.DataFrame()
    if not df_sap_fin.empty:
        pag = df_sap_fin[(df_sap_fin["PostingKey"].astype(str) == "25") & df_sap_fin["Data_Filtro"].notna()
                         & (df_sap_fin["Data_Filtro"] >= pd.Timestamp(data_inicial))
                         & (df_sap_fin["Data_Filtro"] <= pd.Timestamp(data_final))]
        pag = pag.merge(forn[["Supplier", "Categoria", "Nome_exibicao"]], how="left", on="Supplier")
        df_sap_pago = pag[pag["Categoria"].isin(cat_total)].copy()
    total_pago = float(df_sap_pago["AmountInCompanyCodeCurrency"].sum()) if not df_sap_pago.empty else 0.0
    por_cat = df_sap_pago.groupby("Categoria")["AmountInCompanyCodeCurrency"].sum() if not df_sap_pago.empty else pd.Series(dtype=float)

    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Total de Solicitações", num(len(df_filtrado_global)))
    kpi(c2, "Criadores Únicos", num(df_filtrado_global.get("Criador", pd.Series(dtype=str)).nunique()), cor="B")
    kpi(c3, "Tipos de Solicitação", num(df_filtrado_global.get("Tipo de solicitação:", pd.Series(dtype=str)).nunique()), cor="A")
    if opcao_redespacho == "Considerar todos":
        kpi(c4, "Total Gasto com Frete", brl(total_pago), "pagamentos no SAP no período")
    else:
        kpi(c4, "Total Gasto com Frete", "N/A", "o SAP não separa redespacho")
    if "erro_fin" in st.session_state:
        st.warning(f"O SAP financeiro não respondeu: {st.session_state['erro_fin']}")

    secao("Gasto com frete por categoria")
    k = st.columns(4)
    subs = {"Transportadora": "empresas de transporte", "Autônomo": "motoristas autônomos (PF e MEI)",
            "Mudança": "mudanças de colaboradores", "Internacional": "courier internacional"}
    for col, (cat, rot, cor) in zip(k, [("Transportadora", "Transportadoras", "G"), ("Autônomo", "Autônomos", "B"),
                                        ("Mudança", "Mudanças", "A"), ("Internacional", "Internacional", "R")]):
        kpi(col, rot, brl(por_cat.get(cat, 0.0)), subs[cat], cor)

    if "Criado em" in df_filtrado_global.columns:
        cont_tempo = df_filtrado_global.assign(Data=df_filtrado_global["Criado em"].dt.date).groupby("Data").size().reset_index(name="Volume")
        if not cont_tempo.empty:
            fig_line = px.area(cont_tempo, x="Data", y="Volume", title="Evolução de solicitações por dia")
            fig_line.update_traces(line_color=COR["G"], fillcolor="rgba(62,207,110,.15)")
            fig_line.update_layout(height=250, margin=dict(l=10, r=30, t=36, b=10), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_line, width="stretch")

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    with r1c1:
        gerar_top_n(df_filtrado_global, "Tipo de solicitação:", "Tipos de solicitação", cor="Blues")
    with r1c2:
        gerar_top_n(df_filtrado_global, "Criador", "Criadores (solicitantes)", cor="Teal")
    with r1c3:
        gerar_top_n(df_filtrado_global, "Qual a frota utilizada?", "Frota utilizada", cor="Purples")
    with r1c4:
        if opcao_redespacho != "Considerar todos":
            st.info("Gráfico indisponível com o filtro de redespacho.")
        elif df_sap_pago.empty:
            st.info("Sem pagamentos de frete no período.")
        else:
            g = df_sap_pago.groupby("Nome_exibicao")["AmountInCompanyCodeCurrency"].sum().nlargest(7).reset_index()
            barras_valor(g, "AmountInCompanyCodeCurrency", "Nome_exibicao", "Gasto por fornecedor de frete", altura=280)

    with st.expander("🔎 Fornecedores fora do total e a revisar"):
        st.markdown('<span class="nota">A lista fica em <b>fornecedores_frete.csv</b> (código do fornecedor no SAP e categoria). '
                    'Categorias somadas: Transportadora, Autônomo, Mudança e Internacional. "Revisar" e "Fora: …" não entram. '
                    'Para incluir alguém, troque a categoria no arquivo.</span>', unsafe_allow_html=True)
        if not df_sap_fin.empty:
            fora = pag[~pag["Categoria"].isin(cat_total) & pag["Categoria"].notna()]
            t = fora.groupby(["Categoria", "Supplier", "SupplierName"])["AmountInCompanyCodeCurrency"].sum().reset_index()
            t = t.sort_values(["Categoria", "AmountInCompanyCodeCurrency"], ascending=[True, False]).rename(
                columns={"Supplier": "Código", "SupplierName": "Fornecedor", "AmountInCompanyCodeCurrency": "Pago no período"})
            st.dataframe(t, width="stretch", hide_index=True, column_config={"Pago no período": st.column_config.NumberColumn(format="R$ %.2f")})
            novos = pag[pag["Categoria"].isna() & pag["SupplierName"].astype(str).str.upper().str.contains(r"TRANSP|LOGIST|CARGA|ENCOMEND|EXPRESS|FRETE|MUDAN", na=False)]
            if not novos.empty:
                st.markdown('<span class="nota">Fornecedores com nome de transporte que <b>não estão na lista</b>:</span>', unsafe_allow_html=True)
                n = novos.groupby(["Supplier", "SupplierName"])["AmountInCompanyCodeCurrency"].sum().reset_index().sort_values("AmountInCompanyCodeCurrency", ascending=False)
                st.dataframe(n.rename(columns={"Supplier": "Código", "SupplierName": "Fornecedor", "AmountInCompanyCodeCurrency": "Pago no período"}),
                             width="stretch", hide_index=True, column_config={"Pago no período": st.column_config.NumberColumn(format="R$ %.2f")})

# -----------------------------------------------------------
# 💰 VENDAS
# -----------------------------------------------------------
with aba_vendas:
    df_vendas = tipo(df_filtrado_global, "Venda")
    if "Cliente:" in df_vendas.columns:
        df_vendas["Cliente:"] = df_vendas["Cliente:"].apply(encurtar_nome_cliente_fornecedor)
    if "Pipe Pai:" in df_vendas.columns and "Unidade de embarque:" in df_vendas.columns:
        mask_pipe = df_vendas["Pipe Pai:"].astype(str).str.strip().isin(["Pedido de Garantia", "Solicitações Itens Fábrica"])
        mask_mod = df_vendas["Modalidade"].astype(str).str.strip() == "Garantias" if "Modalidade" in df_vendas.columns else False
        df_vendas.loc[mask_pipe | mask_mod, "Unidade de embarque:"] = UNIDADE_MATRIZ
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Total de Vendas", num(len(df_vendas)))
    kpi(c2, "Valor Total da Remessa", brl(remessa(df_vendas)), cor="B")
    kpi(c3, "Frete pago (CT-e)", brl(frete_cte(df_vendas)), sub_frete(df_vendas), "A")
    if not df_vendas.empty:
        r1 = st.columns(4)
        with r1[0]:
            gerar_pizza(df_vendas, "Modalidade", "Modalidade")
        with r1[1]:
            gerar_pizza(df_vendas, "Responsável pelo frete:", "Responsável pelo frete")
        with r1[2]:
            gerar_pizza(df_vendas, "Tipo de local de entrega?", "Local de entrega")
        with r1[3]:
            gerar_pizza(df_vendas, "Unidade de embarque:", "Unidade de embarque")
        r2 = st.columns(3)
        with r2[0]:
            gerar_top_n(df_vendas, "Cliente:", "Clientes")
        with r2[1]:
            gerar_top_n(df_vendas, "Localidade (Desembarque):", "Cidades de destino")
        with r2[2]:
            gerar_top_n(df_vendas, "UF (Desembarque):", "UFs de destino")

# -----------------------------------------------------------
# 🛒 COMPRAS
# -----------------------------------------------------------
with aba_compras:
    df_compras = tipo(df_filtrado_global, "Compra")
    if "Fornecedor:" in df_compras.columns:
        df_compras["Fornecedor:"] = df_compras["Fornecedor:"].apply(encurtar_nome_cliente_fornecedor)
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Total de Compras", num(len(df_compras)))
    kpi(c2, "Valor Total da Remessa", brl(remessa(df_compras)), cor="B")
    kpi(c3, "Frete pago (CT-e)", brl(frete_cte(df_compras)), sub_frete(df_compras), "A")
    if not df_compras.empty:
        r1 = st.columns(2)
        with r1[0]:
            gerar_pizza(df_compras, "Unidade de desembarque:", "Unidade de desembarque")
        with r1[1]:
            gerar_top_n(df_compras, "Fornecedor:", "Fornecedores")
        r2 = st.columns(2)
        with r2[0]:
            gerar_top_n(df_compras, "Localidade (Embarque):", "Cidades de embarque")
        with r2[1]:
            gerar_top_n(df_compras, "UF (Embarque):", "UFs de embarque")

# -----------------------------------------------------------
# 📦 FILIAL E FÁBRICA
# -----------------------------------------------------------
with aba_filial_fabrica:
    secao("Envio para a filial")
    df_filial = tipo(df_filtrado_global, "Envio para a filial")
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Total p/ Filial", num(len(df_filial)))
    kpi(c2, "Valor Total da Remessa", brl(remessa(df_filial)), cor="B")
    kpi(c3, "Frete pago (CT-e)", brl(frete_cte(df_filial)), sub_frete(df_filial), "A")
    if not df_filial.empty:
        if "Pipe Pai:" in df_filial.columns:
            df_filial["Origem"] = df_filial["Pipe Pai:"].astype(str).str.strip().replace({"": "Solicitação Comum", "nan": "Solicitação Comum"})
        if "Unidade de embarque:" in df_filial.columns and "Unidade de desembarque:" in df_filial.columns:
            df_filial["Fluxo"] = df_filial["Unidade de embarque:"].fillna("Não Inf.").astype(str) + " → " + df_filial["Unidade de desembarque:"].fillna("Não Inf.").astype(str)
        r1 = st.columns(2)
        with r1[0]:
            gerar_pizza(df_filial, "Origem", "Origem (Pipe Pai)")
        with r1[1]:
            gerar_top_n(df_filial, "Fluxo", "Principais fluxos")

    secao("Envio para a fábrica e devolução comercial")
    df_fabrica = tipo(df_filtrado_global, "Envio para a fábrica", "Devolução Comercial")
    mask_dev = (df_fabrica.get("Pipe Pai:", pd.Series("", index=df_fabrica.index)).astype(str).str.upper() == "DEVOLUÇÃO COMERCIAL") | \
               (df_fabrica["Tipo de solicitação:"].astype(str).str.upper() == "DEVOLUÇÃO COMERCIAL") if not df_fabrica.empty else pd.Series(dtype=bool)
    df_dev = df_fabrica[mask_dev] if not df_fabrica.empty else df_fabrica
    df_fab = df_fabrica[~mask_dev] if not df_fabrica.empty else df_fabrica
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Total p/ Fábrica", num(len(df_fabrica)), f"{len(df_fab)} envios · {len(df_dev)} devoluções")
    kpi(c2, "Devolução Comercial", brl(remessa(df_dev)), f"valor da remessa · {len(df_dev)} cards", "R")
    kpi(c3, "Frete pago · envios p/ fábrica", brl(frete_cte(df_fab)), f"{len(df_fab)} envios", "A")
    kpi(c4, "Frete pago · devolução comercial", brl(frete_cte(df_dev)), sub_frete(df_dev) or f"{len(df_dev)} devoluções", "A")
    if not df_fabrica.empty:
        def ajustar_origem(row):
            tp = str(row.get("Tipo de solicitação:", "")).upper()
            pai = str(row.get("Pipe Pai:", "")).strip()
            if tp == "DEVOLUÇÃO COMERCIAL" or pai.upper() == "DEVOLUÇÃO COMERCIAL":
                return "Devolução Comercial"
            return pai if pai and pai.lower() != "nan" else "Solicitação Comum"

        def deduzir_embarque(row):
            emb = str(row.get("Unidade de embarque:", "")).strip()
            if emb and emb.lower() != "nan":
                return emb
            cc = str(row.get("Centro de custo:", "")).strip()
            return cc.split("-")[1].strip() if "-" in cc and len(cc.split("-")) >= 2 else "Não Informado"

        df_fabrica["Origem"] = df_fabrica.apply(ajustar_origem, axis=1)
        df_fabrica["Fluxo"] = df_fabrica.apply(deduzir_embarque, axis=1).astype(str) + f" → {UNIDADE_MATRIZ}"
        r1 = st.columns(2)
        with r1[0]:
            gerar_pizza(df_fabrica, "Origem", "Origem (Pipe Pai / Tipo)")
        with r1[1]:
            gerar_top_n(df_fabrica, "Fluxo", "Principais fluxos")

# -----------------------------------------------------------
# 🎯 MARKETING
# -----------------------------------------------------------
with aba_mkt:
    df_marketing = tipo(df_filtrado_global, "Ações Marketing")
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Ações de Marketing", num(len(df_marketing)))
    kpi(c2, "Valor Total da Remessa", brl(remessa(df_marketing)), cor="B")
    kpi(c3, "Frete pago (CT-e)", brl(frete_cte(df_marketing)), sub_frete(df_marketing), "A")
    if not df_marketing.empty:
        df_marketing["Transportadora"] = df_marketing.apply(
            lambda r: "Transporte Próprio" if (pd.isna(r.get("Nome da transportadora")) or str(r.get("Nome da transportadora")).strip() == "")
            and str(r.get("Qual a frota utilizada?")).strip().upper() in FROTAS_PROPRIAS
            else normalizar_transportadora(r.get("Nome da transportadora")), axis=1)
        r1 = st.columns(4)
        for col, (campo, titulo) in zip(r1, [("Localidade (Embarque):", "Cidades de origem"), ("UF (Embarque):", "UFs de origem"),
                                             ("Localidade (Desembarque):", "Cidades de destino"), ("UF (Desembarque):", "UFs de destino")]):
            with col:
                gerar_top_n(df_marketing, campo, titulo)
        gerar_top_n(df_marketing, "Transportadora", "Transportadoras utilizadas", cor="Blues")

# -----------------------------------------------------------
# 📄 COTAÇÕES
# -----------------------------------------------------------
df_merge_frete = pd.DataFrame()
with aba_cotacoes:
    if df_cot.empty:
        st.info("A API não retornou dados de cotações.")
    else:
        fases_validas = ["Aguardando Despacho", "Aguardando Fatura", "Aguardando Entrega", "Concluído"]
        incluir_concluido = st.checkbox("Incluir registros 'Concluído'", value=True)
        df_temp = df_filtrado_global.copy()
        if "Fase atual" in df_temp.columns:
            df_temp = df_temp[df_temp["Fase atual"].isin(fases_validas)]
            if not incluir_concluido:
                df_temp = df_temp[df_temp["Fase atual"] != "Concluído"]
        df_temp["Lista Cotações"] = df_temp.get("Informe aqui as cotações realizadas para este frete:", pd.Series("", index=df_temp.index)) \
            .fillna("").astype(str).apply(lambda x: [tratar_codigo_cotacao(i) for i in x.split(",")])
        df_temp_sel = df_temp[df_temp["Cotacao_Normalizada"] != ""].copy()

        if df_temp_sel.empty:
            st.warning("Nenhum registro possui cotação selecionada neste filtro.")
        else:
            cot_valor = df_cot.groupby("Nº da cotação")["Valor:"].apply(list).to_dict()
            cot_primeiro = df_cot.drop_duplicates("Nº da cotação").set_index("Nº da cotação")
            valores_aprovados, savings = [], []
            for _, row in df_temp_sel.iterrows():
                valores_lista = [v for c in row["Lista Cotações"] for v in cot_valor.get(c, [])]
                sel = row["Cotacao_Normalizada"]
                valor_selected = float(cot_primeiro.at[sel, "Valor:"]) if sel in cot_primeiro.index else None
                valores_aprovados.append(valor_selected)
                savings.append(0 if not valores_lista or valor_selected is None else max(max(valores_lista) - valor_selected, 0))
            df_temp_sel["Valor Selecionado"] = valores_aprovados
            df_temp_sel["Saving"] = savings
            frota = df_temp_sel.get("Qual a frota utilizada?", pd.Series("", index=df_temp_sel.index)).fillna("").astype(str).str.strip().str.upper()
            transp_sel = df_temp_sel["Cotacao_Normalizada"].map(cot_primeiro["Transportadora:"]).apply(normalizar_transportadora)
            df_temp_sel["Tipo de frota"] = (frota.isin(FROTAS_PROPRIAS) | (transp_sel == "FROTA PRÓPRIA")).map({True: "Frota própria", False: "Terceiros"})

            def calcular_desvio(row):
                s, cte = row.get("Valor Selecionado", 0), row.get("Valor CTE:", 0)
                if pd.isna(s) or pd.isna(cte) or s == 0 or cte == 0:
                    return None
                d = ((cte - s) / s) * 100
                return round(d, 2) if d > 0 else 0

            df_temp_sel["Desvio %"] = df_temp_sel.apply(calcular_desvio, axis=1)
            lk = df_cot[df_cot["Nº da cotação"] != ""].drop_duplicates(subset=["Nº da cotação"])[["Nº da cotação", "Valor:", "Transportadora:"]]
            df_merge_frete = df_temp_sel.merge(lk, how="left", left_on="Cotacao_Normalizada", right_on="Nº da cotação")
            df_merge_frete["Transportadora_Normalizada"] = df_merge_frete["Transportadora:"].fillna("Vazio").apply(normalizar_transportadora)
            df_merge_frete["KM_RODADO"] = pd.to_numeric(df_merge_frete["KM_RODADO"], errors="coerce")
            df_merge_frete["RS_KM"] = df_merge_frete["Valor:"] / df_merge_frete["KM_RODADO"].where(df_merge_frete["KM_RODADO"] > 0)

            c1, c2, c3, c4 = st.columns(4)
            kpi(c1, "Fretes analisados", num(len(df_temp_sel)))
            rem_ok = pd.to_numeric(df_merge_frete.get("Valor da Remessa:", pd.Series(0.0, index=df_merge_frete.index)), errors="coerce").fillna(0)
            frete_ok = pd.to_numeric(df_merge_frete["Valor:"], errors="coerce").fillna(0)
            par = (rem_ok > 0) & (frete_ok > 0)  # só fretes com os dois valores, para não inflar o percentual
            sum_frete, sum_rem = frete_ok[par].sum(), rem_ok[par].sum()
            kpi(c2, "Frete / Remessa", f"{(sum_frete / sum_rem * 100) if sum_rem > 0 else 0:.2f}%".replace(".", ","),
                f"{num(int(par.sum()))} de {num(len(df_merge_frete))} fretes com remessa informada", "B")
            kpi(c3, "Saving Total", brl(df_temp_sel["Saving"].sum()), "maior cotação − cotação selecionada")
            kpi(c4, "Saving Médio", brl(df_temp_sel["Saving"].mean()), cor="A")

            r1c1, r1c2 = st.columns(2)
            with r1c1:
                val = df_temp_sel[(~df_temp_sel["Desvio %"].isna()) & (df_temp_sel["Valor Selecionado"] > 0) & (df_temp_sel.get("Valor CTE:", 0) > 0)].copy()
                if not val.empty:
                    def classificar_desvio(v):
                        return "Até 5%" if v <= 5 else ("5% a 10%" if v <= 10 else "Acima de 10%")
                    val["Classificação"] = val["Desvio %"].apply(classificar_desvio)
                    cont = val["Classificação"].value_counts().reindex(["Até 5%", "5% a 10%", "Acima de 10%"]).fillna(0).reset_index()
                    cont.columns = ["Classificação", "Quantidade"]
                    fig_d = px.bar(cont, x="Classificação", y="Quantidade", color="Classificação", text="Quantidade",
                                   title="Desvio do CT-e sobre a cotação selecionada",
                                   color_discrete_map={"Até 5%": COR["G"], "5% a 10%": COR["A"], "Acima de 10%": COR["R"]})
                    fig_d.update_layout(height=350, margin=dict(l=10, r=30, t=40, b=10), showlegend=False, xaxis_title=None, yaxis_title=None)
                    fig_d.update_traces(textposition="outside", cliponaxis=False)
                    st.plotly_chart(fig_d, width="stretch")
                    st.caption(f"Registros válidos: {len(val)} · verde até 5% acima da cotação, amarelo 5% a 10%, vermelho acima de 10%")
                else:
                    st.warning("Nenhum registro válido para desvio.")
            with r1c2:
                g = df_merge_frete.groupby("Transportadora_Normalizada").agg(Frete_Total=("Valor:", "sum"), Quant=("Valor:", "count"),
                                                                             RS_KM_Medio=("RS_KM", "mean")).reset_index()
                g["Frete_Medio"] = g["Frete_Total"] / g["Quant"]
                if not g.empty:
                    ct1, ct2 = st.columns(2)
                    min_t = ct1.slider("Mínimo de fretes", 1, int(g["Quant"].max()), min(3, int(g["Quant"].max())), key="slider_transp_cot")
                    op_t = ct2.radio("Métrica", ["Frete Total", "Quantidade", "Frete Médio", "R$/KM"], horizontal=True, label_visibility="collapsed")
                    xc = {"Frete Total": "Frete_Total", "Quantidade": "Quant", "Frete Médio": "Frete_Medio", "R$/KM": "RS_KM_Medio"}[op_t]
                    dp = g[(g["Quant"] >= min_t) & (g["Transportadora_Normalizada"].str.upper() != "VAZIO")].sort_values(xc, ascending=False).head(10)
                    if not dp.empty:
                        barras_valor(dp, xc, "Transportadora_Normalizada", f"Transportadoras ({op_t})", cor="Blues",
                                     fmt="%{x:,.0f}" if op_t == "Quantidade" else "R$ %{x:,.2f}", altura=350)

            cd1, cd2 = st.columns(2)
            with cd1:
                cols = [c for c in ["Cotacao_Normalizada", "Transportadora_Normalizada", "Valor:", "KM_RODADO", "RS_KM"] if c in df_merge_frete.columns]
                st.download_button("📥 Baixar fretes com KM (CSV)", data=df_merge_frete[cols].to_csv(index=False, sep=";").encode("utf-8-sig"),
                                   file_name="fretes_km.csv", mime="text/csv")
            with cd2:
                st.download_button("📥 Baixar cotações analisadas (CSV)", data=df_temp_sel.to_csv(index=False, sep=";").encode("utf-8-sig"),
                                   file_name="cotacoes.csv", mime="text/csv")

# -----------------------------------------------------------
# 🗺️ TRANSPORTADORAS POR ESTADO
# -----------------------------------------------------------
with aba_estados:
    st.markdown('<span class="nota">Principal transportadora de cada estado: <b>destino</b> nas saídas e <b>origem</b> nas entradas. '
                'Peso e notas vêm das notas fiscais do SAP (YY1_RELATORIO_FRETE); frete pago e R$/kg vêm dos CT-e do Pipefy '
                '(o SAP não tem o valor do frete por nota). Passe o mouse para ver a principal e clique para a lista completa.</span>',
                unsafe_allow_html=True)
    with st.spinner("Lendo as notas fiscais no SAP..."):
        df_nf = dados_frete_nf()
    if "erro_frete_nf" in st.session_state:
        st.warning(f"O SAP (YY1_RELATORIO_FRETE) não respondeu: {st.session_state['erro_frete_nf']}")
    cmin, _ = st.columns([1, 3])
    min_fretes = cmin.number_input("Mínimo de fretes para o R$/kg", 1, 20, 3, help="Evita que um frete isolado defina a mais barata do estado.")
    nf_per = df_nf[(df_nf["Data"] >= inicio_dt) & (df_nf["Data"] <= fim_dt)] if not df_nf.empty else df_nf
    cards_per = df_filtrado_global
    dados_mapa, sem_transp = mapa_estados.montar(nf_per, cards_per, df_cot, int(min_fretes))
    components.html(mapa_estados.html_mapa(dados_mapa, sem_transp, int(min_fretes), altura=640), height=660, scrolling=False)
    tab = mapa_estados.tabela_ranking(dados_mapa)
    if not tab.empty:
        st.download_button("📥 Baixar ranking por estado (CSV)", data=tab.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name="transportadoras_por_estado.csv", mime="text/csv")

# ===========================================================
# ⚖️ PESO & VOLUME
# ===========================================================
with aba_peso_vol:
    if df_sap.empty:
        st.info("O SAP não retornou faturas válidas para a análise de peso e volume.")
    elif df_merge_frete.empty:
        st.info("Sem fretes com cotação selecionada no filtro atual.")
    else:
        df_fat = df_sap.copy()

        def normalizar_volume_letras(valor):
            if pd.isna(valor):
                return "OUTRO"
            txt = re.sub(r"[^A-Z]", "", "".join(c for c in unicodedata.normalize("NFD", str(valor).upper().strip()) if unicodedata.category(c) != "Mn"))
            if any(x in txt for x in ["CX", "CAIX"]):
                return "CAIXA"
            if any(x in txt for x in ["PAL", "PALT"]):
                return "PALETE"
            if any(x in txt for x in ["PAC", "PCT"]):
                return "PACOTE"
            return "OUTRO"

        df_fat["Volume_Normalizado"] = df_fat["MarcaVolume"].apply(normalizar_volume_letras)
        df_fat["Peso Bruto (Total NF)"] = df_fat["PesoBrutoTotalNF"].apply(tratar_numero)
        df_fat["Qtd Volumes (Total)"] = df_fat["QtdVolumesTransportados"].apply(tratar_numero)
        df_remessa = df_fat.groupby(["NumeroOV", "NumeroRemessa", "Volume_Normalizado"], as_index=False).agg(
            Peso_Total_KG=("Peso Bruto (Total NF)", "max"), Qtd_Volumes=("Qtd Volumes (Total)", "max"))

        def norm_pedido(v):
            v = re.sub(r"\s+", "", str(v))
            v = v.split(".")[0] if "." in v else v
            return "".join(c for c in v if c.isdigit()).lstrip("0")

        df_merge = df_merge_frete.copy()
        df_merge["Pedido_Normalizado"] = df_merge.get("N° Pedido:", pd.Series("", index=df_merge.index)).apply(norm_pedido)
        df_remessa["Pedido_Normalizado"] = df_remessa["NumeroOV"].apply(norm_pedido)
        df_merge = df_merge.merge(df_remessa[df_remessa["Pedido_Normalizado"] != ""], how="left", on="Pedido_Normalizado")

        c_slider, c_min, c_rank = st.columns([2, 1, 1.5])
        with c_slider:
            km_max = int(df_merge["KM_RODADO"].max()) if df_merge["KM_RODADO"].notna().any() else 3000
            km_min, km_max_sel = st.slider("📏 Faixa de KM", 0, max(km_max, 10), (0, max(km_max, 10)), step=10)
        df_merge["Registro_Valido"] = df_merge["Valor:"].notna() & (df_merge["KM_RODADO"] > 0) & df_merge["Peso_Total_KG"].notna() & df_merge["Qtd_Volumes"].notna()
        df_validos = df_merge[df_merge["Registro_Valido"] & df_merge["KM_RODADO"].between(km_min, km_max_sel)].copy()

        if df_validos.empty:
            st.warning("Nenhum frete com valor, km e peso válidos nesta faixa.")
        else:
            df_validos["kg_km"] = df_validos["Peso_Total_KG"] * df_validos["KM_RODADO"]
            df_validos["volume_km"] = df_validos["Qtd_Volumes"] * df_validos["KM_RODADO"]
            df_transp = df_validos.groupby("Transportadora_Normalizada", as_index=False).agg(
                Frete_Total=("Valor:", "sum"), kg_km=("kg_km", "sum"), volume_km=("volume_km", "sum"), Quantidade=("Pedido_Normalizado", "count"))
            df_transp["rs_kg_km"] = df_transp["Frete_Total"] / df_transp["kg_km"]
            df_transp["rs_volume_km"] = df_transp["Frete_Total"] / df_transp["volume_km"]
            with c_min:
                min_pedidos = st.slider("📦 Mín. pedidos", 1, max(int(df_transp["Quantidade"].max()), 1), min(5, max(int(df_transp["Quantidade"].max()), 1)))
            with c_rank:
                opcao_rank = st.radio("Métrica", ["Frete Total (R$)", "Custo Médio (R$/kg·km)", "Custo Médio (R$/volume·km)"], label_visibility="collapsed")
            filt = df_transp[(df_transp["Quantidade"] >= min_pedidos) & (df_transp["Transportadora_Normalizada"].str.upper() != "VAZIO")]
            if not filt.empty:
                xr = "Frete_Total" if "Frete" in opcao_rank else ("rs_kg_km" if "kg" in opcao_rank else "rs_volume_km")
                barras_valor(filt.sort_values(xr, ascending=False).head(10), xr, "Transportadora_Normalizada", f"Ranking: {opcao_rank}",
                             cor="Blues", fmt="R$ %{x:,.2f}" if "Frete" in opcao_rank else "R$ %{x:,.4f}", altura=300)
            df_tipo = df_validos.groupby(["Transportadora_Normalizada", "Volume_Normalizado"], as_index=False).agg(
                Frete_Total=("Valor:", "sum"), Peso_Total=("Peso_Total_KG", "sum"), Volume_Total=("Qtd_Volumes", "sum"),
                KM_Total=("KM_RODADO", "sum"), Quant=("Pedido_Normalizado", "count"))
            df_tipo = df_tipo[(df_tipo["Quant"] >= min_pedidos) & (df_tipo["Transportadora_Normalizada"].str.upper() != "VAZIO")].copy()
            if df_tipo.empty:
                st.warning("Após os filtros, não há registros suficientes para comparar por tipo de volume.")
            else:
                df_tipo["rs_kg_km"] = df_tipo["Frete_Total"] / (df_tipo["Peso_Total"] * df_tipo["KM_Total"])
                df_tipo["rs_volume_km"] = df_tipo["Frete_Total"] / (df_tipo["Volume_Total"] * df_tipo["KM_Total"])
                cm1, cm2 = st.columns(2)
                kpi(cm1, "Média global (R$/kg·km)", brl(df_tipo["rs_kg_km"].mean(), 4))
                kpi(cm2, "Média global (R$/vol·km)", brl(df_tipo["rs_volume_km"].mean(), 4), cor="B")
                r1 = st.columns(2)
                for col, xc, tt in [(r1[0], "rs_kg_km", "Custo médio (R$/kg·km) por tipo"), (r1[1], "rs_volume_km", "Custo médio (R$/vol·km) por tipo")]:
                    with col:
                        fig = px.bar(df_tipo, x=xc, y="Transportadora_Normalizada", color="Volume_Normalizado", barmode="group", orientation="h", title=tt)
                        fig.update_layout(height=320, margin=dict(l=10, r=80, t=36, b=10), yaxis_title=None, xaxis_title=None)
                        fig.update_traces(texttemplate="R$ %{x:,.4f}", textposition="outside", cliponaxis=False)
                        st.plotly_chart(fig, width="stretch")

# ===========================================================
# ⏱️ SLAS E ATRASOS
# ===========================================================
with aba_slas:
    if "Fase atual" not in df_filtrado_global.columns:
        st.info("A coluna 'Fase atual' não foi encontrada.")
    else:
        df_slas_ativo = df_filtrado_global[~df_filtrado_global["Fase atual"].astype(str).str.upper().isin(["CONCLUÍDO", "FINALIZADO", "CANCELADO", "DESCONTINUADO"])].copy()
        if df_slas_ativo.empty:
            st.warning("Não há cards ativos no momento.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                cf = df_slas_ativo["Fase atual"].value_counts().reset_index()
                cf.columns = ["Fase", "Qtd"]
                fig_f = px.bar(cf.head(10), x="Qtd", y="Fase", orientation="h", title="Cards parados por fase", text="Qtd",
                               color="Qtd", color_continuous_scale=ESCALAS["Reds"])
                fig_f.update_layout(height=350, margin=dict(l=10, r=50, t=36, b=10), yaxis={"categoryorder": "total ascending"},
                                    coloraxis_showscale=False, yaxis_title=None, xaxis_title=None)
                fig_f.update_traces(textposition="outside", cliponaxis=False)
                st.plotly_chart(fig_f, width="stretch")
            tempo_cols = [c for c in df_slas_ativo.columns if isinstance(c, str) and any(x in c.upper() for x in ["(TEMPO", "(DIA", "(DURA", "(LEAD"])]
            df_tempo = df_slas_ativo[tempo_cols].apply(pd.to_numeric, errors="coerce") if tempo_cols else pd.DataFrame()
            with c2:
                if tempo_cols:
                    mt = df_tempo.mean().reset_index()
                    mt.columns = ["Fase", "Tempo"]

                    def limpa_fase(nome):
                        n = re.sub(r"\s*\([^)]*(tempo|dia|dura|lead)[^)]*\)", "", str(nome), flags=re.IGNORECASE)
                        return re.sub(r"(?i)\s*-?\s*tempo (total )?na fase", "", n).strip()

                    mt["Fase"] = mt["Fase"].apply(limpa_fase)
                    mt = mt[~mt["Fase"].str.upper().isin(["CONCLUÍDO", "FINALIZADO", "CANCELADO", "DESCONTINUADO"])]
                    mt = mt[mt["Tempo"] > 0].sort_values("Tempo", ascending=False).head(10)
                    fig_t = px.bar(mt, x="Tempo", y="Fase", orientation="h", title="Tempo médio na fase", text="Tempo",
                                   color="Tempo", color_continuous_scale=ESCALAS["Oranges"])
                    fig_t.update_layout(height=350, margin=dict(l=10, r=60, t=36, b=10), yaxis={"categoryorder": "total ascending"},
                                        coloraxis_showscale=False, yaxis_title=None, xaxis_title=None)
                    fig_t.update_traces(texttemplate="%{text:.1f} d", textposition="outside", cliponaxis=False)
                    st.plotly_chart(fig_t, width="stretch")
                else:
                    st.info("Sem dados de SLA na base.")
            with c3:
                if "Vencido" in df_slas_ativo.columns:
                    stt = df_slas_ativo["Vencido"].astype(str).str.upper().replace({"TRUE": "Atrasado", "SIM": "Atrasado", "YES": "Atrasado", "1": "Atrasado", "1.0": "Atrasado",
                                                                                   "FALSE": "No Prazo", "NÃO": "No Prazo", "NAO": "No Prazo", "0": "No Prazo", "NAN": "S/ Info"})
                    cv = stt.value_counts().reset_index()
                    cv.columns = ["Status", "Qtd"]
                    fig_v = px.pie(cv, names="Status", values="Qtd", title="Status de vencimento", color="Status", hole=0.55,
                                   color_discrete_map={"Atrasado": COR["R"], "No Prazo": COR["G"], "S/ Info": COR["t3"]})
                    fig_v.update_traces(textinfo="percent+value", marker=dict(line=dict(color=COR["bg"], width=2)))
                    fig_v.update_layout(height=350, margin=dict(l=10, r=10, t=36, b=10), legend=dict(orientation="h", y=-0.2))
                    st.plotly_chart(fig_v, width="stretch")
            if tempo_cols:
                with st.expander("🔍 Tempo médio de todas as fases"):
                    mc = df_tempo.mean().reset_index()
                    mc.columns = ["Fase", "Tempo médio (dias)"]
                    st.dataframe(mc, width="stretch", hide_index=True,
                                 column_config={"Tempo médio (dias)": st.column_config.NumberColumn(format="%.2f")})
