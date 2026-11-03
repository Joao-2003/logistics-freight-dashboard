# Logistics and freight dashboard

[🇧🇷 Português](README.md) | 🇺🇸 English

A Streamlit dashboard that combines, at runtime, freight requests and quotes from **Pipefy**, billing and carrier spend data from **SAP S/4HANA** and route distances (**OpenStreetMap + OSRM**) to track transport cost, savings, efficiency and lead times.

> I built it for the Logistics team of a Brazilian manufacturer. Credentials, pipe IDs, independent carrier names and site names were removed or replaced with examples.

## Data flow

1. **Pipefy (GraphQL, paginated):** freight requests, approved and rejected quotes and cost centers.
2. **SAP S/4HANA (OData):** gross weight and volumes from each order's invoice, and the net amount paid to carriers.
3. **Distance engine:** Nominatim turns city and state into coordinates and OSRM returns the driving distance; every computed route goes into a local Excel cache, so the dashboard gets faster with use and stays within the free APIs' limits.
4. **In-memory merge:** Pipefy × SAP by normalized order number, then requests × quotes × distances.

## Tabs

| Tab | What it shows |
|---|---|
| Summary | Request volume, daily trend, requesters and freight types |
| Sales and Purchasing | Outbound and inbound freight: value, mode, customers or suppliers and states |
| Branch and Plant | Transfers between sites and main flows |
| Marketing | Promotional shipments, own fleet × third parties |
| Quotes | Savings versus rejected quotes, gap between the billed CT-e and the approved quote (green, yellow, red) and BRL/km per carrier |
| Weight/Volume | Efficiency in BRL/kg·km and BRL/volume·km, with filters for badly filled data |
| SLAs | Cards stuck per phase, average time per step and late shipments |
| Cost center | Allocation of own-fleet usage across departments |

Built-in data cleaning: carrier names are standardized, amounts typed with mixed dots and commas are converted and quote codes are sanitized before merging.

## How to run

```bash
pip install -r requirements.txt
cp .env.example .env    # fill it in and export the variables (e.g. set -a; source .env; set +a)
streamlit run Dashboard_.py
```

`calcular_distancias.py` rebuilds the distance cache in batch and `teste_APIs.py` tests the geolocation APIs.

## Tech stack

Python 3 · Streamlit · pandas · Plotly · requests · Pipefy GraphQL · SAP S/4HANA OData · OpenStreetMap Nominatim · OSRM · ViaCEP

## Author

João Victor Guidi de Lima · [LinkedIn](https://www.linkedin.com/in/joão-lima-8b512) · [GitHub](https://github.com/Joao-2003)
