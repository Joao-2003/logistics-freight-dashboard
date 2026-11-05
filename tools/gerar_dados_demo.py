"""Gera os dados fictícios da pasta demo/ (usados pelo modo demonstração e pela página do GitHub Pages).

Nada aqui vem da empresa: clientes, fornecedores, transportadoras, pessoas, valores e números de
pedido são inventados. As cidades são reais (com coordenadas aproximadas) para o mapa e o motor de
distâncias fazerem sentido. A semente é fixa, então o resultado é sempre o mesmo.

    python tools/gerar_dados_demo.py
"""
import math
import os
import random
import sys
from datetime import datetime, timedelta

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from config import UNIDADES  # noqa: E402

DEMO = os.path.join(RAIZ, "demo")
rnd = random.Random(2026)

INICIO = datetime(2025, 6, 1)
FIM = datetime(2026, 10, 31)
N_CARDS = 1650

# ------------------------------------------------------------------ cidades (coordenadas aproximadas)
CIDADES = [
    ("Goiânia", "GO", -16.686, -49.264), ("Rio Verde", "GO", -17.792, -50.920), ("Jataí", "GO", -17.881, -51.714),
    ("Cristalina", "GO", -16.768, -47.613), ("Catalão", "GO", -18.166, -47.946), ("Itumbiara", "GO", -18.419, -49.215),
    ("Uberlândia", "MG", -18.918, -48.277), ("Uberaba", "MG", -19.747, -47.939), ("Patos de Minas", "MG", -18.579, -46.518),
    ("Unaí", "MG", -16.358, -46.906), ("Paracatu", "MG", -17.222, -46.874), ("Belo Horizonte", "MG", -19.917, -43.934),
    ("Ribeirão Preto", "SP", -21.177, -47.810), ("Campinas", "SP", -22.906, -47.061), ("Barretos", "SP", -20.557, -48.568),
    ("Presidente Prudente", "SP", -22.126, -51.389), ("Bauru", "SP", -22.315, -49.061), ("São Paulo", "SP", -23.550, -46.633),
    ("Londrina", "PR", -23.310, -51.163), ("Cascavel", "PR", -24.956, -53.455), ("Ponta Grossa", "PR", -25.095, -50.162),
    ("Curitiba", "PR", -25.428, -49.273), ("Maringá", "PR", -23.420, -51.933), ("Guarapuava", "PR", -25.395, -51.462),
    ("Chapecó", "SC", -27.100, -52.615), ("Joinville", "SC", -26.304, -48.849), ("Passo Fundo", "RS", -28.262, -52.408),
    ("Cruz Alta", "RS", -28.639, -53.606), ("Santa Maria", "RS", -29.684, -53.807), ("Porto Alegre", "RS", -30.035, -51.218),
    ("Rondonópolis", "MT", -16.470, -54.636), ("Sorriso", "MT", -12.545, -55.711), ("Sinop", "MT", -11.864, -55.503),
    ("Lucas do Rio Verde", "MT", -13.050, -55.911), ("Primavera do Leste", "MT", -15.560, -54.296), ("Cuiabá", "MT", -15.601, -56.097),
    ("Dourados", "MS", -22.221, -54.806), ("Campo Grande", "MS", -20.469, -54.620), ("Chapadão do Sul", "MS", -18.788, -52.623),
    ("Luís Eduardo Magalhães", "BA", -12.096, -45.786), ("Barreiras", "BA", -12.152, -44.990), ("Salvador", "BA", -12.971, -38.501),
    ("Balsas", "MA", -7.532, -46.035), ("Imperatriz", "MA", -5.526, -47.479), ("Uruçuí", "PI", -7.229, -44.556),
    ("Palmas", "TO", -10.184, -48.333), ("Gurupi", "TO", -11.729, -49.068), ("Paragominas", "PA", -2.997, -47.353),
    ("Vilhena", "RO", -12.740, -60.146), ("Brasília", "DF", -15.794, -47.882), ("Linhares", "ES", -19.391, -40.072),
    ("Petrolina", "PE", -9.389, -40.503), ("Fortaleza", "CE", -3.732, -38.527), ("Mossoró", "RN", -5.188, -37.344),
    ("Campos dos Goytacazes", "RJ", -21.754, -41.324), ("Arapiraca", "AL", -9.752, -36.661), ("Lagarto", "SE", -10.917, -37.650),
    ("Campina Grande", "PB", -7.230, -35.881), ("Manaus", "AM", -3.119, -60.022), ("Rio Branco", "AC", -9.975, -67.810),
]
PESO_UF = {"GO": 9, "MG": 8, "SP": 7, "PR": 7, "MT": 8, "MS": 5, "BA": 5, "RS": 4, "SC": 2, "MA": 3, "PI": 2, "TO": 3,
           "PA": 1, "RO": 1, "DF": 2, "ES": 1, "PE": 1, "CE": 1, "RN": 1, "RJ": 1, "AL": 1, "SE": 1, "PB": 1, "AM": 1, "AC": 1}
