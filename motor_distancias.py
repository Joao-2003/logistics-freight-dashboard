"""Motor de distâncias: km rodado de cada frete do Pipefy (Nominatim + OSRM), com cache em Excel.

Por que parou de atualizar na versão antiga:
1. Uma falha de geocodificação ficava guardada na memória do servidor até ele reiniciar.
   Bastava o Nominatim recusar uma vez a cidade da matriz para quase todo frete ficar sem km
   dali em diante (só 5 a 17 fretes por mês ganhavam distância).
2. O cálculo só rodava quando alguém abria o dashboard, preso ao cache diário do Streamlit.

Agora:
- as unidades do grupo têm coordenadas fixas (não dependem do Nominatim);
- falhas não ficam guardadas: cada execução tenta de novo;
- se o Nominatim ou o OSRM bloquear (429/403), a execução para e retoma na próxima;
- o script atualizar_distancias.py roda todo dia (systemd timer ou cron), independente de visitas;
- no modo de demonstração não há rede: as coordenadas vêm de demo/cidades.csv e a distância de
  estrada é estimada pela linha reta × 1,27 (fator médio de sinuosidade das rodovias).
"""
import math
import os
import time
from datetime import datetime

import pandas as pd
import requests

from config import CACHE_DISTANCIAS, DEMO_DIR, UNIDADES

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
HEADERS_GEO = {"User-Agent": "logistics-freight-dashboard/4.0 (contato@exemplo.com.br)"}  # use um contato real
FATOR_ESTRADA = 1.27
COLS_MOTOR = ["LAT_O", "LON_O", "LAT_D", "LON_D", "KM_RODADO", "FONTE_O", "FONTE_D"]


class Bloqueado(Exception):
    """O serviço de mapas pediu para parar (limite de uso)."""


def _vazio(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "None", "0.0")


def resolver_localizacao(row, tipo):
    sufixo = "Embarque" if tipo == "origem" else "Desembarque"
    cidade, uf = row.get(f"Localidade ({sufixo}):"), row.get(f"UF ({sufixo}):")
    unidade = row.get(f"Unidade de {sufixo.lower()}:")
    endereco, cep = row.get(f"Endereço de {sufixo.lower()}:"), row.get(f"CEP de {sufixo.lower()}:")
    if not _vazio(cidade) and not _vazio(uf):
        return str(cidade).strip(), str(uf).strip(), "CIDADE"
    if not _vazio(unidade) and str(unidade).strip().upper() in UNIDADES:
        u = UNIDADES[str(unidade).strip().upper()]
        return u[0], u[1], "UNIDADE"
    if not _vazio(endereco):
        return str(endereco).strip().replace("\n", ", "), "", "ENDERECO"
    if not _vazio(cep):
        return str(cep).strip(), "", "CEP"
    return None, None, "SEM_INFO"


