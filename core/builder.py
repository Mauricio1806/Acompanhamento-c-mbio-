"""
Módulo de geração de JSONs estáticos para o frontend.
Gera latest.json, history.json e ranking.json.
"""
import json
import os
from datetime import datetime
from core.db import get_cotacoes_dia, get_historico, get_menor_custo_30_dias
from core.calculator import gerar_ranking


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "data")


def ensure_output_dir():
    """Garante que o diretório de saída existe."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_latest_json(data=None):
    """
    Gera latest.json com a última coleta completa.
    """
    ensure_output_dir()
    
    if data is None:
        data = datetime.now().strftime("%Y-%m-%d")
    
    cotacoes = get_cotacoes_dia(data)
    menor_30d = get_menor_custo_30_dias()
    
    resultado = {
        "meta": {
            "data_coleta": data,
            "hora_atualizacao": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "total_casas": len(cotacoes),
            "moeda": "EUR",
            "cidade": "Salvador/BA",
            "menor_custo_30_dias": menor_30d
        },
        "cotacoes": []
    }
    
    for c in cotacoes:
        entry = {
            "casa_slug": c["casa_slug"],
            "nome": c["nome"],
            "endereco": c.get("endereco", ""),
            "bairro": c.get("bairro", ""),
            "tipo": c.get("tipo", ""),
            "horario": c.get("horario", ""),
            "telefone": c.get("telefone", ""),
            "whatsapp": c.get("whatsapp", ""),
            "google_maps": c.get("google_maps", ""),
            "formas_pagamento": c.get("formas_pagamento", "").split(",") if c.get("formas_pagamento") else [],
            "agendamento_acima": c.get("agendamento_acima"),
            "valor_venda_especie": c.get("valor_venda_especie"),
            "valor_venda_cartao": c.get("valor_venda_cartao"),
            "spread_ptax_pct": c.get("spread_ptax"),
            "spread_wise_pct": c.get("spread_wise"),
            "iof_especie_pct": 1.1,
            "custo_efetivo": c.get("custo_efetivo"),
            "variacao_dia_anterior_rs": c.get("variacao_dia_anterior"),
            "variacao_dia_anterior_pct": c.get("variacao_pct_dia_anterior"),
            "estoque_disponivel": bool(c.get("estoque_disponivel", 1)),
            "ptax_venda": c.get("ptax_venda"),
            "hora_coleta": c.get("hora", ""),
            "e_menor_30_dias": (
                c.get("custo_efetivo") == menor_30d 
                if menor_30d and c.get("custo_efetivo") else False
            ),
            "fonte": c.get("fonte", ""),
            "observacao": c.get("observacao", "")
        }
        resultado["cotacoes"].append(entry)
    
    filepath = os.path.join(OUTPUT_DIR, "latest.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    
    return filepath


def build_history_json(dias=90):
    """
    Gera history.json com série temporal.
    """
    ensure_output_dir()
    
    historico = get_historico(dias)
    
    # Agrupar por data
    por_data = {}
    for h in historico:
        data = h["data"]
        if data not in por_data:
            por_data[data] = {
                "data": data,
                "ptax": h.get("ptax_venda"),
                "casas": {}
            }
        por_data[data]["casas"][h["casa_slug"]] = {
            "nome": h["nome"],
            "valor_venda": h.get("valor_venda_especie"),
            "custo_efetivo": h.get("custo_efetivo"),
            "spread_ptax": h.get("spread_ptax")
        }
    
    resultado = {
        "meta": {
            "periodo_dias": dias,
            "total_registros": len(historico),
            "data_inicio": historico[0]["data"] if historico else None,
            "data_fim": historico[-1]["data"] if historico else None,
            "timestamp": datetime.now().isoformat()
        },
        "serie_temporal": list(por_data.values())
    }
    
    filepath = os.path.join(OUTPUT_DIR, "history.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    
    return filepath


def build_ranking_json(data=None, volumes=[5000, 10000, 20000]):
    """
    Gera ranking.json com top 3 e diferenças por volume.
    """
    ensure_output_dir()
    
    if data is None:
        data = datetime.now().strftime("%Y-%m-%d")
    
    cotacoes = get_cotacoes_dia(data)
    ranking = gerar_ranking(cotacoes, volumes)
    
    resultado = {
        "meta": {
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "volumes_referencia_eur": volumes,
            "moeda": "EUR",
            "cidade": "Salvador/BA"
        },
        "ranking": ranking
    }
    
    filepath = os.path.join(OUTPUT_DIR, "ranking.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    
    return filepath


def build_all(data=None):
    """Gera todos os JSONs."""
    latest = build_latest_json(data)
    history = build_history_json()
    ranking = build_ranking_json(data)
    return {
        "latest": latest,
        "history": history,
        "ranking": ranking
    }
