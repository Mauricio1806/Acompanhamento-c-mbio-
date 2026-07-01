"""
Scraper DayCambio (Grupo Daycoval) via Playwright.

A pagina /simulador-cambio-online/ tem simulador dinamico com cotacoes.
"""
from datetime import datetime

from scrapers.playwright_base import (
    browser_page, find_prices_in_range,
    PLAYWRIGHT_AVAILABLE,
)


URL = "https://www.daycambio.com.br/simulador-cambio-online/"


def scrape_daycambio() -> dict:
    resultado = {
        "fonte": "daycambio",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "vet_eur": None,
        "cambio_comercial": None,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=30000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(4000)

            # tenta selecionar EUR
            for seletor in ["text=EURO", "text=Euro", "text=EUR"]:
                try:
                    el = page.query_selector(seletor)
                    if el:
                        el.click(timeout=2500)
                        break
                except Exception:
                    continue
            page.wait_for_timeout(2500)

            texto = page.evaluate("document.body.innerText") or ""
            _parse(texto, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _parse(texto: str, resultado: dict):
    import re

    m = re.search(r"[Cc][âa]mbio\s+comercial[:\s]+R\$?\s*(\d{1,2}[.,]\d{2,4})", texto)
    if m:
        try:
            resultado["cambio_comercial"] = float(m.group(1).replace(",", "."))
        except ValueError:
            pass

    m = re.search(r"VET[:\s]+R\$?\s*(\d{1,2}[.,]\d{2,4})", texto)
    if m:
        try:
            resultado["vet_eur"] = float(m.group(1).replace(",", "."))
        except ValueError:
            pass

    if resultado["vet_eur"] is None:
        vals = find_prices_in_range(texto, lo=5.5, hi=10.0)
        turismo = [v for v in vals if v > 5.5]
        if turismo:
            if resultado["cambio_comercial"]:
                acima = [v for v in turismo if v > resultado["cambio_comercial"] + 0.3]
                if acima:
                    resultado["vet_eur"] = acima[0]
            else:
                resultado["vet_eur"] = turismo[0]


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_daycambio(), indent=2, ensure_ascii=False))
