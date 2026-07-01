"""
Scraper Ourominas (OM DTVM) via Playwright.
URL: https://www.ourominas.com/cotacao-do-dia
"""
from datetime import datetime

from scrapers.playwright_base import (
    browser_page, find_prices_in_range,
    PLAYWRIGHT_AVAILABLE,
)


URL = "https://www.ourominas.com/cotacao-do-dia"


def scrape_ourominas() -> dict:
    resultado = {
        "fonte": "ourominas",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "venda_eur_especie": None,
        "compra_eur_especie": None,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=30000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(4000)

            texto = page.evaluate("document.body.innerText") or ""
            _parse(texto, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _parse(texto: str, resultado: dict):
    """
    Ourominas tipicamente mostra tabela com Compra/Venda por moeda.
    Estrutura esperada em texto: "EURO ... [compra] ... [venda]"
    """
    import re

    # tenta achar bloco EURO
    m = re.search(
        r"EURO[^\n]*\n?(?:[^0-9]{0,80}(\d{1,2}[.,]\d{2,4})[^0-9]{0,50}(\d{1,2}[.,]\d{2,4}))?",
        texto, re.IGNORECASE | re.DOTALL,
    )
    if m and m.group(1) and m.group(2):
        try:
            v1 = float(m.group(1).replace(",", "."))
            v2 = float(m.group(2).replace(",", "."))
            # convencao: compra < venda
            if v1 < v2:
                resultado["compra_eur_especie"] = v1
                resultado["venda_eur_especie"] = v2
            else:
                resultado["compra_eur_especie"] = v2
                resultado["venda_eur_especie"] = v1
        except ValueError:
            pass

    # fallback: se so tem 1 valor plausivel, assume que e venda turismo
    if resultado["venda_eur_especie"] is None:
        vals = find_prices_in_range(texto, lo=5.5, hi=10.0)
        if vals:
            resultado["venda_eur_especie"] = vals[0]


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_ourominas(), indent=2, ensure_ascii=False))
