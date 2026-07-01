"""
Scraper MelhorCambio Salvador via Playwright.

O site foi reformulado em jun/2026: agora renderiza cotacoes via JavaScript.
Este scraper abre a pagina em navegador headless e extrai os valores.

URL alvo: https://www.melhorcambio.com/cotacao/compra/euro/salvador
"""
from datetime import datetime

from scrapers.playwright_base import (
    browser_page, parse_brl, find_prices_in_range,
    PLAYWRIGHT_AVAILABLE,
)


URL = "https://www.melhorcambio.com/cotacao/compra/euro/salvador"


def scrape_melhorcambio_salvador() -> dict:
    """
    Retorna dict:
    {
      "fonte": "melhorcambio",
      "timestamp": "...",
      "cambio_comercial": 5.83,
      "papel_moeda_menor": 6.27,
      "cartao_prepago_menor": 6.38,
      "casas": [ {nome, endereco, valor_venda_especie, valor_venda_cartao} ],
      "casas_count": N,
      "erro": null | "mensagem"
    }
    """
    resultado = {
        "fonte": "melhorcambio",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "cambio_comercial": None,
        "papel_moeda_menor": None,
        "cartao_prepago_menor": None,
        "casas": [],
        "casas_count": 0,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=25000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            # da tempo para JS renderizar
            page.wait_for_timeout(3500)

            # 1. tenta pegar valores de referencia (papel moeda menor, cartao menor, comercial)
            _extrair_referencias(page, resultado)

            # 2. tenta pegar lista de casas
            _extrair_casas(page, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    resultado["casas_count"] = len(resultado["casas"])
    return resultado


def _extrair_referencias(page, resultado: dict):
    """Procura a tabela resumo (papel moeda menor/comercial/cartao pre-pago)."""
    try:
        html = page.content()
    except Exception:
        return

    # heuristica sobre o texto renderizado
    text = _plain_text(page)
    if not text:
        return

    lines = text.split("\n")
    for i, line in enumerate(lines):
        l = line.strip().lower()
        # captura o valor da linha OU da linha seguinte
        contexto = " ".join(lines[i:i+3]).lower() if i + 3 <= len(lines) else l
        if "papel moeda" in l and "menor" in l:
            v = _proximo_valor(contexto)
            if v:
                resultado["papel_moeda_menor"] = v
        elif ("cartao" in l or "cartão" in l) and "menor" in l:
            v = _proximo_valor(contexto)
            if v:
                resultado["cartao_prepago_menor"] = v
        elif "comercial" in l and ("cambio" in l or "câmbio" in l):
            v = _proximo_valor(contexto)
            if v:
                resultado["cambio_comercial"] = v


def _extrair_casas(page, resultado: dict):
    """
    Procura cards de casas de cambio. O layout do MelhorCambio geralmente
    tem elementos com nome, endereco e dois valores (papel moeda + cartao).
    Estrategia: procurar por todos os elementos que contenham "Valor com IOF"
    ou similares e subir na arvore ate um bloco que tenha nome + endereco.
    """
    try:
        # candidato 1: blocos com data-attribute conhecido
        cards = page.query_selector_all("[class*='casa'], [class*='store'], [class*='card']")
        for card in cards:
            info = _extrair_info_card(card)
            if info:
                # evitar duplicatas por nome
                if not any(c["nome"].lower() == info["nome"].lower() for c in resultado["casas"]):
                    resultado["casas"].append(info)

        # candidato 2: se nao achou nada, olhar por elementos contendo "Salvador"
        # e valores no formato "R$ X,XX"
        if not resultado["casas"]:
            _extrair_por_texto_bruto(page, resultado)

    except Exception:
        pass


def _extrair_info_card(elem) -> dict | None:
    """Tenta identificar nome, endereco e valores dentro de um elemento card."""
    try:
        text = elem.inner_text().strip()
    except Exception:
        return None

    if not text or len(text) < 20:
        return None
    if "Salvador" not in text and "BA" not in text:
        return None

    prices = find_prices_in_range(text, lo=4.5, hi=12.0)
    if not prices:
        return None

    # nome: primeira linha significativa
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    nome = None
    blacklist = ("R$", "Papel", "Cartão", "Cartao", "Valor", "IOF", "Faca",
                 "Faça", "Ligar", "Site", "Voltar", "SEG", "SÁB", "SAB", "DOM",
                 "Habilitado", "Correspondente", "Salvador -", "Euro")
    for linha in lines:
        if any(b.lower() in linha.lower() for b in blacklist):
            continue
        if 3 < len(linha) < 100:
            nome = linha
            break

    if not nome:
        return None

    return {
        "nome": nome,
        "endereco": _extrair_endereco(text),
        "valor_venda_especie": prices[0] if len(prices) >= 1 else None,
        "valor_venda_cartao": prices[1] if len(prices) >= 2 else None,
        "correspondente": _extrair_correspondente(text),
    }


def _extrair_por_texto_bruto(page, resultado: dict):
    """Fallback: cria casa 'agregada' com o valor menor mostrado no topo."""
    if resultado["papel_moeda_menor"]:
        resultado["casas"].append({
            "nome": "MelhorCambio (menor valor Salvador)",
            "endereco": "Salvador, BA (agregado do site)",
            "valor_venda_especie": resultado["papel_moeda_menor"],
            "valor_venda_cartao": resultado["cartao_prepago_menor"],
            "correspondente": None,
        })


# ---------- helpers ----------

def _plain_text(page) -> str:
    try:
        return page.evaluate("document.body.innerText")
    except Exception:
        return ""


def _proximo_valor(texto: str) -> float | None:
    """Encontra o primeiro valor decimal plausivel no texto."""
    vals = find_prices_in_range(texto, lo=4.0, hi=15.0)
    return vals[0] if vals else None


def _extrair_endereco(texto: str) -> str | None:
    import re
    m = re.search(
        r"((?:Av\.?|Avenida|Rua|R\.|Praca|Praça|Estrada|Rod\.?)[^\n]{5,150}?(?:Salvador\s*-?\s*BA|Salvador,?\s*BA))",
        texto, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extrair_correspondente(texto: str) -> str | None:
    import re
    m = re.search(r"Correspondente\s+Cambial\s+([^\[\n]{3,80})", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(BCO\s+\w[\w\s\.]{3,40})", texto, re.IGNORECASE)
    return m.group(1).strip() if m else None


if __name__ == "__main__":
    import json
    dados = scrape_melhorcambio_salvador()
    print(json.dumps(dados, indent=2, ensure_ascii=False))
