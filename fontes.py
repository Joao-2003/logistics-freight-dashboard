"""Leitura das fontes do dashboard de frete: Pipefy (GraphQL) e SAP (OData).

Sem dependência do Streamlit: o dashboard aplica o cache por cima, e o script diário de
distâncias usa as mesmas funções. No modo de demonstração (config.DEMO_DIR), lê os arquivos de demo/.
"""
import ast
import os
import re
import time

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from config import DEMO_DIR, PADROES_TRANSPORTADORAS, SEG

PIPEFY_URL = "https://api.pipefy.com/graphql"


# ===========================================================
# LIMPEZA (mesmas regras do dashboard atual)
# ===========================================================
def normalizar_transportadora(nome):
    if pd.isna(nome) or str(nome).strip() == "":
        return "Vazio"
    nome_upper = str(nome).upper()
    for nome_padrao, variacoes in PADROES_TRANSPORTADORAS.items():
        if any(v in nome_upper for v in variacoes):
            return nome_padrao
    return re.sub(r"^\d{2}\.\d{3}\.\d{3}\s+|\s+\d{11}$", "", str(nome).strip())


def encurtar_nome_cliente_fornecedor(nome):
    if pd.isna(nome) or str(nome).strip() == "":
        return "Não Informado"
    palavras = str(nome).strip().split()
    return " ".join(palavras[:-3]) if len(palavras) > 6 else str(nome).strip()


def tratar_numero(valor):
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    v = re.sub(r"[^\d\.,\-]", "", str(valor).strip())
    if v == "":
        return 0.0
    if "." in v and "," in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def tratar_codigo_cotacao(cod):
    if pd.isna(cod):
        return ""
    cod = str(cod).replace(" ", "").replace("\n", "").replace("\t", "").replace("\xa0", "").replace(",", "")
    if cod.endswith(".0"):
        cod = cod[:-2]
    if cod.endswith("."):
        cod = cod[:-1]
    try:
        if "e" in cod.lower():
            cod = str(int(float(cod)))
    except ValueError:
        pass
    return cod.strip()


def limpar_valor_pipefy(val):
    if isinstance(val, list):
        return ", ".join(str(i) for i in val)
    if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
        try:
            parsed = ast.literal_eval(val)
            if isinstance(parsed, list):
                return ", ".join(str(i) for i in parsed)
        except (ValueError, SyntaxError):
            pass
    return val


RENOMEAR_SOLIC = {
    "localidade (embarque)": "Localidade (Embarque):", "uf (embarque)": "UF (Embarque):",
    "unidade de embarque": "Unidade de embarque:", "localidade (desembarque)": "Localidade (Desembarque):",
    "uf (desembarque)": "UF (Desembarque):", "unidade de desembarque": "Unidade de desembarque:",
    "qual a cotação selecionada": "Qual a cotação selecionada?", "tipo de solicitação": "Tipo de solicitação:",
    "valor da remessa": "Valor da Remessa:", "pipe pai": "Pipe Pai:", "qual a frota utilizada": "Qual a frota utilizada?",
    "centro de custo": "Centro de custo:", "cliente": "Cliente:", "existe pedido no sap": "Existe pedido no SAP?",
    "n° pedido": "N° Pedido:", "numero do pedido": "N° Pedido:",
    "informe aqui as cotações realizadas para este frete": "Informe aqui as cotações realizadas para este frete:",
    "valor cte": "Valor CTE:", "modalidade": "Modalidade", "responsável pelo frete": "Responsável pelo frete:",
    "tipo de local de entrega": "Tipo de local de entrega?", "fornecedor": "Fornecedor:",
    "nome da transportadora": "Nome da transportadora", "peso total da carga": "Peso total da carga:",
}


