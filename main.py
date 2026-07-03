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
    from scrapers.confidence import scrape_confidence
    print("\n[Confidence] iniciando via API AWS...")
    dados = _safe_scrape("Confidence", scrape_confidence)

    if dados.get("erro"):
        print(f"[Confidence] falhou: {dados['erro']}")
        return 0
    if not dados.get("valor_bruto"):
        print(f"[Confidence] sem valor bruto")
        return 0

    valor_bruto = dados["valor_bruto"]
    iof_api = dados.get("iof_pct")
    taxa_api = dados.get("taxa_pct")

    # IMPORTANTE: usamos o valor_bruto DIRETO como venda espécie.
    # Os campos iof/taxa da API sao para outros produtos (remessa 3.5%),
    # nao para papel-moeda. Nosso pipeline aplica IOF 1.1% (espécie) automaticamente.
    print(f"[Confidence] Salvador (id {dados.get('cidade_id')}): "
          f"valor bruto R$ {valor_bruto} (API tb informou iof {iof_api}% + taxa {taxa_api}% - remessa, ignorados)")

    # aplica a todas as unidades Confidence do config
    slugs = [c["slug"] for c in config.get("casas_cambio", [])
             if c["slug"].startswith("confidence-")]

    processadas = 0
    for slug in slugs:
        processar_cotacao(
            slug, valor_bruto, ptax, wise, config,
            fonte="confidence_api",
            observacao=f"valor bruto Confidence Salvador (API)",
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


# ============================================================
# KambioApp — agregador com varias casas de Salvador
# ============================================================

# mapeamento nome_kambio + palavra-chave no endereco -> slug do config
KAMBIO_ADDRESS_HINTS = {
    # Confidence tem 5 unidades - diferenciar por endereco
    ("confidence", "tancredo neves, 2915"):   "confidence-salvador-shopping",
    ("confidence", "tancredo neves, 3133"):   "confidence-salvador-shopping",
    ("confidence", "salvador shopping"):      "confidence-salvador-shopping",
    ("confidence", "shopping barra"):         "confidence-shopping-barra",
    ("confidence", "centenario, 2992"):       "confidence-shopping-barra",
    ("confidence", "centenário, 2992"):       "confidence-shopping-barra",
    ("confidence", "chame-chame"):            "confidence-shopping-barra",
    ("confidence", "tancredo neves, 148"):    "confidence-shopping-bahia",
    ("confidence", "shopping da bahia"):      "confidence-shopping-bahia",
    ("confidence", "paralela"):               "confidence-paralela",
    ("confidence", "patamares"):              "confidence-paralela",
    ("confidence", "luís viana, 8544"):       "confidence-paralela",
    ("confidence", "aeroporto"):              "confidence-aeroporto-ssa",
    ("confidence", "são cristóvão"):          "confidence-aeroporto-ssa",
    # DayCambio
    ("daycambio", "tancredo neves, 148"):     "daycambio-shopping-bahia",
    ("daycambio", "shopping da bahia"):       "daycambio-shopping-bahia",
    # Lumina 2 unidades
    ("lúmina", "centenário, 2992"):           "lumina-shopping-barra",
    ("lúmina", "shopping barra"):             "lumina-shopping-barra",
    ("lumina", "centenário, 2992"):           "lumina-shopping-barra",
    ("lumina", "shopping barra"):             "lumina-shopping-barra",
    ("lúmina", "tancredo neves, 3133"):       "lumina-salvador-shopping",
    ("lúmina", "salvador shopping"):          "lumina-salvador-shopping",
    ("lumina", "tancredo neves, 3133"):       "lumina-salvador-shopping",
    # Labor
    ("labor", "tancredo neves, 3133"):        "labor-cambio",
    ("labor", "loja 133"):                    "labor-cambio",
    # Conecta
    ("conecta", "tancredo neves, 3313"):      "conecta-salvador-shopping",
    ("conecta", "salvador shopping"):         "conecta-salvador-shopping",
    ("conecta", "tancredo neves, 1632"):      "conecta-trade-center",
    ("conecta", "trade center"):              "conecta-trade-center",
    # Simple
    ("simple", "tancredo neves, 2227"):       "simple-cambio",
    ("simple", "salvador prime"):             "simple-cambio",
    # Prime
    ("prime", "antônio carlos magalhães, 656"): "prime-cambio-itaigara",
    ("prime", "itaigara"):                    "prime-cambio-itaigara",
    # Salvador Cambio
    ("salvador cambio", "itaigara"):          "salvador-cambio-itaigara",
    ("salvador câmbio", "itaigara"):          "salvador-cambio-itaigara",
    # Bahia Cambio
    ("bahia", "antônio carlos magalhães, 585"): "bahia-cambio",
    # Voamais
    ("voamais", "sete de setembro"):          "voamais-barra",
    # Tours Bahia
    ("tours", "bélgica"):                     "tours-bahia-international",
    # Iguatemi
    ("iguatemi", "tancredo neves, 148"):      "iguatemi-cambio-turismo",
    # Ourominas
    ("ourominas", ""):                        "ourominas",
    # Get Money
    ("get money", ""):                        "get-money",
    # Frente
    ("frente", ""):                           "frente-corretora",
}


def _norm(s: str) -> str:
    """Remove acentos e passa pra lowercase pra facilitar match."""
    import unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _match_kambio_slug(nome_kambio: str, endereco: str) -> str | None:
    """Encontra slug do config baseado em nome+endereco do KambioApp."""
    nome_l = _norm(nome_kambio)
    end_l = _norm(endereco)
    for (nome_key, end_key), slug in KAMBIO_ADDRESS_HINTS.items():
        nk = _norm(nome_key)
        ek = _norm(end_key)
        if nk in nome_l:
            if not ek or ek in end_l:
                return slug
    return None


def coletar_kambioapp(config, ptax, wise, dry_run) -> int:
    """
    Coleta cotacoes agregadas de casas de Salvador via KambioApp.
    Valores retornados JA incluem IOF - dividimos pra ter o valor bruto,
    pipeline recalcula com IOF de 1.1% (espécie).
    """
    from scrapers.kambioapp import scrape_kambioapp
    print("\n[KambioApp] iniciando scraping do agregador...")
    dados = _safe_scrape("KambioApp", scrape_kambioapp)

    if dados.get("erro"):
        print(f"[KambioApp] falhou: {dados['erro']}")
        return 0

    casas = dados.get("casas") or []
    print(f"[KambioApp] {len(casas)} casas encontradas")

    if not casas:
        return 0

    iof_pipeline = config["iof"]["especie"]  # 0.011
    processadas = 0
    nao_mapeadas = []

    for casa in casas:
        nome_k = casa["nome_kambio"]
        endereco = casa.get("endereco") or ""
        valor_com_iof = casa["valor_com_iof"]

        slug = _match_kambio_slug(nome_k, endereco)
        if not slug:
            nao_mapeadas.append(f"{nome_k} | {endereco[:60]}")
            continue

        # valor com IOF -> valor bruto (pipeline reaplica IOF)
        valor_bruto = round(valor_com_iof / (1 + iof_pipeline), 4)

        processar_cotacao(
            slug, valor_bruto, ptax, wise, config,
            fonte="kambioapp",
            observacao=f"KambioApp: valor com IOF R$ {valor_com_iof}",
            dry_run=dry_run,
        )
        processadas += 1

    if nao_mapeadas:
        print(f"[KambioApp] {len(nao_mapeadas)} casas nao mapeadas:")
        for n in nao_mapeadas:
            print(f"  - {n}")

    return processadas


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

    totais = {"kambioapp": 0, "melhorcambio": 0, "confidence": 0, "daycambio": 0, "ourominas": 0, "manual": 0}

    if not skip_scraping:
        # KambioApp primeiro (agregador com varias casas)
        totais["kambioapp"]    = coletar_kambioapp(config, ptax, wise, dry_run)
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
