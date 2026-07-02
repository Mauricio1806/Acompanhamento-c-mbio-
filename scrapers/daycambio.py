"""
Scraper DayCambio: DESATIVADO em 01/07/26.
Motivo: paginas /simulador-cambio-online/ e /cambio/moedas-em-especie/euro/
sao INSTITUCIONAIS (falam sobre historia do euro, nao mostram cotacao).
Cotacao real so via WhatsApp/telefone da loja.
Parser anterior gerava FALSO POSITIVO pegando qualquer numero da pagina.
"""
from datetime import datetime


def scrape_daycambio() -> dict:
    return {
        "fonte": "daycambio",
        "url": "https://www.daycambio.com.br/",
        "timestamp": datetime.now().isoformat(),
        "vet_eur": None,
        "erro": "desativado: site nao publica cotacao HTTP-acessivel, so via WhatsApp",
    }