def padronizar_colunas(df, tipo):
    if df.empty:
        return df
    rename = {}
    for c in df.columns:
        cl = str(c).lower().strip().replace(":", "").replace("?", "")
        if tipo == "solicitacao" and cl in RENOMEAR_SOLIC:
            rename[c] = RENOMEAR_SOLIC[cl]
        elif tipo == "cotacao":
            if cl in ("nº da cotação", "n da cotacao"):
                rename[c] = "Nº da cotação"
            elif cl == "valor":
                rename[c] = "Valor:"
            elif cl == "transportadora":
                rename[c] = "Transportadora:"
            elif "redespacho" in cl:
                rename[c] = "Necessário redespacho?"
    # Dois campos do Pipefy podem cair no mesmo nome (ex.: "Valor da Remessa:" do formulário inicial e
    # "Valor da remessa", criado depois numa fase). Ficar só com o primeiro zerava compras, filial e
    # fábrica. Junta os dois: vale o do formulário inicial (com ":") e, se vazio, o outro.
    destinos = {}
    for origem, destino in rename.items():
        destinos.setdefault(destino, []).append(origem)
    for destino, origens in destinos.items():
        if len(origens) > 1:
            origens = sorted(origens, key=lambda c: (not str(c).strip().endswith(":"), list(df.columns).index(c)))
            junto = df[origens[0]].copy()
            for o in origens[1:]:
                vazio = junto.isna() | junto.astype(str).str.strip().isin(["", "0", "0.0", "nan", "None"])
                junto = junto.where(~vazio, df[o])
            df = df.drop(columns=origens)
            df[destino] = junto
            for o in origens:
                rename.pop(o, None)
    df = df.rename(columns=rename)
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    if tipo == "cotacao":
        if "Nº da cotação" not in df.columns:
            df["Nº da cotação"] = df["Título"] if "Título" in df.columns else ""
        for col, padrao in [("Valor:", 0.0), ("Necessário redespacho?", "Vazio"), ("Transportadora:", "Vazio")]:
            if col not in df.columns:
                df[col] = padrao
    else:
        for col in ["Valor CTE:", "Valor da Remessa:"]:
            if col not in df.columns:
                df[col] = 0.0
    return df


