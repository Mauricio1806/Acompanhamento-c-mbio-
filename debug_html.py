#!/usr/bin/env python3
"""
Debug script: abre cada site de casa de cambio, tira screenshot e salva
HTML + innerText renderizados. Util pra debugar por que o scraper nao acha
a cotacao EUR.

Roda via GitHub Actions (workflow debug-scrape.yml) e os arquivos gerados
sao upados como artifact.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.playwright_base import browser_page


SITES = [
    {
        "nome": "confidence-ecommerce",
        "url": "https://www.confidencecambio.com.br/ecommerce/",
        "acao": "tentar_selecionar_eur",
    },
    {
        "nome": "confidence-euro-hoje",
        "url": "https://www.confidencecambio.com.br/euro-hoje/",
        "acao": None,
    },
    {
        "nome": "daycambio-simulador",
        "url": "https://www.daycambio.com.br/simulador-cambio-online/",
        "acao": "tentar_selecionar_eur",
    },
    {
        "nome": "daycambio-euro-pagina",
        "url": "https://www.daycambio.com.br/cambio/moedas-em-especie/euro/",
        "acao": None,
    },
    {
        "nome": "ourominas-cotacao",
        "url": "https://www.ourominas.com/cotacao-do-dia",
        "acao": None,
    },
    {
        "nome": "melhorcambio-salvador",
        "url": "https://www.melhorcambio.com/cotacao/compra/euro/salvador",
        "acao": None,
    },
]


def tentar_selecionar_eur(page):
    for sel in [
        "select option[value*='EUR' i]",
        "button:has-text('EUR')",
        "button:has-text('Euro')",
        "a:has-text('EUR')",
        "a:has-text('Euro')",
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=2500, force=True)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    try:
        page.evaluate("""
            () => {
              const nodes = Array.from(document.querySelectorAll('button, a, [role=button], option, div'));
              const match = nodes.find(n => /\\bEUR\\b|\\bEuro\\b/i.test((n.innerText || '').trim()));
              if (match) { match.click(); return true; }
              return false;
            }
        """)
    except Exception:
        pass
    return False


def main():
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")
    os.makedirs(outdir, exist_ok=True)

    resumo = []

    for site in SITES:
        print(f"\n=== {site['nome']} ===")
        base_path = os.path.join(outdir, site["nome"])

        info = {
            "nome": site["nome"],
            "url": site["url"],
            "timestamp": datetime.now().isoformat(),
            "status_http": None,
            "titulo": None,
            "erro": None,
        }

        try:
            with browser_page(headless=True, timeout_ms=30000) as page:
                resp = page.goto(site["url"], wait_until="domcontentloaded", timeout=35000)
                info["status_http"] = resp.status if resp else None
                page.wait_for_timeout(5000)

                if site["acao"] == "tentar_selecionar_eur":
                    trocado = tentar_selecionar_eur(page)
                    info["eur_selecionado"] = trocado
                    page.wait_for_timeout(3000)

                info["titulo"] = page.title()

                # screenshot da tela toda (viewport)
                try:
                    page.screenshot(path=f"{base_path}.png", full_page=True)
                    print(f"  screenshot OK: {site['nome']}.png")
                except Exception as e:
                    print(f"  screenshot falhou: {e}")

                # HTML renderizado
                try:
                    html = page.content()
                    with open(f"{base_path}.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"  HTML OK: {len(html)} chars")
                except Exception as e:
                    print(f"  HTML falhou: {e}")

                # innerText (o que meu scraper enxerga)
                try:
                    texto = page.evaluate("document.body.innerText") or ""
                    with open(f"{base_path}.txt", "w", encoding="utf-8") as f:
                        f.write(texto)
                    print(f"  innerText OK: {len(texto)} chars")

                    # tenta identificar linhas com EUR/Euro/R$
                    linhas_relevantes = []
                    for linha in texto.split("\n"):
                        l = linha.strip()
                        if not l:
                            continue
                        low = l.lower()
                        if "euro" in low or "eur" in low.split() or "r$" in low:
                            linhas_relevantes.append(l[:200])
                    info["linhas_relevantes"] = linhas_relevantes[:30]
                except Exception as e:
                    print(f"  innerText falhou: {e}")
                    info["erro"] = str(e)

        except Exception as e:
            info["erro"] = str(e)
            print(f"  ERRO GERAL: {e}")

        resumo.append(info)

    # salva resumo
    import json
    with open(os.path.join(outdir, "_resumo.json"), "w", encoding="utf-8") as f:
        json.dump(resumo, f, indent=2, ensure_ascii=False)

    print(f"\n=== FIM ===\nArquivos gerados em: {outdir}/")
    for site in SITES:
        for ext in [".png", ".html", ".txt"]:
            p = os.path.join(outdir, site["nome"] + ext)
            if os.path.exists(p):
                print(f"  {os.path.getsize(p):>10} {p}")


if __name__ == "__main__":
    main()
