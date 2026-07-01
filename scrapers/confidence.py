"""
Scraper Confidence Cambio (Travelex) via Playwright.

A pagina /ecommerce/ e SPA. Mostra:
- Cambio comercial de referencia
- VET (Valor Efetivo Total) para EUR - ja inclui IOF
- Permite escolher moeda entre Dolar/Euro/Libra/etc

Estrategia: entra na pagina, seleciona EUR (se possivel), pega o VET.
"""
from datetime import datetime

from scrapers.playwright_base import (
    browser_page, find_prices_in_range,
    PLAYWRIGHT_AVAILABLE,
)


URL = "https://www.confidencecambio.com.br/ecommerce/"


def scrape_confidence() -> dict:
    resultado = {
        "fonte": "confidence",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "cambio_comercial": None,
        "vet_eur": None,          # valor efetivo total EUR (com IOF)
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=30000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(4000)  # espera SPA renderizar

            # tenta selecionar EUR (dropdown ou botao)
            _tentar_selecionar_eur(page)
            page.wait_for_timeout(2500)

            texto = page.evaluate("document.body.innerText") or ""

            # extrai valores
            _parse(texto, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _tentar_selecionar_eur(page):
    """Tenta clicar em EUR se houver seletor de moeda."""
    # varias estrategias de seleção
    for seletor in [
        "text=EUR",
        "text=Euro",
        "[data-currency='EUR']",
        "[value='EUR']",
        "button:has-text('EUR')",
    ]:
        try:
            el = page.query_selector(seletor)
            if el:
                el.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


def _parse(texto: str, resultado: dict):
    """
    Procura por padrões:
    - "Câmbio comercial: R$ X,XX"
    - "VET: R$ X,XX"
    """
    import re

    m = re.search(r"[Cc][âa]mbio\s+comercial[:\s]+R\$?\s*(\d{1,2}[.,]\d{2,4})", texto)
    if m:
        val = m.group(1).replace(",", ".")
        try:
            resultado["cambio_comercial"] = float(val)
        except ValueError:
            pass

    m = re.search(r"VET[:\s]+R\$?\s*(\d{1,2}[.,]\d{2,4})", texto)
    if m:
        val = m.group(1).replace(",", ".")
        try:
            resultado["vet_eur"] = float(val)
        except ValueError:
            pass

    # fallback: se nao pegou VET explicito, pega o maior valor entre 5-10 (deve ser turismo)
    if resultado["vet_eur"] is None:
        vals = find_prices_in_range(texto, lo=5.5, hi=10.0)
        # filtra valores muito baixos (comercial) e pega o maior plausivel
        turismo = [v for v in vals if v > 5.5]
        if turismo:
            # se comercial esta definido, pega o primeiro valor acima dele
            if resultado["cambio_comercial"]:
                acima = [v for v in turismo if v > resultado["cambio_comercial"] + 0.3]
                if acima:
                    resultado["vet_eur"] = acima[0]
            else:
                resultado["vet_eur"] = turismo[0]


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_confidence(), indent=2, ensure_ascii=False))