PESOS_CIDADE = [PESO_UF[c[1]] for c in CIDADES]

# Transportadoras fictícias: código no SAP, filial (UF) e regiões onde são fortes
TRANSP = {
    "RODOVIA EXPRESS LTDA": ("2000101", "GO", {"GO", "MG", "DF", "TO", "BA"}),
    "TRANSLESTE CARGAS LTDA": ("2000102", "MG", {"MG", "ES", "RJ", "BA"}),
    "ALFA SUL TRANSPORTES LTDA": ("2000103", "PR", {"PR", "SC", "RS"}),
    "CERRADO CARGAS E ENCOMENDAS": ("2000104", "MT", {"MT", "MS", "RO", "GO"}),
    "SERRA AZUL TRANSPORTES": ("2000105", "SP", {"SP", "MG", "PR"}),
    "NORTE RAPIDO LOGISTICA": ("2000106", "MA", {"MA", "PI", "PA", "TO", "CE"}),
    "PAMPA LOG TRANSPORTES": ("2000107", "RS", {"RS", "SC"}),
    "VALE LOG TRANSPORTES": ("2000108", "BA", {"BA", "PE", "SE", "AL", "PB", "RN"}),
    "ROTA CENTRAL CARGAS": ("2000109", "DF", {"DF", "GO", "TO"}),
    "ECO ENTREGAS EXPRESSAS": ("2000110", "SP", {"SP", "RJ", "AM", "AC"}),
    "AUTONOMO A": ("2000201", "GO", {"GO", "MG"}),
    "AUTONOMO B": ("2000202", "GO", {"GO", "MT"}),
    "AUTONOMO C": ("2000203", "PR", {"PR"}),
}
AUTONOMOS = {"AUTONOMO A", "AUTONOMO B", "AUTONOMO C"}

PESSOAS = ["Ana Ribeiro", "Bruno Lacerda", "Carla Menezes", "Diego Prado", "Elisa Monteiro", "Fábio Rocha",
           "Gabriela Nunes", "Henrique Sales", "Isabela Duarte", "Júlio Campos", "Larissa Freitas", "Marcos Teles"]
CLIENTES = [f"{a} {b} LTDA" for a in ["AGRO", "CAMPO FORTE", "TERRA BOA", "SAFRA", "SEMEAR", "VERDE VALE", "COLHEITA",
                                         "RURAL CENTER", "PLANTAR", "HORIZONTE"]
            for b in ["MÁQUINAS", "PEÇAS AGRÍCOLAS", "COMÉRCIO", "IMPLEMENTOS"]]
FORNECEDORES = [f"{a} {b}" for a in ["METALÚRGICA", "AÇOS", "BORRACHAS", "ELETRÔNICA", "PARAFUSOS", "TINTAS", "HIDRÁULICA"]
                for b in ["EXEMPLO LTDA", "MODELO S.A.", "FICTÍCIA EIRELI"]]
CENTROS = ["101 - FILIAL SP", "102 - FILIAL CURITIBA", "103 - CD MARINGÁ", "201 - COMERCIAL", "301 - ASSISTÊNCIA TÉCNICA"]
FASES = ["Cotação", "Aprovação Da Cotação", "Aguardando Entrega", "Aguardando CTE", "Fechamento do Frete", "Aguardando Fatura", "Concluído"]

