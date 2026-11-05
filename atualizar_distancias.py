"""Atualização diária das distâncias (rodar pelo cron, independente de alguém abrir o dashboard).

Uso:
    python atualizar_distancias.py [limite_de_consultas]
Agendamento diário, por exemplo com cron (5h40):
    40 5 * * * cd /caminho/do/dashboard && venv/bin/python atualizar_distancias.py >> dados/distancias.log 2>&1
ou com um systemd timer (OnCalendar=*-*-* 05:40:00) chamando um serviço oneshot com o mesmo comando.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CACHE_DISTANCIAS, DIR_DADOS  # noqa: E402
from fontes import carregar_pipefy  # noqa: E402
from motor_distancias import atualizar  # noqa: E402

if __name__ == "__main__":
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    cards, _ = carregar_pipefy()
    print(f"{len(cards)} cards no Pipefy")
    resumo = atualizar(cards, CACHE_DISTANCIAS, max_consultas=limite)
    with open(os.path.join(DIR_DADOS, "distancias_status.json"), "w", encoding="utf-8") as fh:
        json.dump(resumo, fh, ensure_ascii=False)
