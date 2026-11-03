# Dashboard de logística e fretes

🇧🇷 Português | [🇺🇸 English](README.en.md)

Painel em Streamlit que reúne, em tempo de execução, as solicitações e cotações de frete do **Pipefy**, os dados de faturamento e de gasto com transportadoras do **SAP S/4HANA** e as distâncias das rotas (**OpenStreetMap + OSRM**), para acompanhar custo, saving, eficiência e prazos do transporte.

> Desenvolvido por mim para a área de Logística de uma indústria brasileira. Credenciais, IDs de pipe, nomes de transportadoras autônomas e unidades foram removidos ou trocados por exemplos.

## Fluxo de dados

1. **Pipefy (GraphQL, paginado):** solicitações de frete, cotações aprovadas e rejeitadas e centros de custo.
2. **SAP S/4HANA (OData):** peso bruto e volumes da nota fiscal de cada pedido, e o gasto líquido pago às transportadoras.
3. **Motor de distâncias:** Nominatim converte cidade e UF em coordenadas e o OSRM devolve a distância de estrada; cada rota calculada vai para um cache local em Excel, então o painel fica mais rápido a cada uso e respeita o limite das APIs gratuitas.
4. **Cruzamento em memória:** Pipefy × SAP pelo número do pedido normalizado, e solicitações × cotações × distâncias.

## Abas

| Aba | O que mostra |
|---|---|
| Resumo | Volume de solicitações, evolução diária, solicitantes e tipos de frete |
| Vendas e Compras | Fretes de saída e de entrada: valor, modalidade, clientes ou fornecedores e estados |
| Filial e Fábrica | Transferências entre unidades e principais fluxos |
| Marketing | Envios de material promocional, frota própria × terceiros |
| Cotações | Saving frente às cotações rejeitadas, desvio entre CT-e cobrado e cotação aprovada (verde, amarelo, vermelho) e R$/km por transportadora |
| Peso/Vol | Eficiência por R$/kg·km e R$/volume·km, com filtros para dados mal preenchidos |
| SLAs | Cards parados por fase, tempo médio por etapa e fretes fora do prazo |
| Centro de custo | Rateio do uso da frota própria entre os setores |

Limpeza de dados embutida: nomes de transportadoras padronizados, valores digitados com pontos e vírgulas misturados convertidos e códigos de cotação saneados antes do cruzamento.

## Como executar

```bash
pip install -r requirements.txt
cp .env.example .env    # preencha e exporte as variáveis (ex.: set -a; source .env; set +a)
streamlit run Dashboard_.py
```

`calcular_distancias.py` recalcula o cache de distâncias em lote e `teste_APIs.py` testa as APIs de geolocalização.

## Tecnologias

Python 3 · Streamlit · pandas · Plotly · requests · Pipefy GraphQL · SAP S/4HANA OData · OpenStreetMap Nominatim · OSRM · ViaCEP

## Autor

João Victor Guidi de Lima · [LinkedIn](https://www.linkedin.com/in/joão-lima-8b512) · [GitHub](https://github.com/Joao-2003)