UN = {k: v for k, v in UNIDADES.items() if k != "FILIAL CURITBA"}


def km_entre(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) * 1.27


def cidade():
    return rnd.choices(CIDADES, PESOS_CIDADE)[0]


def transportadora_para(uf):
    fortes = [t for t, (_, _, reg) in TRANSP.items() if uf in reg and t not in AUTONOMOS]
    if fortes and rnd.random() < 0.72:
        return rnd.choice(fortes)
    if uf in {"GO", "MG", "MT", "PR"} and rnd.random() < 0.25:
        return rnd.choice([t for t in AUTONOMOS if uf in TRANSP[t][2]] or ["AUTONOMO A"])
    return rnd.choice([t for t in TRANSP if t not in AUTONOMOS])


def ms(d):
    return f"/Date({int(d.replace(hour=0, minute=0, second=0).timestamp() * 1000)})/"


def main():
    os.makedirs(DEMO, exist_ok=True)
    cards, fat, nfs, cache = [], [], [], []
    tipos = ["Venda"] * 40 + ["Compra"] * 40 + ["Envio para a filial"] * 5 + ["Envio para a fábrica"] * 3 + \
            ["Devolução Comercial"] * 2 + ["Ações Marketing"] * 3 + ["Material de teste"] * 3 + ["Manutenção"] * 2 + \
            ["Devolução Fornecedor"] * 1 + ["Mudança colaborador"] * 1
    n_cot, n_ov, n_nf = 40000, 10000000, 1
    dias = (FIM - INICIO).days
    for i in range(N_CARDS):
        criado = INICIO + timedelta(days=dias * (i / N_CARDS) + rnd.uniform(-2, 2), hours=rnd.uniform(8, 18))
        criado = min(max(criado, INICIO), FIM)
        tp = rnd.choice(tipos)
        idade = (FIM - criado).days
        fase = "Concluído" if idade > 25 or rnd.random() < 0.55 else rnd.choice(FASES[:-1])
        if rnd.random() < 0.02:
            fase = "Descontinuado"
        c = {"Código": 900000000 + i * 37, "Título": f"Frete {i + 1:05d}", "Fase atual": fase,
             "Criador": rnd.choice(PESSOAS), "Criado em": criado.strftime("%Y-%m-%d %H:%M:%S"),
             "Vencido": rnd.random() < 0.3, "Tipo de solicitação:": tp}
        emb_un = des_un = None
        if tp == "Venda":
            emb_un = rnd.choices(["MATRIZ", "CD MARINGÁ", "FILIAL SP"], [80, 12, 8])[0]
            dest = cidade()
            c.update({"Pipe Pai:": rnd.choices(["Comercial", "Pedido de Garantia", ""], [75, 10, 15])[0],
                      "Modalidade": rnd.choices(["Venda", "Garantias", "Doações", "Demonstrações"], [80, 10, 5, 5])[0],
                      "Responsável pelo frete:": rnd.choices(["CIF → EMPRESA", "CIF → EMBUTIDO", "CIF → REDESPACHO"], [60, 28, 12])[0],
                      "Tipo de local de entrega?": rnd.choices(["Revenda", "Cliente final"], [85, 15])[0],
                      "Cliente:": rnd.choice(CLIENTES), "Existe pedido no SAP?": "Sim"})
            orig = UN[emb_un]
            o_cid, o_uf, o_ll = orig[0], orig[1], (orig[2], orig[3])
            d_cid, d_uf, d_ll = dest[0], dest[1], (dest[2], dest[3])
            remessa = round(rnd.lognormvariate(9.6, 0.8), 2)
        elif tp in ("Compra", "Devolução Fornecedor", "Material de teste", "Manutenção"):
            des_un = rnd.choices(["MATRIZ", "FILIAL SP", "FILIAL CURITIBA", "FILIAL CURITBA", "CD MARINGÁ"], [80, 8, 6, 1, 5])[0]
            orig = cidade()
            c.update({"Pipe Pai:": "Compras" if tp == "Compra" else "", "Fornecedor:": rnd.choice(FORNECEDORES)})
            o_cid, o_uf, o_ll = orig[0], orig[1], (orig[2], orig[3])
            dd = UN[des_un if des_un in UN else "FILIAL CURITIBA"]
            d_cid, d_uf, d_ll = dd[0], dd[1], (dd[2], dd[3])
            remessa = round(rnd.lognormvariate(9.3, 0.9), 2) if tp == "Compra" else round(rnd.lognormvariate(7.5, 0.8), 2)
            if tp == "Compra":
                tp_pai = c["Pipe Pai:"]
                c["Pipe Pai:"] = tp_pai
        elif tp == "Envio para a filial":
            emb_un = rnd.choice(["MATRIZ", "FILIAL SP", "CD MARINGÁ"])
            des_un = rnd.choice([u for u in ["FILIAL SP", "FILIAL CURITIBA", "MATRIZ"] if u != emb_un])
            c.update({"Pipe Pai:": rnd.choices(["Solicitações Itens Fábrica", "Comercial", ""], [60, 25, 15])[0]})
            o, d = UN[emb_un], UN[des_un]
            o_cid, o_uf, o_ll, d_cid, d_uf, d_ll = o[0], o[1], (o[2], o[3]), d[0], d[1], (d[2], d[3])
            remessa = round(rnd.lognormvariate(8.0, 0.9), 2) if rnd.random() < 0.7 else 0.0
        elif tp in ("Envio para a fábrica", "Devolução Comercial"):
            des_un = "MATRIZ"
            if tp == "Envio para a fábrica":
                emb_un = rnd.choice(["FILIAL SP", "FILIAL CURITIBA", "CD MARINGÁ", ""])
                c.update({"Pipe Pai:": rnd.choice(["Solicitações Itens Fábrica", ""]), "Centro de custo:": rnd.choice(CENTROS)})
                o = UN.get(emb_un) or UN["FILIAL SP"]
                o_cid, o_uf, o_ll = o[0], o[1], (o[2], o[3])
                remessa = 0.0 if rnd.random() < 0.85 else round(rnd.uniform(100, 600), 2)
            else:
                orig = cidade()
                c.update({"Pipe Pai:": "Devolução Comercial", "Cliente:": rnd.choice(CLIENTES),
                          "Centro de custo:": "201 - COMERCIAL"})
                o_cid, o_uf, o_ll = orig[0], orig[1], (orig[2], orig[3])
                remessa = round(rnd.lognormvariate(9.0, 0.7), 2)
            d = UN["MATRIZ"]
            d_cid, d_uf, d_ll = d[0], d[1], (d[2], d[3])
        else:  # Ações Marketing, Mudança colaborador
            emb_un = "MATRIZ"
            dest = cidade()
            o = UN["MATRIZ"]
            o_cid, o_uf, o_ll = o[0], o[1], (o[2], o[3])
            d_cid, d_uf, d_ll = dest[0], dest[1], (dest[2], dest[3])
            remessa = round(rnd.lognormvariate(7.8, 0.7), 2)

        # endereço: as unidades vão pelo nome; as demais pontas, pela cidade e UF
        c["Unidade de embarque:"] = emb_un or ""
        c["Unidade de desembarque:"] = des_un or ""
        c["Localidade (Embarque):"] = "" if emb_un else o_cid
        c["UF (Embarque):"] = "" if emb_un else o_uf
        c["Localidade (Desembarque):"] = "" if des_un else d_cid
        c["UF (Desembarque):"] = "" if des_un else d_uf
        if rnd.random() < 0.03:  # cards sem origem ou destino, como na vida real
            c["Localidade (Desembarque):"] = c["UF (Desembarque):"] = c["Unidade de desembarque:"] = ""

        km = km_entre(o_ll, d_ll) if o_ll != d_ll else 15.0
        peso = round(rnd.lognormvariate(5.4, 1.0), 1)
        c["Peso total da carga:"] = peso
        # remessa: uns cards só têm o campo novo (fase), para exercitar a junção dos dois campos
        if tp == "Venda" and rnd.random() < 0.18:
            c["Valor da Remessa:"], c["Valor da remessa"] = "", f"{remessa:.2f}".replace(".", ",")
        else:
            c["Valor da Remessa:"], c["Valor da remessa"] = (f"{remessa:.2f}".replace(".", ",") if remessa else ""), ""

        frota = rnd.choices(["Fornecedor externo", "Caminhão interno", "Caminhonete interna",
                             "Retirado por terceiros (vendedor, cliente ou outros.)"], [72, 14, 10, 4])[0]
        if km > 1300 and frota != "Fornecedor externo":
            frota = "Fornecedor externo"
        c["Qual a frota utilizada?"] = frota if fase not in ("Cotação",) else ""
        uf_ref = d_uf if (emb_un or not des_un) else o_uf
        transp = transportadora_para(uf_ref)
        frete = round(max(95.0, 70 + km * (0.33 + peso / 2200) * rnd.uniform(0.8, 1.25)), 2)
        if fase not in ("Cotação", "Descontinuado") and frota != "Retirado por terceiros (vendedor, cliente ou outros.)":
            cods = [str(n_cot + k) for k in range(rnd.choice([2, 3, 3, 4]))]
            n_cot += len(cods)
            sel = cods[0]
            c["Informe aqui as cotações realizadas para este frete:"] = ", ".join(cods)
            c["Qual a cotação selecionada?"] = sel
            c["Valor Cotação Demo"] = frete
            if frota == "Fornecedor externo":
                c["Nome da transportadora"] = transp
                if fase in ("Aguardando Fatura", "Concluído", "Fechamento do Frete"):
                    desvio = rnd.choices([0, rnd.uniform(0, .05), rnd.uniform(.05, .10), rnd.uniform(.10, .3)], [45, 35, 12, 8])[0]
                    c["Valor CTE:"] = f"{frete * (1 + desvio):.2f}".replace(".", ",")
        else:
            c["Informe aqui as cotações realizadas para este frete:"] = ""
        if tp == "Venda":
            n_ov += rnd.randint(1, 4)
            c["N° Pedido:"] = str(n_ov)
            marca = rnd.choices(["CAIXA", "CAIXAS", "PALLET", "PALETES", "PACOTE"], [45, 15, 25, 10, 5])[0]
            fat.append({"NumeroOV": str(n_ov), "NumeroRemessa": str(80000000 + i), "MarcaVolume": marca,
                        "PesoBrutoTotalNF": f"{peso:.3f}", "QtdVolumesTransportados": str(max(1, int(peso / rnd.uniform(15, 60)))),
                        "BR_NFSituationCode": "00", "NomeTipoDocumento": "Fatura", "BR_NFIsCanceled": "false"})
        # tempo em cada fase (dias), como o Pipefy devolve em phases_history
        for f in FASES[:-1]:
            if fase == "Concluído" or FASES.index(f) <= FASES.index(fase if fase in FASES else "Cotação"):
                c[f"Tempo na fase {f} (Dias)"] = round(rnd.expovariate(1 / {"Cotação": 1.2, "Aprovação Da Cotação": 0.8,
                                                                             "Aguardando Entrega": 4.5, "Aguardando CTE": 3.0,
                                                                             "Fechamento do Frete": 1.5, "Aguardando Fatura": 6.0}[f]), 2)
        cards.append(c)

        # nota fiscal no SAP para as saídas e entradas com transportadora
        if frota == "Fornecedor externo" and c.get("Nome da transportadora") and tp in ("Venda", "Compra"):
            cod_cli = str(3000000 + CLIENTES.index(c["Cliente:"])) if tp == "Venda" else str(4000000 + FORNECEDORES.index(c["Fornecedor:"]))
            nfs.append({"BR_NotaFiscal": str(n_nf), "BR_NFIssueDate": ms(criado + timedelta(days=rnd.randint(1, 6))),
                        "BR_NFDirection": "2" if tp == "Venda" else "1", "BR_NFPartner_1": cod_cli,
                        "BR_NFPartnerRegionCode": d_uf if tp == "Venda" else o_uf,
                        "BR_NFTotalAmount": f"{remessa:.2f}", "BR_NFPartnerName1": c["Nome da transportadora"],
                        "BR_NFIsCanceled": "true" if rnd.random() < 0.02 else "false",
                        "HeaderGrossWeight": f"{peso:.3f}", "HeaderWeightUnit": "KG"})
            n_nf += 1
        # distâncias já calculadas (85%); o resto fica para o botão "Calcular distâncias pendentes"
        if rnd.random() < 0.85 and c["UF (Desembarque):"] + c["Unidade de desembarque:"]:
            cache.append({"ID_Pipefy": c["Código"], "LAT_O": o_ll[0], "LON_O": o_ll[1], "LAT_D": d_ll[0], "LON_D": d_ll[1],
                          "KM_RODADO": round(km, 2), "FONTE_O": "UNIDADE" if emb_un else "CIDADE",
                          "FONTE_D": "UNIDADE" if des_un else "CIDADE"})

    df = pd.DataFrame(cards)

    # notas de saída sem card no Pipefy (o SAP tem mais notas que o Pipefy tem fretes)
    for _ in range(1400):
        d = cidade()
        t = transportadora_para(d[1])
        dt = INICIO + timedelta(days=rnd.uniform(0, dias))
        nfs.append({"BR_NotaFiscal": str(n_nf), "BR_NFIssueDate": ms(dt), "BR_NFDirection": rnd.choice(["2", "2", "1"]),
                    "BR_NFPartner_1": str(3000000 + rnd.randrange(len(CLIENTES))), "BR_NFPartnerRegionCode": d[1],
                    "BR_NFTotalAmount": f"{rnd.lognormvariate(9.2, 0.9):.2f}",
                    "BR_NFPartnerName1": "" if rnd.random() < 0.08 else t, "BR_NFIsCanceled": "false",
                    "HeaderGrossWeight": f"{rnd.lognormvariate(5.4, 1.0):.3f}", "HeaderWeightUnit": "KG"})
        n_nf += 1

    # CT-e recebidos (entrada; parceiro = transportadora; UF = filial que emitiu) e pagamentos (chave 25)
    pag = []
    cte = df[df.get("Valor CTE:").fillna("").astype(str) != ""].copy()
    cte["valor"] = cte["Valor CTE:"].astype(str).str.replace(",", ".").astype(float)
    cte["mes"] = pd.to_datetime(cte["Criado em"]).dt.to_period("M")
    for (t, mes), g in cte.groupby(["Nome da transportadora", "mes"]):
        cod, uf_filial, _ = TRANSP[t]
        for _, r in g.iterrows():
            nfs.append({"BR_NotaFiscal": str(n_nf), "BR_NFIssueDate": ms(pd.Timestamp(r["Criado em"]).to_pydatetime() + timedelta(days=3)),
                        "BR_NFDirection": "1", "BR_NFPartner_1": cod, "BR_NFPartnerRegionCode": uf_filial,
                        "BR_NFTotalAmount": f"{r['valor']:.2f}", "BR_NFPartnerName1": "", "BR_NFIsCanceled": "false",
                        "HeaderGrossWeight": "0", "HeaderWeightUnit": "KG"})
            n_nf += 1
        # fatura do mês paga no início do mês seguinte (fretes sem card entram com +15%)
        dia_pag = (mes + 1).to_timestamp() + timedelta(days=rnd.randint(4, 12))
        if dia_pag <= pd.Timestamp(FIM):
            pag.append((cod, t, round(g["valor"].sum() * rnd.uniform(1.05, 1.25), 2), dia_pag))
    meses = pd.period_range(INICIO, FIM, freq="M")
    outros = [("2000301", "MUDANÇAS BOA VIAGEM LTDA", 0.25, 2500, 9000), ("2000401", "GLOBAL EXPRESS COURIER LTDA", 0.6, 800, 6000),
              ("2000501", "TRADING EXEMPLO COMERCIO EXTERIOR LTDA", 0.8, 40000, 260000),
              ("2000502", "LOCADORA DE VEICULOS EXEMPLO S.A.", 0.9, 3000, 9000),
              ("2000503", "EMPRESA DO GRUPO EXEMPLO S.A.", 0.7, 10000, 60000),
              ("2000601", "J. M. TRANSPORTES ME", 0.3, 800, 3000),
              ("2000701", "NOVA CARGA TRANSPORTES LTDA", 0.25, 900, 4000)]
    for cod, nome, prob, a, b in outros:
        for m in meses:
            if rnd.random() < prob:
                dia = m.to_timestamp() + timedelta(days=rnd.randint(2, 26))
                if dia <= pd.Timestamp(FIM):
                    pag.append((cod, nome, round(rnd.uniform(a, b), 2), dia))
    fin = [{"Supplier": cod, "SupplierName": nome, "AmountInCompanyCodeCurrency": f"{v:.2f}", "PostingKey": "25",
            "PostingDate": ms(d.to_pydatetime() if hasattr(d, "to_pydatetime") else d), "AccountingDocumentType": "KZ"}
           for cod, nome, v, d in pag]
    # faturas (chave 31) também chegam na consulta e o painel precisa ignorá-las
    fin += [{**f, "PostingKey": "31", "AmountInCompanyCodeCurrency": "-" + f["AmountInCompanyCodeCurrency"],
             "AccountingDocumentType": "RE"} for f in fin[::3]]

    forn = [{"Supplier": cod, "Nome_SAP": nome, "Categoria": "Autônomo" if nome in AUTONOMOS else "Transportadora",
             "Nome_exibicao": nome.replace(" LTDA", "").replace(" CARGAS E ENCOMENDAS", " CARGAS").title()
             .replace("Autonomo", "Autônomo").replace("Rapido", "Rápido"), "Observacao": ""}
            for nome, (cod, _, _) in TRANSP.items()]
    forn += [
        {"Supplier": "2000301", "Nome_SAP": "MUDANÇAS BOA VIAGEM LTDA", "Categoria": "Mudança", "Nome_exibicao": "Mudanças Boa Viagem", "Observacao": "mudanças de colaboradores"},
        {"Supplier": "2000401", "Nome_SAP": "GLOBAL EXPRESS COURIER LTDA", "Categoria": "Internacional", "Nome_exibicao": "Global Express", "Observacao": "courier de amostras"},
        {"Supplier": "2000501", "Nome_SAP": "TRADING EXEMPLO COMERCIO EXTERIOR LTDA", "Categoria": "Fora: comércio exterior", "Nome_exibicao": "Trading Exemplo", "Observacao": "numerário de importação: impostos e mercadoria, não só frete"},
        {"Supplier": "2000502", "Nome_SAP": "LOCADORA DE VEICULOS EXEMPLO S.A.", "Categoria": "Fora: não é frete", "Nome_exibicao": "Locadora Exemplo", "Observacao": "aluguel de veículos"},
        {"Supplier": "2000503", "Nome_SAP": "EMPRESA DO GRUPO EXEMPLO S.A.", "Categoria": "Fora: intragrupo", "Nome_exibicao": "Empresa do grupo", "Observacao": "transferência entre empresas do grupo"},
        {"Supplier": "2000601", "Nome_SAP": "J. M. TRANSPORTES ME", "Categoria": "Revisar", "Nome_exibicao": "J. M. Transportes", "Observacao": "MEI: confirmar se é frete"},
    ]

    cid = pd.DataFrame(CIDADES, columns=["cidade", "uf", "lat", "lon"])
    df.to_csv(os.path.join(DEMO, "pipefy_relatorio.csv"), sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame(fat).to_csv(os.path.join(DEMO, "faturamento.csv"), sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame(nfs).to_csv(os.path.join(DEMO, "frete_nf.csv"), sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame(fin).to_csv(os.path.join(DEMO, "frete_itens_fornec.csv"), sep=";", index=False, encoding="utf-8-sig")
    cid.to_csv(os.path.join(DEMO, "cidades.csv"), sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame(cache).to_excel(os.path.join(DEMO, "distancias_cache.xlsx"), index=False)
    pd.DataFrame(forn).to_csv(os.path.join(RAIZ, "fornecedores_frete_exemplo.csv"), sep=";", index=False, encoding="utf-8-sig")
    print(f"{len(df)} cards · {len(fat)} faturas · {len(nfs)} notas · {len(fin)} partidas · {len(cache)} distâncias")


if __name__ == "__main__":
    main()
