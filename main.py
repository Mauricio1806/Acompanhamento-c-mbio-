#!/usr/bin/env python3
"""
Script principal do Monitor de Câmbio EUR/BRL - Salvador, BA.
Executa o ciclo completo: scraping → cálculos → banco de dados → JSONs.

Uso:
    python main.py                    # Execução completa
    python main.py --init             # Apenas inicializar banco
    python main.py --build-json       # Apenas gerar JSONs
    python main.py --import-data FILE # Importar dados de arquivo JSON
"""
import sys
import os
import json
import yaml
import argparse
from datetime import datetime

# Adicionar diretório raiz ao path
sys.path.insert(0, os.path.dirname(__file__))

from core.db import (
    init_db, upsert_casa_cambio, insert_cotacao,
    get_ultima_cotacao, vacuum_db, limpar_historico_antigo
)
from core.calculator import (
    calcular_custo_efetivo, calcular_spread_ptax,
    calcular_spread_wise, calcular_variacao, verificar_discrepancia
)
from core.builder import build_all
from scrapers.bcb_ptax import get_ptax_eur, get_wise_rate


def load_config():
    """Carrega configuração do config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_casas_cambio(config):
    """Inicializa/atualiza dados cadastrais das casas de câmbio."""
    for casa in config.get("casas_cambio", []):
        upsert_casa_cambio(casa)
    print(f"[OK] {len(config.get('casas_cambio', []))} casas de câmbio cadastradas.")


def coletar_referencias():
    """Coleta PTAX e Wise como referências."""
    hoje = datetime.now().strftime("%m-%d-%Y")
    
    ptax = get_ptax_eur(hoje)
    wise = get_wise_rate()
    
    ptax_venda = ptax["cotacao_venda"] if ptax else None
    wise_rate = wise["rate"] if wise else None
    
    print(f"[PTAX] EUR/BRL venda: {ptax_venda}")
    print(f"[Wise] EUR/BRL: {wise_rate}")
    
    return ptax_venda, wise_rate


def processar_cotacao(casa_slug, valor_venda, ptax_venda, wise_rate, config, 
                      valor_cartao=None, fonte="scraping", observacao=""):
    """
    Processa e salva uma cotação individual.
    """
    iof_especie = config["iof"]["especie"]
    
    # Cálculos
    custo_efetivo = calcular_custo_efetivo(valor_venda, iof_especie)
    spread_ptax = calcular_spread_ptax(valor_venda, ptax_venda)
    spread_wise = calcular_spread_wise(valor_venda, wise_rate)
    
    # Variação vs dia anterior
    ultima = get_ultima_cotacao(casa_slug)
    var_rs, var_pct = (None, None)
    if ultima and ultima.get("valor_venda_especie"):
        var_rs, var_pct = calcular_variacao(valor_venda, ultima["valor_venda_especie"])
    
    # Verificar discrepância
    discrepancia = verificar_discrepancia(
        valor_venda, ptax_venda, config.get("max_spread_ptax", 3.0)
    )
    if discrepancia:
        obs_extra = f" [ALERTA: spread >{config.get('max_spread_ptax', 3.0)}% vs PTAX]"
        observacao = (observacao or "") + obs_extra
    
    # Montar dados
    cotacao_data = {
        "casa_slug": casa_slug,
        "data": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M:%S"),
        "valor_venda_especie": valor_venda,
        "valor_venda_cartao": valor_cartao,
        "ptax_venda": ptax_venda,
        "wise_rate": wise_rate,
        "spread_ptax": spread_ptax,
        "spread_wise": spread_wise,
        "iof_especie": iof_especie * 100,  # Salvar em %
        "custo_efetivo": custo_efetivo,
        "variacao_dia_anterior": var_rs,
        "variacao_pct_dia_anterior": var_pct,
        "estoque_disponivel": 1,
        "fonte": fonte,
        "observacao": observacao
    }
    
    insert_cotacao(cotacao_data)
    
    print(f"  [{casa_slug}] Venda: R$ {valor_venda:.4f} | "
          f"Efetivo: R$ {custo_efetivo:.4f} | "
          f"Spread PTAX: {spread_ptax}%")
    
    return cotacao_data


def importar_dados_json(filepath, config, ptax_venda, wise_rate):
    """
    Importa cotações de um arquivo JSON gerado pelo agente.
    Formato esperado:
    [
        {"casa_slug": "...", "valor_venda_especie": 6.45, "valor_venda_cartao": null, "fonte": "...", "observacao": "..."},
        ...
    ]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        dados = json.load(f)
    
    processados = 0
    for item in dados:
        if item.get("valor_venda_especie") and item.get("casa_slug"):
            processar_cotacao(
                casa_slug=item["casa_slug"],
                valor_venda=item["valor_venda_especie"],
                ptax_venda=ptax_venda,
                wise_rate=wise_rate,
                config=config,
                valor_cartao=item.get("valor_venda_cartao"),
                fonte=item.get("fonte", "import_json"),
                observacao=item.get("observacao", "")
            )
            processados += 1
    
    print(f"[OK] {processados} cotações importadas de {filepath}")
    return processados


def main():
    parser = argparse.ArgumentParser(description="Monitor de Câmbio EUR/BRL - Salvador")
    parser.add_argument("--init", action="store_true", help="Apenas inicializar banco")
    parser.add_argument("--build-json", action="store_true", help="Apenas gerar JSONs")
    parser.add_argument("--import-data", type=str, help="Importar dados de arquivo JSON")
    parser.add_argument("--vacuum", action="store_true", help="Executar vacuum no banco")
    args = parser.parse_args()
    
    config = load_config()
    
    # Inicializar banco
    init_db()
    init_casas_cambio(config)
    
    if args.init:
        print("[OK] Banco inicializado com sucesso.")
        return
    
    if args.vacuum:
        limpar_historico_antigo(config.get("historico_dias", 90))
        vacuum_db()
        print("[OK] Vacuum executado.")
        return
    
    # Coletar referências
    ptax_venda, wise_rate = coletar_referencias()
    
    if args.import_data:
        importar_dados_json(args.import_data, config, ptax_venda, wise_rate)
    
    if args.build_json or args.import_data:
        # Gerar JSONs
        hoje = datetime.now().strftime("%Y-%m-%d")
        arquivos = build_all(hoje)
        print(f"[OK] JSONs gerados: {arquivos}")
        return
    
    # Execução completa - aguarda dados do agente via --import-data
    print("[INFO] Execute com --import-data <arquivo.json> para importar cotações coletadas.")
    print("[INFO] Execute com --build-json para gerar JSONs a partir dos dados existentes.")


if __name__ == "__main__":
    main()