class Motor:
    def __init__(self, max_consultas=400, log=print):
        self.geo, self.rota = {}, {}
        self.consultas, self.max_consultas, self.log = 0, max_consultas, log
        for u in UNIDADES.values():
            self.geo[f"{u[0].upper()}-{u[1].upper()}"] = (u[2], u[3])
        self.simulado = bool(DEMO_DIR)
        self.cidades = {}
        arq = os.path.join(DEMO_DIR, "cidades.csv") if DEMO_DIR else ""
        if arq and os.path.exists(arq):
            c = pd.read_csv(arq, sep=";", encoding="utf-8-sig")
            self.cidades = {f"{a.upper()}-{b.upper()}": (float(la), float(lo))
                            for a, b, la, lo in zip(c["cidade"], c["uf"], c["lat"], c["lon"])}

    # --- geocodificação: só sucessos vão para o cache ---
    def geocodificar(self, cidade, uf):
        if not cidade:
            return None, None
        chave = f"{str(cidade).upper()}-{str(uf).upper()}"
        if chave in self.geo:
            return self.geo[chave]
        if self.consultas >= self.max_consultas:
            return None, None
        self.consultas += 1
        if self.simulado:  # demonstração: sem rede
            if chave not in self.cidades:
                return None, None
            self.geo[chave] = self.cidades[chave]
            return self.geo[chave]
        q = f"{cidade}, {uf}, Brasil" if uf else f"{cidade}, Brasil"
        try:
            r = requests.get(NOMINATIM_URL, params={"q": q, "format": "json", "limit": 1, "countrycodes": "br"},
                             headers=HEADERS_GEO, timeout=15)
            time.sleep(1.1)  # política do Nominatim: no máximo 1 consulta por segundo
            if r.status_code in (403, 429):
                raise Bloqueado(f"Nominatim HTTP {r.status_code}")
            dados = r.json() if r.status_code == 200 else []
        except requests.RequestException as e:
            self.log(f"  Nominatim falhou para {q}: {e}")
            return None, None
        if not dados:
            return None, None
        self.geo[chave] = (float(dados[0]["lat"]), float(dados[0]["lon"]))
        return self.geo[chave]

    def distancia(self, lat_o, lon_o, lat_d, lon_d):
        if None in (lat_o, lon_o, lat_d, lon_d):
            return None
        chave = f"{lat_o:.5f},{lon_o:.5f}_{lat_d:.5f},{lon_d:.5f}"
        if chave in self.rota:
            return self.rota[chave]
        if self.simulado:  # demonstração: linha reta (haversine) × fator de estrada
            p1, p2 = math.radians(lat_o), math.radians(lat_d)
            a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon_d - lon_o) / 2) ** 2
            self.rota[chave] = round(2 * 6371 * math.asin(math.sqrt(a)) * FATOR_ESTRADA, 2)
            return self.rota[chave]
        try:
            r = requests.get(f"{OSRM_URL}/{lon_o},{lat_o};{lon_d},{lat_d}", params={"overview": "false"},
                             headers=HEADERS_GEO, timeout=20)
            if r.status_code in (403, 429):
                raise Bloqueado(f"OSRM HTTP {r.status_code}")
            dados = r.json()
        except (requests.RequestException, ValueError) as e:
            self.log(f"  OSRM falhou: {e}")
            return None
        if dados.get("code") != "Ok":
            return None
        km = round(dados["routes"][0]["distance"] / 1000, 2)
        self.rota[chave] = km
        return km

    # --- histórico salvo ---
    def carregar_historico(self, df_cache):
        hist = {}
        for _, row in df_cache.iterrows():
            if pd.isna(row.get("KM_RODADO")):
                continue
            hist[str(row.get("ID_Pipefy", "")).strip()] = {c: row.get(c) for c in COLS_MOTOR}
            for tipo, la, lo in (("origem", "LAT_O", "LON_O"), ("destino", "LAT_D", "LON_D")):
                c, uf, _ = resolver_localizacao(row, tipo)
                if c and pd.notna(row.get(la)):
                    self.geo.setdefault(f"{str(c).upper()}-{str(uf).upper()}", (row[la], row[lo]))
        return hist


def atualizar(df_cards, caminho=CACHE_DISTANCIAS, max_consultas=400, log=print):
    """Completa o KM dos cards sem distância e grava o cache. Devolve um resumo."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    df = df_cards.copy()
    df["ID_Pipefy"] = df["ID_Pipefy"].astype(str).str.strip()
    motor = Motor(max_consultas=max_consultas, log=log)
    hist = motor.carregar_historico(pd.read_excel(caminho)) if os.path.exists(caminho) else {}
    for c in COLS_MOTOR:
        df[c] = None
    for i, idc in df["ID_Pipefy"].items():
        if idc in hist:
            for c, v in hist[idc].items():
                df.at[i, c] = v

    novos, sem_info, motivo = 0, 0, ""
    try:
        for i, row in df[df["KM_RODADO"].isna()].iterrows():
            c_o, uf_o, f_o = resolver_localizacao(row, "origem")
            c_d, uf_d, f_d = resolver_localizacao(row, "destino")
            if not c_o or not c_d:
                sem_info += 1
                continue
            lat_o, lon_o = motor.geocodificar(c_o, uf_o)
            lat_d, lon_d = motor.geocodificar(c_d, uf_d)
            km = motor.distancia(lat_o, lon_o, lat_d, lon_d)
            if km is not None:
                df.loc[i, COLS_MOTOR] = [lat_o, lon_o, lat_d, lon_d, km, f_o, f_d]
                novos += 1
                if novos % 200 == 0:
                    df.to_excel(caminho, index=False)
            if motor.consultas >= motor.max_consultas:
                motivo = f"limite de {motor.max_consultas} consultas ao Nominatim nesta execução"
                break
    except Bloqueado as e:
        motivo = str(e)
    df.to_excel(caminho, index=False)
    faltam = int(df["KM_RODADO"].isna().sum())
    resumo = {"quando": datetime.now().strftime("%d/%m/%Y %H:%M"), "novos_km": novos, "sem_km": faltam,
              "sem_origem_ou_destino": sem_info, "consultas_nominatim": motor.consultas, "parou_por": motivo}
    log(f"Distâncias: {novos} novas, {faltam} cards ainda sem km ({sem_info} sem origem ou destino no card). {motivo}")
    return resumo
