#!/usr/bin/env python3
"""
Monitor de Cambio EUR/BRL - Salvador, BA.

Pipeline completo (execucao default):
1. Inicializa banco e cadastra casas do config.yaml
2. Coleta PTAX (BCB) + Wise como referencias
3. Faz scraping via Playwright de:
   - MelhorCambio Salvador
   - Confidence/Travelex (VET EUR)
   - DayCambio (VET EUR)
   - Ourominas
4. Importa cotacoes manuais (data/manual_quotes.json)
5. Calcula custo efetivo, spreads, variacao
6. Salva no SQLite e gera JSONs para o dashboard
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


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
MANUAL_QUOTES_PATH = os.path.join(ROOT_DIR, "data", "manual_quotes.json")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_casas_from_config(config: dict):
    # remove casas obsoletas de versoes anteriores (limpeza v5 -> v6)
    from core.db import _conn
    con = _conn()
    cur = con.cursor()
    for slug_obsoleto in ["melhorcambio-sp", "melhorcambio-rj", "melhorcambio-agregado"]:
        cur.execute("DELETE FROM cotacoes WHERE casa_slug = ?", (slug_obsoleto,))
        cur.execute("DELETE FROM casas_cambio WHERE slug = ?", (slug_obsoleto,))
    con.commit()
    con.close()

    casas = config.get("casas_cambio", [])
    for casa in casas:
        upsert_casa_cambio(casa)
    print(f"[OK] {len(casas)} casas cadastradas no banco.")


def coletar_referencias() -> tuple[float | None, float | None]:
    ptax = get_ptax_eur()
    wise = get_wise_rate()
    ptax_venda = ptax["cotacao_venda"] if ptax else None
    wise_rate = wise["rate"] if wise else None
    print(f"[PTAX] EUR/BRL venda: {ptax_venda}")
    print(f"[Wise] EUR/BRL: {wise_rate}")
    return ptax_venda, wise_rate


def processar_cotacao(
    casa_slug, valor_venda, ptax_venda, wise_rate, config,
    valor_cartao=None, fonte="scraping", observacao="", dry_run=False,
):
    # SANITY CHECK: rejeita valores absurdos
    if valor_venda is None or valor_venda <= 0:
        print(f"  [{casa_slug}] REJEITADO: valor invalido ({valor_venda})")
        return None
    if ptax_venda and valor_venda < ptax_venda * 0.97:
        # cotacao turismo NUNCA fica abaixo do PTAX (spread negativo > 3% e bug)
        print(f"  [{casa_slug}] REJEITADO: valor R$ {valor_venda:.4f} abaixo do PTAX "
              f"R$ {ptax_venda:.4f} (provavel scraping de outra moeda)")
        return None
    if valor_venda > 15.0 or valor_venda < 4.0:
        print(f"  [{casa_slug}] REJEITADO: valor fora da faixa plausivel ({valor_venda})")
        return None

    iof = config["iof"]["especie"]

    custo_efetivo = calcular_custo_efetivo(valor_venda, iof)
    spread_ptax = calcular_spread_ptax(valor_venda, ptax_venda)
    spread_wise = calcular_spread_wise(valor_venda, wise_rate)

    ultima = get_ultima_cotacao(casa_slug)
    var_rs, var_pct = (None, None)
    if ultima and ultima.get("valor_venda_especie"):
        var_rs, var_pct = calcular_variacao(valor_venda, ultima["valor_venda_especie"])

    if verificar_discrepancia(valor_venda, ptax_venda, config.get("max_spread_ptax", 5.0)):
        observacao = (observacao + " " if observacao else "") + \
            f"[ALERTA: spread >{config.get('max_spread_ptax', 5.0)}% vs PTAX]"

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

    print(f"  [{casa_slug:38s}] venda R$ {valor_venda:.4f} | "
          f"efetivo R$ {custo_efetivo:.4f} | spread PTAX {spread_ptax}%")
    return row


def _safe_scrape(nome, fn):
    try:
        return fn()
    except Exception as e:
        print(f"[{nome}] ERRO: {e}")
        return {"erro": str(e)}


def coletar_melhorcambio(config, ptax, wise, dry_run) -> int:
    """
    Coleta cotacao de EUR turismo do MelhorCambio Salvador.
    Aplica ao slug 'salvador-cambio-itaigara' (ja cadastrado no config).
    """
    from scrapers.melhorcambio import scrape_cidade

    print("\n[MelhorCambio-salvador] iniciando scraping...")
    dados = _safe_scrape("MelhorCambio-salvador", lambda: scrape_cidade("salvador"))
    if dados.get("erro"):
        print(f"[MelhorCambio-salvador] falhou: {dados['erro']}")
        return 0

    print(f"[MelhorCambio-salvador] papel_menor={dados.get('papel_moeda_menor')} "
          f"cartao_menor={dados.get('cartao_menor')} "
          f"comercial={dados.get('cambio_comercial')} "
          f"casa={dados.get('casa_principal')}")

    if not dados.get("papel_moeda_menor"):
        print("[MelhorCambio-salvador] sem valor - pulando")
        return 0

    processar_cotacao(
        "salvador-cambio-itaigara", dados["papel_moeda_menor"], ptax, wise, config,
        valor_cartao=dados.get("cartao_menor"),
        fonte="melhorcambio",
        observacao=f"casa: {dados.get('casa_principal') or '?'}",
        dry_run=dry_run,
    )
    return 1


def coletar_confidence(config, ptax, wise, dry_run) -> int:
    """
    Coleta cotacao EUR turismo da Confidence via API AWS.
    Aplica a mesma cotacao a todas as 5 unidades Confidence de Salvador,
    ja que a cotacao e por cidade (Salvador), nao por loja.
    """
    from scrapers.confidence import scrape_confidence
    print("\n[Confidence] iniciando via API AWS...")
    dados = _safe_scrape("Confidence", scrape_confidence)

    if dados.get("erro"):
        print(f"[Confidence] falhou: {dados['erro']}")
        return 0
    if not dados.get("vet_eur"):
        print(f"[Confidence] sem VET (valor bruto: {dados.get('valor_bruto')})")
        return 0

    vet = dados["vet_eur"]
    valor_bruto = dados["valor_bruto"]
    print(f"[Confidence] Salvador (id {dados.get('cidade_id')}): "
          f"bruto R$ {valor_bruto} + IOF {dados.get('iof_pct')}% + taxa {dados.get('taxa_pct')}% = VET R$ {vet}")

    # aplica a todas as unidades Confidence do config
    slugs = [c["slug"] for c in config.get("casas_cambio", [])
             if c["slug"].startswith("confidence-")]

    # o VET ja inclui IOF, nosso pipeline reaplica IOF por cima.
    # entao dividimos pelo IOF esperado pra ter o "valor sem IOF"
    iof_pipeline = config["iof"]["especie"]  # 0.011 = 1.1%
    valor_sem_iof_pipeline = round(vet / (1 + iof_pipeline), 4)

    processadas = 0
    for slug in slugs:
        processar_cotacao(
            slug, valor_sem_iof_pipeline, ptax, wise, config,
            fonte="confidence_api",
            observacao=f"VET Confidence R$ {vet} (bruto {valor_bruto} + IOF {dados.get('iof_pct')}% + taxa {dados.get('taxa_pct')}%)",
            dry_run=dry_run,
        )
        processadas += 1
    return processadas


def coletar_daycambio(config, ptax, wise, dry_run) -> int:
    from scrapers.daycambio import scrape_daycambio
    print("\n[DayCambio] iniciando scraping...")
    dados = _safe_scrape("DayCambio", scrape_daycambio)
    if dados.get("erro") or not dados.get("vet_eur"):
        print(f"[DayCambio] sem cotacao ({dados.get('erro') or 'vet nao encontrado'})")
        return 0

    print(f"[DayCambio] VET EUR: {dados['vet_eur']}")
    valor = dados["vet_eur"]
    iof = config["iof"]["especie"]
    valor_sem_iof = round(valor / (1 + iof), 4)

    processar_cotacao(
        "daycambio-shopping-bahia", valor_sem_iof, ptax, wise, config,
        fonte="daycambio_site",
        observacao=f"VET original {valor}",
        dry_run=dry_run,
    )
    return 1


def coletar_ourominas(config, ptax, wise, dry_run) -> int:
    from scrapers.ourominas import scrape_ourominas
    print("\n[Ourominas] iniciando scraping...")
    dados = _safe_scrape("Ourominas", scrape_ourominas)
    if dados.get("erro") or not dados.get("venda_eur_especie"):
        print(f"[Ourominas] sem cotacao ({dados.get('erro') or 'venda nao encontrada'})")
        return 0

    valor = dados["venda_eur_especie"]
    print(f"[Ourominas] venda EUR: {valor}")
    processar_cotacao(
        "ourominas", valor, ptax, wise, config,
        fonte="ourominas_site", dry_run=dry_run,
    )
    return 1


def _mapear_slugs(config: dict) -> dict:
    m = {}
    for c in config.get("casas_cambio", []):
        m[c["nome"].lower()] = c["slug"]
        for token in c["nome"].lower().split(" - "):
            m[token.strip()] = c["slug"]
    return m


def _match_slug(nome, mapa) -> str | None:
    nome_l = nome.lower()
    for chave, slug in mapa.items():
        if len(chave) < 5:
            continue
        if chave in nome_l or nome_l in chave:
            return slug
    return None


def importar_manual(config, ptax, wise, dry_run) -> int:
    if not os.path.exists(MANUAL_QUOTES_PATH):
        print("\n[Manual] data/manual_quotes.json nao encontrado (pulando).")
        return 0
    try:
        with open(MANUAL_QUOTES_PATH, "r", encoding="utf-8") as f:
            entradas = json.load(f)
    except Exception as e:
        print(f"[Manual] erro lendo arquivo: {e}")
        return 0
    if not isinstance(entradas, list) or not entradas:
        print("[Manual] vazio ou formato invalido.")
        return 0

    print(f"\n[Manual] processando {len(entradas)} cotacoes manuais...")
    count = 0
    for item in entradas:
        slug = item.get("casa_slug")
        valor = item.get("valor_venda_especie")
        if not slug or not valor:
            continue
        processar_cotacao(
            slug, float(valor), ptax, wise, config,
            valor_cartao=item.get("valor_venda_cartao"),
            fonte=item.get("fonte", "manual"),
            observacao=item.get("observacao", ""),
            dry_run=dry_run,
        )
        count += 1
    return count


def pipeline(dry_run: bool = False, skip_scraping: bool = False):
    config = load_config()
    init_db()
    init_casas_from_config(config)

    ptax, wise = coletar_referencias()

    totais = {"melhorcambio": 0, "confidence": 0, "daycambio": 0, "ourominas": 0, "manual": 0}

    if not skip_scraping:
        totais["melhorcambio"] = coletar_melhorcambio(config, ptax, wise, dry_run)
        totais["confidence"]   = coletar_confidence(config, ptax, wise, dry_run)
        totais["daycambio"]    = coletar_daycambio(config, ptax, wise, dry_run)
        totais["ourominas"]    = coletar_ourominas(config, ptax, wise, dry_run)

    totais["manual"] = importar_manual(config, ptax, wise, dry_run)

    total = sum(totais.values())
    print(f"\n[Total] {total} cotacoes processadas | {totais}")

    if not dry_run:
        arquivos = build_all()
        print(f"[OK] JSONs gerados: {list(arquivos.keys())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--build-json", action="store_true")
    parser.add_argument("--vacuum", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-scrape", action="store_true")
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

    pipeline(dry_run=args.dry_run, skip_scraping=args.no_scrape)


if __name__ == "__main__":
    main()
