"""
Scraper DayCambio (Grupo Daycoval) via Playwright.
Estrategia: procura bloco "EURO" no texto e extrai valores proximos.
"""
import re
from datetime import datetime

from scrapers.playwright_base import browser_page, PLAYWRIGHT_AVAILABLE


URL_SIMULADOR = "https://www.daycambio.com.br/simulador-cambio-online/"
URL_EURO = "https://www.daycambio.com.br/cambio/moedas-em-especie/euro/"


def scrape_daycambio() -> dict:
    resultado = {
        "fonte": "daycambio",
        "url": URL_SIMULADOR,
        "timestamp": datetime.now().isoformat(),
        "vet_eur": None,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=35000) as page:
            # tenta simulador primeiro
            page.goto(URL_SIMULADOR, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(5000)

            # tenta selecionar EURO
            _selecionar_euro(page)
            page.wait_for_timeout(3500)

            texto = page.evaluate("document.body.innerText") or ""
            _parse(texto, resultado)

            # se nao achou, tenta pagina especifica de EURO
            if resultado["vet_eur"] is None:
                page.goto(URL_EURO, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(4000)
                texto2 = page.evaluate("document.body.innerText") or ""
                _parse(texto2, resultado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _selecionar_euro(page):
    for sel in [
        "select option[value*='EUR' i]",
        "select option:has-text('EURO')",
        "button:has-text('EURO')",
        "a:has-text('EURO')",
        "[data-currency='EUR']",
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=2500, force=True)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue

    # fallback via JS
    try:
        page.evaluate("""
            () => {
              const nodes = Array.from(document.querySelectorAll('*'));
              const match = nodes.find(n => (n.innerText || '').trim() === 'EURO' && n.offsetParent !== null);
              if (match) match.click();
            }
        """)
    except Exception:
        pass
    return False


def _parse(texto: str, resultado: dict):
    # padrao: bloco EURO com valor VET proximo
    padrao_euro_vet = re.compile(
        r"EURO[\s\S]{0,400}?(?:VET|Total)[:\s]+R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    m = padrao_euro_vet.search(texto)
    if m:
        try:
            v = float(m.group(1).replace(",", "."))
            if v >= 5.80:  # sanity check EUR
                resultado["vet_eur"] = v
                return
        except ValueError:
            pass

    # padrao: EURO seguido de qualquer valor plausivel de turismo (6.00-9.00)
    padrao_euro_val = re.compile(
        r"EURO[\s\S]{0,200}?R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    for match in padrao_euro_val.finditer(texto):
        try:
            v = float(match.group(1).replace(",", "."))
            if 5.80 <= v <= 9.50:
                resultado["vet_eur"] = v
                return
        except ValueError:
            continue


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_daycambio(), indent=2, ensure_ascii=False))