# ===========================================================
# PIPEFY
# ===========================================================
def _pipefy_paginado(query_base, node_type, id_alvo, token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    linhas, after = [], None
    while True:
        after_str = f', after: "{after}"' if after else ""
        query = query_base.replace("{AFTER}", after_str).replace("{ID}", str(id_alvo))
        for tentativa in range(4):
            try:
                r = requests.post(PIPEFY_URL, json={"query": query}, headers=headers, timeout=120)
                if r.status_code == 200 and "errors" not in r.json():
                    break
            except requests.RequestException:
                pass
            time.sleep(3 * (tentativa + 1))
        else:
            raise RuntimeError(f"Pipefy não respondeu ({node_type} {id_alvo})")
        secao = r.json()["data"][node_type]
        for edge in secao["edges"]:
            node = edge["node"]
            linha = {"ID_Pipefy": node["id"], "Título": node.get("title", "")}
            if "created_at" in node:
                linha["Criado em"] = node["created_at"]
            if node.get("current_phase"):
                linha["Fase atual"] = node["current_phase"]["name"]
            if node.get("createdBy"):
                linha["Criador"] = node["createdBy"]["name"]
            if "late" in node:
                linha["Vencido"] = "Sim" if node["late"] else "Não"
            for ph in node.get("phases_history") or []:
                if ph and ph.get("phase") and ph.get("duration") is not None:
                    linha[f"Tempo na fase {ph['phase']['name']} (Dias)"] = ph["duration"] / 86400.0
            for field in node.get("fields", node.get("record_fields", [])):
                linha[field["name"]] = limpar_valor_pipefy(field["value"])
            linhas.append(linha)
        if not secao["pageInfo"]["hasNextPage"]:
            break
        after = secao["pageInfo"]["endCursor"]
    return pd.DataFrame(linhas)


def _pos_pipefy(df_solic, df_cot):
    df_solic = padronizar_colunas(df_solic, "solicitacao")
    df_cot = padronizar_colunas(df_cot, "cotacao")
    if not df_solic.empty:
        df_solic["Criado em"] = pd.to_datetime(df_solic["Criado em"], errors="coerce", utc=True).dt.tz_localize(None)
        if "Fase atual" in df_solic.columns:
            df_solic = df_solic[df_solic["Fase atual"].astype(str).str.upper() != "DESCONTINUADO"]
        for col in ["Valor da Remessa:", "Valor Fatura", "Valor CTE:", "Peso total da carga:"]:
            if col in df_solic.columns:
                df_solic[col] = df_solic[col].apply(tratar_numero)
        df_solic["ID_Pipefy"] = df_solic["ID_Pipefy"].astype(str)
    if not df_cot.empty:
        df_cot["Nº da cotação"] = df_cot["Nº da cotação"].astype(str).apply(tratar_codigo_cotacao)
        df_cot["Valor:"] = df_cot["Valor:"].apply(tratar_numero)
    return df_solic.reset_index(drop=True), df_cot


def carregar_pipefy():
    if DEMO_DIR:
        return _demo_pipefy()
    q_solic = """{ allCards(pipeId: {ID}, first: 50 {AFTER}) { pageInfo { hasNextPage endCursor } edges { node { id title created_at late current_phase { name } createdBy { name } phases_history { phase { name } duration } fields { name value } } } } }"""
    q_cot = """{ table_records(table_id: "{ID}", first: 50 {AFTER}) { pageInfo { hasNextPage endCursor } edges { node { id title record_fields { name value } } } } }"""
    df_solic = _pipefy_paginado(q_solic, "allCards", SEG["PIPE_SOLICITACOES"], SEG["PIPEFY_TOKEN"])
    df_cot = _pipefy_paginado(q_cot, "table_records", SEG["PIPE_COTACOES"], SEG["PIPEFY_TOKEN"])
    return _pos_pipefy(df_solic, df_cot)


# ===========================================================
# SAP (OData com paginação própria: o servidor corta páginas grandes)
# ===========================================================
def _sap_get(url, auth, params, headers=None):
    for tentativa in range(4):
        try:
            r = requests.get(url, params=params, auth=auth, timeout=300,
                             headers={"Accept": "application/json", **(headers or {})})
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(5 * (tentativa + 1))
    raise RuntimeError(f"SAP não respondeu: {url}")


def _sap_v2(servico, entidade, usuario, senha, filtro, top=5000):
    url = f"{SEG['SAP_HOST']}/sap/opu/odata/sap/{servico}/{entidade}"
    auth = HTTPBasicAuth(SEG[usuario], SEG[senha])
    linhas, skip = [], 0
    while True:
        d = _sap_get(url, auth, {"$format": "json", "$filter": filtro, "$top": top, "$skip": skip}).get("d", {})
        lote = d.get("results", [])
        linhas += [{k: v for k, v in x.items() if k != "__metadata"} for x in lote]
        if len(lote) < top:
            return pd.DataFrame(linhas)
        skip += top


def _data_sap(serie):
    """/Date(1748736000000)/ -> Timestamp."""
    ms = pd.to_numeric(serie.astype(str).str.extract(r"(-?\d+)")[0], errors="coerce")
    return pd.to_datetime(ms, unit="ms", errors="coerce")


def _ler_csv(nome):
    return pd.read_csv(os.path.join(DEMO_DIR, nome), sep=";", dtype=str, encoding="utf-8-sig")


def carregar_sap_faturamento(desde="2025-01-01"):
    """ZC_REL_FATURAMENTO (notas de venda): peso e volumes por pedido, para a aba Peso/Vol."""
    if DEMO_DIR:
        df = _ler_csv("faturamento.csv")
    else:
        url = (f"{SEG['SAP_HOST']}/sap/opu/odata4/sap/zb_relatorio_faturamento/srvd/sap/"
               "zd_relatorio_faturamento/0001/ZC_REL_FATURAMENTO")
        auth = HTTPBasicAuth(SEG["SAP_FAT_USER"], SEG["SAP_FAT_PASS"])
        params = {"sap-language": "PT",
                  "$select": "NumeroOV,NumeroRemessa,MarcaVolume,PesoBrutoTotalNF,QtdVolumesTransportados,BR_NFSituationCode,NomeTipoDocumento,BR_NFIsCanceled",
                  "$filter": "BR_NFIsCanceled eq false and BR_NFSituationCode eq '00' and NomeTipoDocumento eq 'Fatura'"}
        linhas, skip, top = [], 0, 5000
        while True:
            lote = _sap_get(url, auth, {**params, "$top": top, "$skip": skip},
                            {"Prefer": f"odata.maxpagesize={top}"}).get("value", [])
            linhas += lote
            if len(lote) < top:
                break
            skip += top
        df = pd.DataFrame(linhas)
    return df


def carregar_sap_financeiro(desde="2025-06-01"):
    """YY1_ITENS_FORNECEDOR: partidas de fornecedor (pagamentos = chave de lançamento 25)."""
    if DEMO_DIR:
        df = _ler_csv("frete_itens_fornec.csv")
    else:
        df = _sap_v2("YY1_ITENS_FORNECEDOR_CDS", "YY1_ITENS_FORNECEDOR", "SAP_FIN_USER", "SAP_FIN_PASS",
                     f"PostingDate ge datetime'{desde}T00:00:00'")
    if df.empty:
        return df
    df["AmountInCompanyCodeCurrency"] = pd.to_numeric(df["AmountInCompanyCodeCurrency"], errors="coerce")
    df["Data_Filtro"] = _data_sap(df["PostingDate"]).dt.normalize()
    df["Supplier"] = df["Supplier"].astype(str).str.lstrip("0")
    return df


def carregar_sap_frete_nf(desde="2025-01-01"):
    """YY1_RELATORIO_FRETE: notas com parceiro (cidade/UF), transportadora, valor e peso bruto."""
    if DEMO_DIR:
        df = _ler_csv("frete_nf.csv")
    else:
        df = _sap_v2("YY1_RELATORIO_FRETE_CDS", "YY1_RELATORIO_FRETE", "SAP_FRETE_USER", "SAP_FRETE_PASS",
                     f"BR_NFIssueDate ge datetime'{desde}T00:00:00'")
    if df.empty:
        return df
    df["Data"] = _data_sap(df["BR_NFIssueDate"]) if df["BR_NFIssueDate"].astype(str).str.contains("Date").any() \
        else pd.to_datetime(df["BR_NFIssueDate"], errors="coerce")
    df["Valor"] = pd.to_numeric(df["BR_NFTotalAmount"], errors="coerce").fillna(0.0)
    peso = pd.to_numeric(df["HeaderGrossWeight"], errors="coerce").fillna(0.0)
    unid = df["HeaderWeightUnit"].fillna("KG").astype(str).str.upper()
    df["Peso_kg"] = peso * unid.map({"G": 0.001, "TO": 1000.0, "T": 1000.0}).fillna(1.0)
    df["Cancelada"] = df["BR_NFIsCanceled"].astype(str).str.lower().isin(["true", "1"])
    df["Direcao"] = df["BR_NFDirection"].astype(str).str.strip()
    return df


# ===========================================================
# MODO DEMONSTRAÇÃO (testes sem acesso às APIs)
# ===========================================================
def _demo_pipefy():
    """Lê os cards fictícios de demo/ e gera as cotações (a selecionada e as concorrentes)."""
    import random
    rnd = random.Random(7)
    rel_csv = os.path.join(DEMO_DIR, "pipefy_relatorio.csv")
    rel_xlsx = os.path.join(DEMO_DIR, "pipefy_relatorio.xlsx")  # relatório exportado do Pipefy (todas as colunas)
    if os.path.exists(rel_csv):
        cards = pd.read_csv(rel_csv, sep=";", encoding="utf-8-sig", low_memory=False)
    elif os.path.exists(rel_xlsx):
        cards = pd.read_excel(rel_xlsx)
    else:
        cards = pd.read_excel(os.path.join(DEMO_DIR, "distancias_cache.xlsx"))
    cards = cards.rename(columns={"Código": "ID_Pipefy"})
    cards = cards[[c for c in cards.columns if not str(c).startswith("Tempo total na fase")]]
    cards = cards.drop(columns=[c for c in ["LAT_O", "LON_O", "LAT_D", "LON_D", "KM_RODADO", "FONTE_O", "FONTE_D"]
                                if c in cards.columns])
    concorrentes = [n for n in PADROES_TRANSPORTADORAS if n not in ("FROTA PRÓPRIA", "CORREIOS", "GLOBAL EXPRESS")]
    cot = []
    for _, r in cards.iterrows():
        lista = [tratar_codigo_cotacao(c) for c in str(r.get("Informe aqui as cotações realizadas para este frete:", "") or "").split(",")]
        sel = tratar_codigo_cotacao(r.get("Qual a cotação selecionada?"))
        base = float(r.get("Valor Cotação Demo") or 0) or tratar_numero(r.get("Valor CTE:")) or rnd.uniform(150, 3000)
        transp = r.get("Nome da transportadora")
        for c in set([x for x in lista if x and x != "nan"] + ([sel] if sel and sel != "nan" else [])):
            t = transp if c == sel and pd.notna(transp) else rnd.choice(concorrentes)
            if c == sel and str(r.get("Qual a frota utilizada?", "")).upper() in ("CAMINHÃO INTERNO", "CAMINHONETE INTERNA"):
                t = "FROTA PRÓPRIA"
            cot.append({"ID_Pipefy": c, "Título": c, "Nº da cotação": c, "Valor": round(base * (1 if c == sel else rnd.uniform(1.03, 1.6)), 2),
                        "Transportadora": t, "Necessário redespacho?": rnd.choice(["Não", "Não", "Não", "Não", "Sim"])})
    cards = cards.drop(columns=["Valor Cotação Demo"], errors="ignore")
    return _pos_pipefy(cards, pd.DataFrame(cot))
