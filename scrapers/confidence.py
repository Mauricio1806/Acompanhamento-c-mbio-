"""
Scraper Confidence Cambio via API AWS publica.

Descoberto atraves de network capture (debug_network) em 02/07/26:
- Base URL: https://b8pybk7hl9.execute-api.sa-east-1.amazonaws.com/production/white-label/cotacao/api/v1/
- /cidades?cidade=Salvador -> retorna ID da cidade
- /moedas-operacionais?tipo=Especie&operacao=Venda -> lista com IDs das moedas
- /moedas-operacionais/{id}/cotacao?cidade-id={cid} -> cotacao com valor+iof+taxa

VET final = valor * (1 + iof/100) * (1 + taxa/100)
"""
import requests
from datetime import datetime


BASE_URL_V1 = "https://b8pybk7hl9.execute-api.sa-east-1.amazonaws.com/production/white-label/cotacao/api/v1"
BASE_URL_V2 = "https://b8pybk7hl9.execute-api.sa-east-1.amazonaws.com/production/white-label/cotacao/api/v2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.confidencecambio.com.br",
    "Referer": "https://www.confidencecambio.com.br/",
}

TIMEOUT = 15


def scrape_confidence() -> dict:
    """Retorna cotacao EUR turismo (papel moeda) da Confidence em Salvador."""
    resultado = {
        "fonte": "confidence_api",
        "url": BASE_URL_V1,
        "timestamp": datetime.now().isoformat(),
        "cidade_id": None,
        "cidade_nome": None,
        "moeda_id": None,
        "valor_bruto": None,
        "iof_pct": None,
        "taxa_pct": None,
        "vet_eur": None,
        "erro": None,
    }

    # 1. ID de Salvador
    try:
        r = requests.get(
            f"{BASE_URL_V1}/cidades", params={"cidade": "Salvador"},
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json().get("payload", [])
        for c in payload:
            if c.get("estado") == "BA" and c.get("nome") == "Salvador":
                resultado["cidade_id"] = c["id"]
                resultado["cidade_nome"] = c["nome"]
                break
        if resultado["cidade_id"] is None and payload:
            resultado["cidade_id"] = payload[0].get("id")
            resultado["cidade_nome"] = payload[0].get("nome")
        if resultado["cidade_id"] is None:
            resultado["erro"] = "Salvador nao encontrada em /cidades"
            return resultado
    except Exception as e:
        resultado["erro"] = f"erro /cidades: {e}"
        return resultado

    # 2. ID EUR Especie
    try:
        r = requests.get(
            f"{BASE_URL_V1}/moedas-operacionais",
            params={"tipo": "Especie", "operacao": "Venda"},
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        for m in r.json().get("payload", []):
            iso = (m.get("moeda") or {}).get("codigo_iso", "").upper()
            if iso == "EUR" and m.get("tipo") == "Especie":
                resultado["moeda_id"] = m["id"]
                break
        if resultado["moeda_id"] is None:
            resultado["erro"] = "EUR Especie nao encontrado"
            return resultado
    except Exception as e:
        resultado["erro"] = f"erro /moedas-operacionais: {e}"
        return resultado

    # 3. Cotacao (tenta v2, fallback v1)
    for base in (BASE_URL_V2, BASE_URL_V1):
        try:
            r = requests.get(
                f"{base}/moedas-operacionais/{resultado['moeda_id']}/cotacao",
                params={"cidade-id": resultado["cidade_id"]},
                headers=HEADERS, timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            payload = r.json().get("payload", {})
            venda = payload.get("venda") or {}
            valor = venda.get("valor")
            iof = venda.get("iof")
            taxa = venda.get("taxa")

            if valor and iof is not None and taxa is not None:
                valor, iof, taxa = float(valor), float(iof), float(taxa)
                vet = round(valor * (1 + iof / 100) * (1 + taxa / 100), 4)

                resultado["valor_bruto"] = round(valor, 4)
                resultado["iof_pct"] = iof
                resultado["taxa_pct"] = taxa
                resultado["vet_eur"] = vet
                return resultado
        except Exception as e:
            resultado["erro"] = f"erro /cotacao ({base[-2:]}): {e}"
            continue

    if not resultado["erro"]:
        resultado["erro"] = "endpoint /cotacao nao retornou dados validos"
    return resultado


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_confidence(), indent=2, ensure_ascii=False))
