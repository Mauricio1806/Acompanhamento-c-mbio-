"""
Scraper Confidence Cambio (Travelex) via Playwright.

Estrategia: acessa a pagina, tenta trocar pra EUR, e VALIDA que o valor
extraido e realmente de EUR (nao Dolar). Se nao conseguir validar, retorna
vazio em vez de retornar valor errado.
"""
import re
from datetime import datetime

from scrapers.playwright_base import browser_page, PLAYWRIGHT_AVAILABLE


URL = "https://www.confidencecambio.com.br/ecommerce/"


def scrape_confidence() -> dict:
    resultado = {
        "fonte": "confidence",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "vet_eur": None,
        "cambio_comercial_eur": None,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=35000) as page:
            page.goto(URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(5000)

            # tenta trocar pra EUR - varias estrategias
            trocado = _trocar_para_eur(page)
            page.wait_for_timeout(3500)

            texto = page.evaluate("document.body.innerText") or ""

            # so aceita valor se conseguiu confirmar EUR
            _parse_com_validacao(texto, resultado, eur_confirmado=trocado)

    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def _trocar_para_eur(page) -> bool:
    """Retorna True se conseguiu efetivamente selecionar EUR."""
    # tenta seletores comuns
    seletores = [
        # dropdown/select
        "select[name*='moeda' i] option[value*='EUR' i]",
        "select[name*='currency' i] option[value*='EUR' i]",
        # botoes com texto
        "button:has-text('EUR')",
        "button:has-text('Euro')",
        # links
        "a:has-text('EUR')",
        "a:has-text('Euro')",
        # divs clicaveis
        "[data-currency='EUR']",
        "[data-moeda='EUR']",
    ]
    for sel in seletores:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=3000, force=True)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue

    # fallback: usar evaluate pra clicar em elemento com texto "EUR"
    try:
        clicked = page.evaluate("""
            () => {
              const nodes = Array.from(document.querySelectorAll('button, a, [role=button], div[class*=currency], div[class*=moeda]'));
              const match = nodes.find(n => /\\bEUR\\b|\\bEuro\\b/i.test(n.innerText || ''));
              if (match) { match.click(); return true; }
              return false;
            }
        """)
        return bool(clicked)
    except Exception:
        return False


def _parse_com_validacao(texto: str, resultado: dict, eur_confirmado: bool):
    """
    So aceita valores se:
    - o texto contem contexto claro de EUR proximo do valor
    - OR conseguimos confirmar troca de moeda
    """
    # busca especificamente "Euro" ou "EUR" acompanhado de valor
    # padrao: "Euro ... VET: R$ X,XX"
    padrao_eur_vet = re.compile(
        r"(?:EUR|Euro)[\s\S]{0,300}?VET[:\s]+R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    m = padrao_eur_vet.search(texto)
    if m:
        try:
            resultado["vet_eur"] = float(m.group(1).replace(",", "."))
        except ValueError:
            pass

    # comercial EUR
    padrao_eur_com = re.compile(
        r"(?:EUR|Euro)[\s\S]{0,200}?[Cc][âa]mbio\s+comercial[:\s]+R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    m2 = padrao_eur_com.search(texto)
    if m2:
        try:
            resultado["cambio_comercial_eur"] = float(m2.group(1).replace(",", "."))
        except ValueError:
            pass

    # Se nao achou por proximidade, so aceita valor generico se
    # confirmamos que EUR foi selecionado E o valor esta na faixa EUR/BRL
    # (EUR turismo geralmente > 5.80 no periodo atual)
    if resultado["vet_eur"] is None and eur_confirmado:
        m3 = re.search(r"VET[:\s]+R?\$?\s*(\d{1,2}[.,]\d{2,4})", texto)
        if m3:
            try:
                v = float(m3.group(1).replace(",", "."))
                # EUR turismo em Salvador esta na faixa 6.00-8.00
                # se estiver abaixo de 5.80 quase certeza que e USD
                if v >= 5.80:
                    resultado["vet_eur"] = v
            except ValueError:
                pass


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_confidence(), indent=2, ensure_ascii=False))
