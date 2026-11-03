import pandas as pd
import requests
import time
import os

# ===========================================================
# CONFIGURAÇÕES GERAIS
# ===========================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL      = "https://routing.openstreetmap.de/routed-car/route/v1/driving"
VIACEP_URL    = "https://viacep.com.br/ws/{cep}/json/"

HEADERS = {
    "User-Agent": "logistica-dashboard/1.0 (seu-email@exemplo.com)"
}

# Caminho do arquivo de cache (relativo ao script)
CAMINHO_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "distancias_cache.xlsx")

# Coluna chave para identificar linhas únicas
# (mesma usada no Dashboard para o merge)
COLUNA_CHAVE = "Qual a cotação selecionada?"

# ===========================================================
# MAPA DE UNIDADES
# ===========================================================

UNIDADES = {
    "Empresa A MATRIZ":   ("Anápolis", "GO"),
    "Empresa A SP":       ("São Paulo",    "SP"),
    "CAMPO MAGRO":   ("Campo Magro",  "PR"),
    "Empresa A CURITIBA": ("Curitiba",     "PR"),
    "MARINGÁ":       ("Maringá",      "PR"),
}

# ===========================================================
# RESOLVER ORIGEM / DESTINO
# ===========================================================

def resolver_localizacao(row, tipo):
    if tipo == "origem":
        cidade  = row.get("Localidade (Embarque):")
        uf      = row.get("UF (Embarque):")
        unidade = row.get("Unidade de embarque:")
        cep     = row.get("CEP de embarque:")
    else:
        cidade  = row.get("Localidade (Desembarque):")
        uf      = row.get("UF (Desembarque):")
        unidade = row.get("Unidade de desembarque:")
        cep     = row.get("CEP de desembarque:")

    # Regra 1 – Cidade + UF
    if pd.notna(cidade) and pd.notna(uf):
        return cidade.strip(), uf.strip(), "CIDADE"

    # Regra 2 – Unidade conhecida
    if unidade in UNIDADES:
        return UNIDADES[unidade][0], UNIDADES[unidade][1], "UNIDADE"

    # Regra 3 – CEP via ViaCEP (fallback)
    cidade_cep, uf_cep = cidade_uf_por_cep(cep)
    if cidade_cep and uf_cep:
        return cidade_cep, uf_cep, "CEP"

    return None, None, "SEM_INFO"

# ===========================================================
# GEOCODIFICAÇÃO COM CACHE EM MEMÓRIA
# ===========================================================

_geocache = {}  # evita chamar a API duas vezes para a mesma cidade/UF
_cepcache = {}  # evita chamar ViaCEP duas vezes para o mesmo CEP

# ===========================================================
# LOOKUP DE CEP VIA VIACEP (cidade+UF a partir do CEP)
# ===========================================================

def normalizar_cep(cep):
    """Remove pontos, traços e zeros decimais — retorna string de 8 dígitos."""
    if pd.isna(cep):
        return None
    cep = str(cep).strip()
    # Remover ".0" gerado pelo Excel ao ler número
    if cep.endswith(".0"):
        cep = cep[:-2]
    cep = "".join([c for c in cep if c.isdigit()])
    return cep.zfill(8) if len(cep) <= 8 else None

def cidade_uf_por_cep(cep_raw):
    """
    Consulta ViaCEP e retorna (cidade, uf) ou (None, None) em caso de falha.
    Usa cache em memória para evitar chamadas repetidas.
    """
    cep = normalizar_cep(cep_raw)
    if not cep:
        return None, None

    if cep in _cepcache:
        return _cepcache[cep]

    try:
        r = requests.get(
            VIACEP_URL.format(cep=cep),
            headers=HEADERS,
            timeout=10
        )
        data = r.json()

        if "erro" in data or "localidade" not in data:
            resultado = (None, None)
        else:
            resultado = (data["localidade"].strip(), data["uf"].strip())

    except Exception:
        resultado = (None, None)

    _cepcache[cep] = resultado
    time.sleep(0.2)  # rate-limit gentil no ViaCEP
    return resultado

