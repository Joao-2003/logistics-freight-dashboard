import requests
import logging
import http.client as http_client

# ===========================================================
# CONFIGURAÇÃO DE LOGS (Essencial para a Infraestrutura)
# ===========================================================
# Ativa o debug na biblioteca padrão de HTTP do Python para ver detalhes da conexão
http_client.HTTPConnection.debuglevel = 1

# Configura o logger para salvar em arquivo e mostrar na tela
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("teste_apis_infra.log", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TesteInfra")
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

# ===========================================================
# CONFIGURAÇÕES DAS APIs
# ===========================================================
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
HEADERS = {"User-Agent": "logistica-dashboard/2.0 (seu-email@exemplo.com)"}

def testar_nominatim():
    logger.info("===" * 15)
    logger.info("INICIANDO TESTE 1: NOMINATIM (Geocodificação)")
    
    cidade, uf = "São Paulo", "SP"
    params = {"q": f"{cidade}, {uf}, Brasil", "format": "json", "limit": 1}
    
    logger.info(f"URL Alvo: {NOMINATIM_URL}")
    logger.info(f"Parâmetros: {params}")
    
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
        logger.info(f"Status Code HTTP: {response.status_code}")
        
        if response.status_code == 200:
            logger.info(f"Resposta JSON (Truncada): {str(response.json())[:200]}...")
            logger.info("✅ TESTE NOMINATIM BEM SUCEDIDO!")
        else:
            logger.warning(f"A API respondeu, mas com erro. Resposta: {response.text}")
            
    except requests.exceptions.ProxyError as e:
        logger.error(f"❌ ERRO DE PROXY BLOQUEANDO A REQUISIÇÃO: {e}")
    except requests.exceptions.SSLError as e:
        logger.error(f"❌ ERRO DE CERTIFICADO SSL (Firewall/Antivírus inspecionando): {e}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ ERRO DE CONEXÃO (Acesso negado ou sem internet): {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"❌ TEMPO ESGOTADO (Timeout - O firewall pode estar descartando pacotes silenciosamente): {e}")
    except Exception as e:
        logger.error(f"❌ ERRO DESCONHECIDO: {e}")

def testar_osrm():
    logger.info("===" * 15)
    logger.info("INICIANDO TESTE 2: OSRM (Roteamento de Distância)")
    
    # Coordenadas de teste: São Paulo (Origem) para Campinas (Destino)
    lon_o, lat_o = -46.6333, -23.5505
    lon_d, lat_d = -47.0608, -22.9099
    
    url_completa = f"{OSRM_URL}/{lon_o},{lat_o};{lon_d},{lat_d}?overview=false"
    logger.info(f"URL Alvo Completa: {url_completa}")
    
    try:
        # Nota: O OSRM é HTTP, não HTTPS, o que costuma ser bloqueado por políticas de segurança corporativas.
        response = requests.get(url_completa, timeout=15)
        logger.info(f"Status Code HTTP: {response.status_code}")
        
        if response.status_code == 200:
            logger.info(f"Resposta JSON (Truncada): {str(response.json())[:200]}...")
            logger.info("✅ TESTE OSRM BEM SUCEDIDO!")
        else:
            logger.warning(f"A API respondeu, mas com erro. Resposta: {response.text}")
            
    except requests.exceptions.ProxyError as e:
        logger.error(f"❌ ERRO DE PROXY BLOQUEANDO A REQUISIÇÃO: {e}")
    except requests.exceptions.SSLError as e:
        logger.error(f"❌ ERRO DE CERTIFICADO SSL: {e}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ ERRO DE CONEXÃO (Acesso negado ou sem internet): {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"❌ TEMPO ESGOTADO (Timeout - O firewall pode estar descartando pacotes silenciosamente): {e}")
    except Exception as e:
        logger.error(f"❌ ERRO DESCONHECIDO: {e}")

if __name__ == "__main__":
    logger.info("INICIANDO BATERIA DE TESTES PARA A INFRAESTRUTURA")
    testar_nominatim()
    testar_osrm()
    logger.info("===" * 15)
    logger.info("TESTES FINALIZADOS. Arquivo 'teste_apis_infra.log' gerado com sucesso.")