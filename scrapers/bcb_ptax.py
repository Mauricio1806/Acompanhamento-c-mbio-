"""
Scraper para PTAX do Banco Central do Brasil.
Usa API pública OLINDA/SGS.
"""
import requests
from datetime import datetime


def get_ptax_eur(data=None):
    """
    Obtém cotação PTAX EUR/BRL do dia.
    Retorna o último boletim disponível (venda).
    """
    if data is None:
        data = datetime.now().strftime("%m-%d-%Y")
    
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
        f"?@moeda='EUR'&@dataCotacao='{data}'&$format=json"
    )
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        dados = response.json()
        
        values = dados.get("value", [])
        if not values:
            return None
        
        # Pegar o último boletim do dia
        ultimo = values[-1]
        
        return {
            "cotacao_compra": ultimo.get("cotacaoCompra"),
            "cotacao_venda": ultimo.get("cotacaoVenda"),
            "data_hora": ultimo.get("dataHoraCotacao"),
            "tipo_boletim": ultimo.get("tipoBoletim"),
            "paridade_compra": ultimo.get("paridadeCompra"),
            "paridade_venda": ultimo.get("paridadeVenda")
        }
    
    except Exception as e:
        print(f"[BCB PTAX] Erro ao buscar PTAX: {e}")
        return None


def get_wise_rate():
    """
    Obtém taxa EUR/BRL da Wise (benchmark digital).
    """
    url = "https://wise.com/rates/live?source=EUR&target=BRL"
    
    try:
        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }, timeout=15)
        response.raise_for_status()
        dados = response.json()
        
        return {
            "rate": dados.get("value"),
            "timestamp": dados.get("time"),
            "source": "EUR",
            "target": "BRL"
        }
    
    except Exception as e:
        print(f"[Wise] Erro ao buscar taxa: {e}")
        return None


if __name__ == "__main__":
    ptax = get_ptax_eur()
    print(f"PTAX EUR/BRL: {ptax}")
    
    wise = get_wise_rate()
    print(f"Wise EUR/BRL: {wise}")
