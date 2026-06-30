#!/usr/bin/env python3
"""
Monitor de Cambio EUR/BRL - Salvador, BA.

Pipeline completo executado por padrao (sem argumentos):
1. Inicializa banco e cadastra casas do config.yaml
2. Coleta PTAX (BCB) + Wise como referencias
3. Faz scraping do MelhorCambio (cotacoes reais de Salvador)
4. Importa cotacoes manuais (data/manual_quotes.json) se existir
5. Calcula custo efetivo, spreads, variacao
6. Salva no SQLite e gera JSONs estaticos pro dashboard

Uso:
    python main.py                  # Pipeline completo (default)
    python main.py --init           # So inicializa banco
    python main.py --build-json     # So regenera JSONs do dia
    python main.py --vacuum         # Limpa historico antigo + vacuum
    python main.py --dry-run        # Coleta e mostra sem salvar
"""
import argparse
import json
import os
import sys
from datetime import datetime

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import (
    init_db, upsert_casa_cambio, insert_cotacao, get_ultima_cotacao,
    vacuum_db, limpar_historico_antigo,
)
from core.calculator import (
    calcular_custo_efetivo, calcular_spread_ptax, calcular_spread_wise,
    calcular_variacao, verificar_discrepancia,
)
from core.builder import build_all
from scrapers.bcb_ptax import get_ptax_eur, get_wise_rate
from scrapers.melhorcambio import scrape_melhorcambio_salvador


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
MANUAL_QUOTES_PATH = os.path.join(ROOT_DIR, "data", "manual_quotes.json")


# ---------- config ----------

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_casas_from_config(config: dict):
    casas = config.get("casas_cambio", [])
    for casa in casas:
        upsert_casa_cambio(casa)
    print(f"[OK] {len(casas)} casas cadastradas no banco.")


# ---------- coleta de referencias ----------

def coletar_referencias() -> tuple[float | None, float | None]:
    ptax = get_ptax_eur()
    wise = get_wise_rate()
    ptax_venda = ptax["cotacao_venda"] if ptax else None
    wise_rate = wise["rate"] if wise else None
    print(f"[PTAX] EUR/BRL venda: {ptax_venda}")
    print(f"[Wise] EUR/BRL: {wise_rate}")
    return ptax_venda, wise_rate


# ---------- processamento ----------

def processar_cotacao(
    casa_slug: str, valor_venda: float, ptax_venda: float | None,
    wise_rate: float | None, config: dict,
    valor_cartao: float | None = None,
    fonte: str = "scraping", observacao: str = "",
    dry_run: bool = False,
) -> dict:
    """Calcula, persiste (se nao dry-run) e retorna a linha de cotacao."""
    iof = config["iof"]["especie"]

    custo_efetivo = calcular_custo_efetivo(valor_venda, iof)
    spread_ptax = calcular_spread_ptax(valor_venda, ptax_venda)
    spread_wise = calcular_spread_wise(valor_venda, wise_rate)

    ultima = get_ultima_cotacao(casa_slug)
    var_rs, var_pct = (None, None)
    if ultima and ultima.get("valor_venda_especie"):
        var_rs, var_pct = calcular_variacao(valor_venda, ultima["valor_venda_especie"])

    if verificar_discrepancia(valor_venda, ptax_venda, config.get("max_spread_ptax", 3.0)):
        observacao = (observacao + " " if observacao else "") + \
            f"[ALERTA: spread >{config.get('max_spread_ptax', 3.0)}% vs PTAX]"

    agora = datetime.now()
    row = {
        "casa_slug": casa_slug,
        "data": agora.strftime("%Y-%m-%d"),
        "hora": agora.strftime("%H:%M:%S"),
        "valor_venda_especie": valor_venda,
        "valor_venda_cartao": valor_cartao,
        "ptax_venda": ptax_venda,
        "wise_rate": wise_rate,
        "spread_ptax": spread_ptax,
        "spread_wise": spread_wise,
        "iof_especie": iof * 100,
        "custo_efetivo": custo_efetivo,
        "variacao_dia_anterior": var_rs,
        "variacao_pct_dia_anterior": var_pct,
        "estoque_disponivel": 1,
        "fonte": fonte,
        "observacao": observacao.strip(),
    }

    if not dry_run:
        insert_cotacao(row)

    print(f"  [{casa_slug:35s}] venda R$ {valor_venda:.4f} | "
          f"efetivo R$ {custo_efetivo:.4f} | spread PTAX {spread_ptax}%")
    return row


# ---------- coleta MelhorCambio ----------

