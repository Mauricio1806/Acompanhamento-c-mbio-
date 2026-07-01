"""
Scraper Ourominas (OM DTVM) via Playwright.
URL: https://www.ourominas.com/cotacao-do-dia
"""
import re
from datetime import datetime

from scrapers.playwright_base import browser_page, PLAYWRIGHT_AVAILABLE


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
        with browser_page(headless=True, timeout_ms=35000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(6000)  # SPA - dar mais tempo

            texto = page.evaluate("document.body.innerText") or ""
            _parse(texto, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _parse(texto: str, resultado: dict):
    """
    Ourominas mostra tabela: Moeda | Compra | Venda.
    Procuramos linha 'EURO' ou 'EUR' seguida de 2 valores.
    """
    # padrao 1: EURO em uma linha, valores nas linhas seguintes
    padrao = re.compile(
        r"(?:EURO|EUR)\b[\s\S]{0,150}?R?\$?\s*(\d{1,2}[.,]\d{2,4})[\s\S]{0,80}?R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    for m in padrao.finditer(texto):
        try:
            v1 = float(m.group(1).replace(",", "."))
            v2 = float(m.group(2).replace(",", "."))
            # ambos precisam ser plausiveis EUR/BRL
            if 5.00 <= v1 <= 10.0 and 5.00 <= v2 <= 10.0:
                # convencao: compra < venda
                if v1 < v2:
                    resultado["compra_eur_especie"] = v1
                    resultado["venda_eur_especie"] = v2
                else:
                    resultado["compra_eur_especie"] = v2
                    resultado["venda_eur_especie"] = v1
                return
        except ValueError:
            continue

    # fallback: EURO + 1 valor plausivel de turismo
    padrao2 = re.compile(
        r"(?:EURO|EUR)\b[\s\S]{0,120}?R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    for m in padrao2.finditer(texto):
        try:
            v = float(m.group(1).replace(",", "."))
            if 5.80 <= v <= 9.50:
                resultado["venda_eur_especie"] = v
                return
        except ValueError:
            continue


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_ourominas(), indent=2, ensure_ascii=False))
