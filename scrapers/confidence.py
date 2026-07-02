"""
Scraper Confidence: DESATIVADO em 01/07/26.
Motivo: A pagina /ecommerce/ e uma SPA React que abre com USD por padrao.
Nao ha selector HTML para trocar pra EUR (tudo renderizado dinamicamente).
Tentativas de clicar via Playwright resultaram em coleta do VET do DOLAR
mostrando spread PTAX negativo (-6.62%), confirmando o bug.
Deixado desabilitado para nao poluir com falsos positivos.
Consulta manual via WhatsApp (botao no dashboard).
"""
from datetime import datetime


def scrape_confidence() -> dict:
    return {
        "fonte": "confidence",
        "url": "https://www.confidencecambio.com.br/ecommerce/",
        "timestamp": datetime.now().isoformat(),
        "vet_eur": None,
        "erro": "desativado: site so expoe USD por padrao, EUR precisa clique JS que nao funciona",
    }