def coletar_melhorcambio(config: dict, ptax: float | None, wise: float | None,
                         dry_run: bool = False) -> int:
    """
    Faz scraping do MelhorCambio Salvador e salva as cotacoes encontradas.
    Cada casa do MelhorCambio que nao tem cadastro no config.yaml e
    cadastrada automaticamente como tipo 'casa_cambio_mc'.
    """
    print("\n[MelhorCambio] iniciando scraping...")
    dados = scrape_melhorcambio_salvador()

    if dados.get("erro"):
        print(f"[MelhorCambio] ERRO: {dados['erro']}")
        return 0

    print(f"[MelhorCambio] referencias: comercial={dados['cambio_comercial']} "
          f"papel_moeda_menor={dados['papel_moeda_menor']} "
          f"cartao_menor={dados['cartao_prepago_menor']}")
    print(f"[MelhorCambio] casas encontradas: {dados['casas_count']}")

    processadas = 0
    for casa in dados["casas"]:
        slug = casa["slug"]

        # cadastra casa que veio do scraping (caso ainda nao esteja no banco)
        if not dry_run:
            upsert_casa_cambio({
                "slug": slug,
                "nome": casa["nome"],
                "url": dados["url"],
                "endereco": casa.get("endereco") or "Salvador, BA",
                "bairro": _extrair_bairro(casa.get("endereco") or ""),
                "tipo": "casa_cambio",
                "horario": casa.get("horario"),
                "telefone": None,
                "whatsapp": None,
                "google_maps": _gerar_google_maps(casa["nome"], casa.get("endereco")),
                "formas_pagamento": ["Pix", "TED", "Dinheiro"],
                "agendamento_acima": 3000,
            })

        if casa.get("valor_venda_especie"):
            processar_cotacao(
                casa_slug=slug,
                valor_venda=casa["valor_venda_especie"],
                ptax_venda=ptax,
                wise_rate=wise,
                config=config,
                valor_cartao=casa.get("valor_venda_cartao"),
                fonte="melhorcambio",
                observacao=(f"correspondente: {casa['correspondente']}"
                            if casa.get("correspondente") else ""),
                dry_run=dry_run,
            )
            processadas += 1

    return processadas


def _extrair_bairro(endereco: str) -> str | None:
    if not endereco:
        return None
    # heuristica: ", BAIRRO, Salvador" ou "Bairro - Salvador"
    import re
    m = re.search(r",\s*([A-ZÀ-Ú][A-Za-zÀ-ú\s]{2,40}?)\s*[,-]\s*Salvador", endereco)
    if m:
        return m.group(1).strip()
    return None


def _gerar_google_maps(nome: str, endereco: str | None) -> str:
    query = nome
    if endereco:
        query = f"{nome} {endereco}"
    import urllib.parse
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"


# ---------- coleta manual (PR-based) ----------

def importar_manual(config: dict, ptax: float | None, wise: float | None,
                    dry_run: bool = False) -> int:
    """
    Le data/manual_quotes.json (commit manual ou via PR) com cotacoes que o
    scraper nao consegue automatizar (casas que so cotam via WhatsApp etc).

    Formato:
    [
      {"casa_slug": "confidence-shopping-barra", "valor_venda_especie": 6.42,
       "valor_venda_cartao": 6.55, "observacao": "consultado via WhatsApp"}
    ]
    """
    if not os.path.exists(MANUAL_QUOTES_PATH):
        print("\n[Manual] data/manual_quotes.json nao encontrado (pulando).")
        return 0

    try:
        with open(MANUAL_QUOTES_PATH, "r", encoding="utf-8") as f:
            entradas = json.load(f)
    except Exception as e:
        print(f"[Manual] erro lendo manual_quotes.json: {e}")
        return 0

    if not isinstance(entradas, list) or not entradas:
        print("[Manual] arquivo vazio ou formato invalido (pulando).")
        return 0

    print(f"\n[Manual] processando {len(entradas)} cotacoes manuais...")
    count = 0
    for item in entradas:
        slug = item.get("casa_slug")
        valor = item.get("valor_venda_especie")
        if not slug or not valor:
            continue
        processar_cotacao(
            casa_slug=slug,
            valor_venda=float(valor),
            ptax_venda=ptax,
            wise_rate=wise,
            config=config,
            valor_cartao=item.get("valor_venda_cartao"),
            fonte=item.get("fonte", "manual"),
            observacao=item.get("observacao", ""),
            dry_run=dry_run,
        )
        count += 1
    return count


# ---------- pipeline ----------

def pipeline(dry_run: bool = False):
    """Pipeline completo: init -> referencias -> scraping -> manual -> build."""
    config = load_config()
    init_db()
    init_casas_from_config(config)

    ptax, wise = coletar_referencias()

    n_mc = coletar_melhorcambio(config, ptax, wise, dry_run=dry_run)
    n_man = importar_manual(config, ptax, wise, dry_run=dry_run)

    print(f"\n[Total] {n_mc + n_man} cotacoes processadas "
          f"({n_mc} via MelhorCambio + {n_man} manuais).")

    if not dry_run:
        arquivos = build_all()
        print(f"[OK] JSONs gerados: {list(arquivos.keys())}")
    else:
        print("[DRY RUN] nada gravado e JSONs nao regerados.")


def main():
    parser = argparse.ArgumentParser(description="Monitor Cambio EUR/BRL Salvador")
    parser.add_argument("--init", action="store_true",
                        help="So inicializa banco e cadastra casas")
    parser.add_argument("--build-json", action="store_true",
                        help="So regenera JSONs a partir do banco")
    parser.add_argument("--vacuum", action="store_true",
                        help="Remove historico antigo e compacta banco")
    parser.add_argument("--dry-run", action="store_true",
                        help="Coleta e mostra mas nao salva nada")
    args = parser.parse_args()

    if args.init:
        config = load_config()
        init_db()
        init_casas_from_config(config)
        print("[OK] init concluido.")
        return

    if args.build_json:
        init_db()
        arquivos = build_all()
        print(f"[OK] JSONs gerados: {arquivos}")
        return

    if args.vacuum:
        config = load_config()
        init_db()
        limpar_historico_antigo(config.get("historico_dias", 90))
        vacuum_db()
        print("[OK] vacuum concluido.")
        return

    pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
