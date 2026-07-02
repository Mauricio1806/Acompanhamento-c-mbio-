#!/usr/bin/env python3
"""
Debug de network: intercepta todas requests XHR/fetch dos sites.

Objetivo: descobrir quais APIs internas cada SPA (Confidence, DayCambio,
Ourominas) chama para obter cotacao EUR. Uma vez identificadas, podemos
chamar a API direto sem precisar Playwright.

Salva por site:
- {nome}_requests.json: lista de todas requests (url, method, status, tipo)
- {nome}_responses.json: content-type e primeiros ~2KB de cada JSON response
- {nome}_apis_eur.json: apenas responses que contem "EUR", "Euro", "eur" no body
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.playwright_base import browser_page


SITES = [
    {
        "nome": "confidence-ecommerce",
        "url": "https://www.confidencecambio.com.br/ecommerce/",
        "interacoes": ["tentar_clicar_eur"],
    },
    {
        "nome": "confidence-comprar-euro",
        "url": "https://www.confidencecambio.com.br/comprar-euro-online/",
        "interacoes": [],
    },
    {
        "nome": "daycambio-simulador",
        "url": "https://www.daycambio.com.br/simulador-cambio-online/",
        "interacoes": ["tentar_clicar_eur"],
    },
    {
        "nome": "daycambio-cotacoes",
        "url": "https://www.daycambio.com.br/cotacoes/",
        "interacoes": [],
    },
    {
        "nome": "ourominas-home",
        "url": "https://www.ourominas.com/",
        "interacoes": [],
    },
    {
        "nome": "ourominas-cambio",
        "url": "https://www.ourominas.com/cambio",
        "interacoes": [],
    },
]


def tentar_clicar_eur(page):
    """Tenta clicar em qualquer coisa que tenha 'EUR' ou 'Euro'."""
    try:
        page.evaluate("""
            () => {
              const candidatos = Array.from(document.querySelectorAll('*'));
              for (const c of candidatos) {
                const txt = (c.innerText || c.textContent || '').trim();
                if (/^(EUR|Euro)$/i.test(txt) && c.offsetParent !== null) {
                  c.click();
                  return true;
                }
              }
              return false;
            }
        """)
    except Exception:
        pass


def coletar_site(site: dict, outdir: str):
    nome = site["nome"]
    print(f"\n=== {nome} ({site['url']}) ===")

    requests_data = []      # todas as requests
    responses_data = []     # response bodies (limitados)
    apis_eur = []           # responses que mencionam EUR/Euro

    with browser_page(headless=True, timeout_ms=30000) as page:

        def on_request(request):
            requests_data.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
                "post_data": (request.post_data or "")[:500],
            })

        def on_response(response):
            try:
                ct = (response.headers or {}).get("content-type", "")
                # so pega XHR/fetch com JSON
                if response.request.resource_type not in ("xhr", "fetch"):
                    return
                if "json" not in ct.lower() and "javascript" not in ct.lower():
                    return

                body = ""
                try:
                    body = response.text()[:2000]  # limita 2KB
                except Exception:
                    return

                if not body:
                    return

                entry = {
                    "url": response.url,
                    "status": response.status,
                    "content_type": ct,
                    "body_preview": body,
                }
                responses_data.append(entry)

                # marca como candidato se contem EUR/Euro
                low = body.lower()
                if "eur" in low or '"euro"' in low or "6.3" in low or "6.4" in low or "6.5" in low:
                    apis_eur.append(entry)
            except Exception as e:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            print(f"  navegando...")
            page.goto(site["url"], wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(5000)

            for interacao in site.get("interacoes") or []:
                if interacao == "tentar_clicar_eur":
                    print(f"  tentando clicar em EUR...")
                    tentar_clicar_eur(page)
                    page.wait_for_timeout(3000)

            # aguarda extra pra requests tardios
            page.wait_for_timeout(3000)

        except Exception as e:
            print(f"  ERRO: {e}")

    print(f"  {len(requests_data)} requests | {len(responses_data)} JSON responses | "
          f"{len(apis_eur)} candidatos EUR")

    base = os.path.join(outdir, nome)
    with open(f"{base}_requests.json", "w", encoding="utf-8") as f:
        json.dump(requests_data, f, indent=2, ensure_ascii=False)
    with open(f"{base}_responses.json", "w", encoding="utf-8") as f:
        json.dump(responses_data, f, indent=2, ensure_ascii=False)
    with open(f"{base}_apis_eur.json", "w", encoding="utf-8") as f:
        json.dump(apis_eur, f, indent=2, ensure_ascii=False)


def main():
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_network")
    os.makedirs(outdir, exist_ok=True)

    for site in SITES:
        try:
            coletar_site(site, outdir)
        except Exception as e:
            print(f"[{site['nome']}] falha total: {e}")

    print(f"\n=== FIM ===\nArquivos em: {outdir}/")
    for f in sorted(os.listdir(outdir)):
        p = os.path.join(outdir, f)
        print(f"  {os.path.getsize(p):>10} {f}")


if __name__ == "__main__":
    main()
