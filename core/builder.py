"""
Geracao dos JSONs estaticos consumidos pelo dashboard (GitHub Pages).
Arquivos gerados em docs/data/:
- latest.json: cotacoes do dia + metadados
- history.json: serie temporal (ate 90 dias)
- ranking.json: top 3 e diferencas por volume
"""
import json
import os
from datetime import datetime

from core.db import (
    get_cotacoes_dia, get_historico, get_menor_custo_30_dias,
)
from core.calculator import gerar_ranking


OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "data",
)


def _ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_latest_json(data: str | None = None) -> str:
    _ensure_dir()
    if data is None:
        data = datetime.now().strftime("%Y-%m-%d")

    cotacoes = get_cotacoes_dia(data)
    menor_30 = get_menor_custo_30_dias()

    payload = {
        "meta": {
            "data_coleta": data,
            "hora_atualizacao": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total_casas": len(cotacoes),
            "moeda": "EUR",
            "cidade": "Salvador/BA",
            "menor_custo_30_dias": menor_30,
        },
        "cotacoes": [
            {
                "casa_slug": c["casa_slug"],
                "nome": c.get("nome"),
                "endereco": c.get("endereco"),
                "bairro": c.get("bairro"),
                "tipo": c.get("tipo"),
                "horario": c.get("horario"),
                "telefone": c.get("telefone"),
                "whatsapp": c.get("whatsapp"),
                "google_maps": c.get("google_maps"),
                "formas_pagamento": (c.get("formas_pagamento") or "").split(",") if c.get("formas_pagamento") else [],
                "agendamento_acima": c.get("agendamento_acima"),
                "valor_venda_especie": c.get("valor_venda_especie"),
                "valor_venda_cartao": c.get("valor_venda_cartao"),
                "spread_ptax_pct": c.get("spread_ptax"),
                "spread_wise_pct": c.get("spread_wise"),
                "iof_especie_pct": c.get("iof_especie"),
                "custo_efetivo": c.get("custo_efetivo"),
                "variacao_dia_anterior_rs": c.get("variacao_dia_anterior"),
                "variacao_dia_anterior_pct": c.get("variacao_pct_dia_anterior"),
                "ptax_venda": c.get("ptax_venda"),
                "hora_coleta": c.get("hora"),
                "e_menor_30_dias": (
                    menor_30 is not None
                    and c.get("custo_efetivo") is not None
                    and abs(c["custo_efetivo"] - menor_30) < 1e-6
                ),
                "fonte": c.get("fonte"),
                "observacao": c.get("observacao"),
            }
            for c in cotacoes
        ],
    }

    path = os.path.join(OUTPUT_DIR, "latest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def build_history_json(dias: int = 90) -> str:
    _ensure_dir()
    hist = get_historico(dias)

    por_data: dict[str, dict] = {}
    for h in hist:
        d = h["data"]
        if d not in por_data:
            por_data[d] = {"data": d, "ptax": h.get("ptax_venda"), "casas": {}}
        por_data[d]["casas"][h["casa_slug"]] = {
            "nome": h.get("nome"),
            "valor_venda": h.get("valor_venda_especie"),
            "custo_efetivo": h.get("custo_efetivo"),
            "spread_ptax": h.get("spread_ptax"),
        }

    payload = {
        "meta": {
            "periodo_dias": dias,
            "total_registros": len(hist),
            "data_inicio": hist[0]["data"] if hist else None,
            "data_fim": hist[-1]["data"] if hist else None,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        },
        "serie_temporal": list(por_data.values()),
    }

    path = os.path.join(OUTPUT_DIR, "history.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def build_ranking_json(data: str | None = None, volumes: list[int] | None = None) -> str:
    _ensure_dir()
    if data is None:
        data = datetime.now().strftime("%Y-%m-%d")
    if volumes is None:
        volumes = [5000, 10000, 20000]

    cotacoes = get_cotacoes_dia(data)
    ranking = gerar_ranking(cotacoes, volumes)

    payload = {
        "meta": {
            "data": data,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "volumes_referencia_eur": volumes,
            "moeda": "EUR",
            "cidade": "Salvador/BA",
        },
        "ranking": ranking,
    }

    path = os.path.join(OUTPUT_DIR, "ranking.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def build_all(data: str | None = None) -> dict[str, str]:
    return {
        "latest": build_latest_json(data),
        "history": build_history_json(),
        "ranking": build_ranking_json(data),
    }