def geocodificar_cidade(cidade, uf):
    if not cidade or not uf:
        return None, None, "SEM_DADOS"

    chave = f"{cidade.strip().upper()}|{uf.strip().upper()}"

    if chave in _geocache:
        return _geocache[chave]

    params = {
        "q":      f"{cidade}, {uf}, Brasil",
        "format": "json",
        "limit":  1
    }

    try:
        r    = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
        data = r.json()

        if not data:
            resultado = (None, None, "NAO_ENCONTRADO")
        else:
            resultado = (float(data[0]["lat"]), float(data[0]["lon"]), "OK")

    except Exception as e:
        resultado = (None, None, f"ERRO_{e}")

    _geocache[chave] = resultado
    return resultado

# ===========================================================
# DISTÂNCIA RODOVIÁRIA REAL — OSRM
# ===========================================================

def calcular_distancia_osrm(lat_o, lon_o, lat_d, lon_d):
    if None in [lat_o, lon_o, lat_d, lon_d]:
        return None

    url = f"{OSRM_URL}/{lon_o},{lat_o};{lon_d},{lat_d}?overview=false"

    try:
        r    = requests.get(url, timeout=15)
        data = r.json()

        if data.get("code") != "Ok":
            print(f"\n    ⚠️  OSRM retornou code={data.get('code')} | message={data.get('message','')}")
            return None

        metros = data["routes"][0]["distance"]
        return round(metros / 1000, 2)

    except Exception as e:
        print(f"\n    ⚠️  OSRM erro: {e}")
        return None

# ===========================================================
# PROCESSAMENTO INCREMENTAL (NÚCLEO DA OTIMIZAÇÃO)
# ===========================================================

