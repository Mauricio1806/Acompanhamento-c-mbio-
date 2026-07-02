"""
Scraper Ourominas: DESATIVADO em 01/07/26.
Motivo: URL /cotacao-do-dia retorna 404 ("OPS! NAO ENCONTRAMOS ESSA PAGINA").
A pagina de cotacao publica foi removida. Contato via telefone.
"""
from datetime import datetime


def scrape_ourominas() -> dict:
    return {
        "fonte": "ourominas",
        "url": "https://www.ourominas.com/",
        "timestamp": datetime.now().isoformat(),
        "venda_eur_especie": None,
        "erro": "desativado: URL /cotacao-do-dia retorna 404 - site removeu pagina publica",
    }
