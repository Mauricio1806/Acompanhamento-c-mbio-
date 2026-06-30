"""
Scrapers de referencia: PTAX (Banco Central) e Wise.
Mantido do projeto original do Abacus (foi validado que funciona).
"""
import requests
from datetime import datetime, timedelta


HEADERS_WISE = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def get_ptax_eur(data: str | None = None) -> dict | None:
    """
    Obtem cotacao PTAX EUR/BRL do dia (ou data informada).
    A API do BCB so retorna em dias uteis; se vier vazio, tenta os 5 dias
    anteriores para nao quebrar em finais de semana e feriados.
    """
    base_url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
        "?@moeda='EUR'&@dataCotacao='{data}'&$format=json"
    )

    if data is None:
        agora = datetime.now()
    else:
        agora = datetime.strptime(data, "%m-%d-%Y")

    # tenta hoje, depois ate 5 dias atras
    for delta in range(0, 6):
        d = agora - timedelta(days=delta)
        data_str = d.strftime("%m-%d-%Y")
        try:
            resp = requests.get(base_url.format(data=data_str), timeout=15)
            resp.raise_for_status()
            dados = resp.json()
            values = dados.get("value", [])
            if values:
                ultimo = values[-1]
                return {
                    "data_referencia": data_str,
                    "cotacao_compra": ultimo.get("cotacaoCompra"),
                    "cotacao_venda": ultimo.get("cotacaoVenda"),
                    "data_hora": ultimo.get("dataHoraCotacao"),
                    "tipo_boletim": ultimo.get("tipoBoletim"),
                }
        except Exception as e:
            print(f"[PTAX] erro {data_str}: {e}")
            continue

    return None


def get_wise_rate() -> dict | None:
    """
    Obtem taxa EUR/BRL da Wise (benchmark digital).
    """
    url = "https://wise.com/rates/live?source=EUR&target=BRL"
    try:
        resp = requests.get(url, headers=HEADERS_WISE, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        return {
            "rate": dados.get("value"),
            "timestamp": dados.get("time"),
            "source": "EUR",
            "target": "BRL",
        }
    except Exception as e:
        print(f"[Wise] erro: {e}")
        return None


if __name__ == "__main__":
    print("PTAX:", get_ptax_eur())
    print("Wise:", get_wise_rate())