def calcular_distancias_incremental(df_novo, caminho_cache=CAMINHO_CACHE):
    """
    Compara df_novo com o cache existente.
    Processa APENAS as linhas novas ou que ainda não têm KM_RODADO.
    Retorna o DataFrame completo (cache antigo + novas linhas calculadas).
    """

    # ----------------------------------------------------------
    # 1) Normalizar chave de cotação (mesma lógica do Dashboard)
    # ----------------------------------------------------------
    def normalizar_chave(v):
        if pd.isna(v):
            return ""
        v = str(v).strip()
        for lixo in [" ", "\n", "\t", "\xa0", ","]:
            v = v.replace(lixo, "")
        if v.endswith(".0"):
            v = v[:-2]
        if v.endswith("."):
            v = v[:-1]
        try:
            if "e" in v.lower():
                v = str(int(float(v)))
        except:
            pass
        return v.strip()

    df_novo["_chave"] = df_novo[COLUNA_CHAVE].apply(normalizar_chave)

    # ----------------------------------------------------------
    # 2) Carregar cache existente (se houver)
    # ----------------------------------------------------------
    if os.path.exists(caminho_cache):
        df_cache = pd.read_excel(caminho_cache)
        df_cache["_chave"] = df_cache[COLUNA_CHAVE].apply(normalizar_chave)
        chaves_com_km = set(
            df_cache.loc[df_cache["KM_RODADO"].notna(), "_chave"]
        )
        print(f"✅ Cache carregado: {len(df_cache)} linhas, {len(chaves_com_km)} com KM calculado.")
    else:
        df_cache        = pd.DataFrame()
        chaves_com_km   = set()
        print("⚠️  Cache não encontrado — processando tudo do zero.")

    # ----------------------------------------------------------
    # 3) Identificar linhas que precisam ser calculadas
    # ----------------------------------------------------------
    df_pendentes = df_novo[~df_novo["_chave"].isin(chaves_com_km)].copy()
    df_pendentes = df_pendentes[df_pendentes["_chave"] != ""]  # ignorar sem chave

    total_pendentes = len(df_pendentes)
    print(f"🔢 Linhas pendentes (novas ou sem KM): {total_pendentes}")

    if total_pendentes == 0:
        print("🎉 Nenhuma linha nova — cache já está atualizado!")
        return df_cache.drop(columns=["_chave"], errors="ignore")

    # ----------------------------------------------------------
    # 4) Inicializar colunas de resultado nas pendentes
    # ----------------------------------------------------------
    for col in ["LAT_O", "LON_O", "LAT_D", "LON_D", "KM_RODADO", "FONTE_O", "FONTE_D"]:
        if col not in df_pendentes.columns:
            df_pendentes[col] = None

    # ----------------------------------------------------------
    # 5) Processar somente as pendentes
    # ----------------------------------------------------------
    resumo = {
        "total_pendentes":    total_pendentes,
        "origem_resolvida":   0,
        "origem_via_cep":     0,
        "destino_resolvido":  0,
        "destino_via_cep":    0,
        "geocode_ok":         0,
        "km_calculado":       0,
        "erros":              0,
    }

    for idx, (i, row) in enumerate(df_pendentes.iterrows()):

        # Progresso a cada 10 linhas
        if idx % 10 == 0:
            print(f"  ⏳ Processando {idx + 1}/{total_pendentes}...", end="\r")

        # Origem
        cidade_o, uf_o, fonte_o = resolver_localizacao(row, "origem")
        if cidade_o:
            resumo["origem_resolvida"] += 1
            if fonte_o == "CEP":
                resumo["origem_via_cep"] += 1
        lat_o, lon_o, status_o = geocodificar_cidade(cidade_o, uf_o)
        time.sleep(1)  # respeitar rate-limit do Nominatim

        # Destino
        cidade_d, uf_d, fonte_d = resolver_localizacao(row, "destino")
        if cidade_d:
            resumo["destino_resolvido"] += 1
            if fonte_d == "CEP":
                resumo["destino_via_cep"] += 1
        lat_d, lon_d, status_d = geocodificar_cidade(cidade_d, uf_d)
        time.sleep(1)

        if status_o == "OK" and status_d == "OK":
            resumo["geocode_ok"] += 1

        km = calcular_distancia_osrm(lat_o, lon_o, lat_d, lon_d)

        if km:
            resumo["km_calculado"] += 1
        else:
            resumo["erros"] += 1

        df_pendentes.at[i, "LAT_O"]      = lat_o
        df_pendentes.at[i, "LON_O"]      = lon_o
        df_pendentes.at[i, "LAT_D"]      = lat_d
        df_pendentes.at[i, "LON_D"]      = lon_d
        df_pendentes.at[i, "KM_RODADO"]  = km
        df_pendentes.at[i, "FONTE_O"]    = fonte_o
        df_pendentes.at[i, "FONTE_D"]    = fonte_d

    print(f"\n✅ Processamento concluído.")

    # ----------------------------------------------------------
    # 6) Mesclar cache antigo + novas linhas calculadas
    # ----------------------------------------------------------
    if not df_cache.empty:
        # Alinhar colunas antes do concat para evitar FutureWarning
        df_cache_out    = df_cache.drop(columns=["_chave"], errors="ignore")
        df_pendentes_out = df_pendentes.drop(columns=["_chave"], errors="ignore")

        # Garantir que colunas numéricas de resultado tenham dtype float explícito
        for col in ["LAT_O", "LON_O", "LAT_D", "LON_D", "KM_RODADO"]:
            if col in df_cache_out.columns:
                df_cache_out[col] = pd.to_numeric(df_cache_out[col], errors="coerce")
            if col in df_pendentes_out.columns:
                df_pendentes_out[col] = pd.to_numeric(df_pendentes_out[col], errors="coerce")

        df_final = pd.concat(
            [df_cache_out, df_pendentes_out],
            ignore_index=True
        )
    else:
        df_final = df_pendentes.drop(columns=["_chave"], errors="ignore")

    return df_final, resumo

# ===========================================================
# SCRIPT DE EXECUÇÃO
# ===========================================================

if __name__ == "__main__":

    ARQUIVO_SOLICITACOES = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dados",
        "Solicitacoes.xlsx"
    )

    print("📥 Carregando base de solicitações...")
    df = pd.read_excel(ARQUIVO_SOLICITACOES)
    print(f"📊 Registros totais: {len(df)}")

    df_resultado, resumo = calcular_distancias_incremental(df)

    print("\n📈 RESUMO DO PROCESSAMENTO")
    for k, v in resumo.items():
        print(f"  {k}: {v}")

    df_resultado.to_excel(CAMINHO_CACHE, index=False)
    print(f"\n💾 Cache atualizado: {CAMINHO_CACHE}")