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
    get_todas_casas, get_ultima_cotacao_data,
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

    cotacoes_hoje = {c["casa_slug"]: c for c in get_cotacoes_dia(data)}
    todas_casas = get_todas_casas()
    menor_30 = get_menor_custo_30_dias()

    cotacoes_payload = []
    for casa in todas_casas:
        slug = casa["slug"]
        c = cotacoes_hoje.get(slug)

        if c:
            # tem cotacao hoje
            entry = {
                "casa_slug": slug,
                "nome": c.get("nome") or casa.get("nome"),
                "cobertura": casa.get("cobertura"),
                "endereco": casa.get("endereco"),
                "bairro": casa.get("bairro"),
                "tipo": casa.get("tipo"),
                "horario": casa.get("horario"),
                "telefone": casa.get("telefone"),
                "whatsapp": casa.get("whatsapp"),
                "google_maps": casa.get("google_maps"),
                "cotacao_url": casa.get("cotacao_url"),
                "formas_pagamento": (casa.get("formas_pagamento") or "").split(",") if casa.get("formas_pagamento") else [],
                "agendamento_acima": casa.get("agendamento_acima"),
                "valor_venda_especie": c.get("valor_venda_especie"),
                "valor_venda_cartao": c.get("valor_venda_cartao"),
                "spread_ptax_pct": c.get("spread_ptax"),
                "spread_wise_pct": c.get("spread_wise"),
                "iof_especie_pct": c.get("iof_especie"),
                "custo_efetivo": c.get("custo_efetivo"),
                "variacao_dia_anterior_rs": c.get("variacao_dia_anterior"),
                "variacao_dia_anterior_pct": c.get("variacao_pct_dia_anterior"),
                "ptax_venda": c.get("ptax_venda"),
                "wise_rate": c.get("wise_rate"),
                "hora_coleta": c.get("hora"),
                "sem_cotacao_hoje": False,
                "e_menor_30_dias": (
                    menor_30 is not None and c.get("custo_efetivo") is not None
                    and abs(c["custo_efetivo"] - menor_30) < 1e-6
                ),
                "fonte": c.get("fonte"),
                "observacao": c.get("observacao"),
            }
        else:
            # sem cotacao hoje - mostra ultima conhecida (se houver) + dados cadastrais
            ultima = get_ultima_cotacao_data(slug)
            entry = {
                "casa_slug": slug,
                "nome": casa.get("nome"),
                "cobertura": casa.get("cobertura"),
                "endereco": casa.get("endereco"),
                "bairro": casa.get("bairro"),
                "tipo": casa.get("tipo"),
                "horario": casa.get("horario"),
                "telefone": casa.get("telefone"),
                "whatsapp": casa.get("whatsapp"),
                "google_maps": casa.get("google_maps"),
                "cotacao_url": casa.get("cotacao_url"),
                "formas_pagamento": (casa.get("formas_pagamento") or "").split(",") if casa.get("formas_pagamento") else [],
                "agendamento_acima": casa.get("agendamento_acima"),
                "valor_venda_especie": ultima.get("valor_venda_especie") if ultima else None,
                "valor_venda_cartao": ultima.get("valor_venda_cartao") if ultima else None,
                "spread_ptax_pct": ultima.get("spread_ptax") if ultima else None,
                "spread_wise_pct": ultima.get("spread_wise") if ultima else None,
                "iof_especie_pct": ultima.get("iof_especie") if ultima else None,
                "custo_efetivo": ultima.get("custo_efetivo") if ultima else None,
                "variacao_dia_anterior_rs": None,
                "variacao_dia_anterior_pct": None,
                "ptax_venda": ultima.get("ptax_venda") if ultima else None,
                "wise_rate": ultima.get("wise_rate") if ultima else None,
                "hora_coleta": None,
                "sem_cotacao_hoje": True,
                "ultima_cotacao_data": ultima.get("data") if ultima else None,
                "e_menor_30_dias": False,
                "fonte": ultima.get("fonte") if ultima else None,
                "observacao": "Sem coleta hoje. Consulte pelo botao de WhatsApp/site." if not ultima
                              else f"Ultima cotacao conhecida em {ultima.get('data')}",
            }
        cotacoes_payload.append(entry)

    com_cot = sum(1 for c in cotacoes_payload if not c["sem_cotacao_hoje"])
    payload = {
        "meta": {
            "data_coleta": data,
            "hora_atualizacao": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total_casas": len(cotacoes_payload),
            "casas_com_cotacao_hoje": com_cot,
            "casas_sem_cotacao_hoje": len(cotacoes_payload) - com_cot,
            "moeda": "EUR",
            "cidade": "Salvador/BA",
            "menor_custo_30_dias": menor_30,
        },
        "cotacoes": cotacoes_payload,
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
