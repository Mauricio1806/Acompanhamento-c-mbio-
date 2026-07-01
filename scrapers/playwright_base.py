"""
Base Playwright: cliente compartilhado pelos scrapers de casas de cambio
que so servem cotacao via JavaScript.

Usa playwright.sync_api. Ajustado para rodar em GitHub Actions runners.
"""
import re
from contextlib import contextmanager
from typing import Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@contextmanager
def browser_page(headless: bool = True, timeout_ms: int = 30000):
    """
    Context manager que abre um navegador Chromium e retorna uma page pronta.
    Fecha tudo mesmo em caso de erro.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "playwright nao instalado. rode: pip install playwright && "
            "playwright install chromium"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            locale="pt-BR",
            timezone_id="America/Bahia",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            yield page
        finally:
            context.close()
            browser.close()


def parse_brl(text: Optional[str]) -> Optional[float]:
    """Extrai float de string tipo 'R$ 6,42' ou '6,4200'."""
    if not text:
        return None
    text = str(text).strip().replace("R$", "").replace("\xa0", " ").strip()
    m = re.search(r"(\d{1,3})[.,](\d{2,4})", text)
    if m:
        try:
            return float(f"{m.group(1)}.{m.group(2)}")
        except ValueError:
            return None
    m = re.search(r"(\d+)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def find_prices_in_range(text: str, lo: float = 4.0, hi: float = 15.0) -> list[float]:
    """
    Encontra todos os valores no texto que parecem ser cotacao EUR/BRL,
    dentro de uma faixa plausivel.
    """
    padrao = re.compile(r"R?\$?\s*(\d{1,2}[.,]\d{2,4})")
    encontrados = []
    for m in padrao.finditer(text):
        v = parse_brl(m.group(1))
        if v is not None and lo <= v <= hi:
            encontrados.append(v)
    # deduplica preservando ordem
    seen = set()
    result = []
    for v in encontrados:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result
