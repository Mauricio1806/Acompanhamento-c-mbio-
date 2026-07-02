"""
Scraper MelhorCambio (multi-cidade) via Playwright.

Baseado em debug REAL do HTML/texto renderizado em 30/06/26.

Estrutura do texto renderizado (importantes):
  linha ~34: "Taxas de câmbio turismo para comprar Euro em {cidade}"
  linha ~35: "R$ 6,34"  (papel moeda menor valor)
  linha ~45: "Salvador Cãmbio"  (nome com til errado no site - normalizar)
  linha ~53: "Valor com IOF R$ 6,3411"
  linha ~65: "R$ 6,45"  (cartão pre pago menor)
  linha ~83: "Valor com IOF R$ 6,4504"
  linha ~85: "Euro Turismo em {cidade} (BA) - DATA"
  linha ~90: "ComercialR$5,8991"

O parser extrai:
  - papel_moeda_menor    (venda espécie)
  - papel_moeda_com_iof  (custo efetivo com IOF já embutido)
  - cartao_menor
  - cartao_com_iof
  - cambio_comercial     (referência tipo PTAX)
  - casa_principal       (nome da casa que aparece no topo)
"""
import re
from datetime import datetime

from scrapers.playwright_base import browser_page, PLAYWRIGHT_AVAILABLE


CIDADES = {
    "salvador":       "https://www.melhorcambio.com/cotacao/compra/euro/salvador",
    "sao-paulo":      "https://www.melhorcambio.com/cotacao/compra/euro/sao-paulo",
    "rio-de-janeiro": "https://www.melhorcambio.com/cotacao/compra/euro/rio-de-janeiro",
}


def scrape_cidade(cidade_slug: str) -> dict:
    """Scraper de uma cidade do MelhorCambio."""
    url = CIDADES.get(cidade_slug)
    if not url:
        return {"erro": f"cidade desconhecida: {cidade_slug}"}

    resultado = {
        "fonte": "melhorcambio",
        "cidade": cidade_slug,
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "papel_moeda_menor": None,
        "papel_moeda_com_iof": None,
        "cartao_menor": None,
        "cartao_com_iof": None,
        "cambio_comercial": None,
        "casa_principal": None,
        "erro": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        resultado["erro"] = "playwright nao disponivel"
        return resultado

    try:
        with browser_page(headless=True, timeout_ms=30000) as page:
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(4000)
            texto = page.evaluate("document.body.innerText") or ""
            _parse(texto, resultado)
    except Exception as e:
        resultado["erro"] = f"erro playwright: {e}"

    return resultado


def scrape_melhorcambio_salvador() -> dict:
    """Wrapper mantido para compatibilidade com main.py antigo."""
    dados = scrape_cidade("salvador")
    # transforma no formato esperado pelo main
    casas = []
    if dados.get("papel_moeda_menor") and dados.get("casa_principal"):
        casas.append({
            "nome": dados["casa_principal"],
            "slug": None,   # main.py mapeia pelo nome
            "endereco": "Salvador, BA (agregado MelhorCambio)",
            "valor_venda_especie": dados["papel_moeda_menor"],
            "valor_venda_cartao":  dados.get("cartao_menor"),
            "correspondente": None,
            "horario": None,
        })

    return {
        "fonte": "melhorcambio",
        "url": dados["url"],
        "timestamp": dados["timestamp"],
        "cambio_comercial":     dados.get("cambio_comercial"),
        "papel_moeda_menor":    dados.get("papel_moeda_menor"),
        "cartao_prepago_menor": dados.get("cartao_menor"),
        "casas": casas,
        "casas_count": len(casas),
        "erro": dados.get("erro"),
    }


def _parse(texto: str, resultado: dict):
    """
    Parsers baseados em padroes reais do HTML renderizado (debug de 30/06).
    Cada padrao e testado independentemente e nao sobrescreve valores ja obtidos.
    """
    # 1) Bloco "Euro Turismo em {cidade} (BA) - DATA" + tabela abaixo:
    #    ComercialR$5,8991
    m = re.search(r"Comercial\s*R\$\s*(\d{1,2}[.,]\d{2,4})", texto)
    if m:
        resultado["cambio_comercial"] = _to_float(m.group(1))

    # 2) "Menor Valor R$ 6,34" (papel moeda)
    #    Pode vir como "Menor ValorR$6,34" (sem espacos) ou "Menor Valor\nR$ 6,34"
    for m in re.finditer(
        r"(Papel\s+Moeda\s*Menor\s+Valor|Menor\s+Valor\s*Papel\s+Moeda|Papel\s+Moeda\W+Menor\s+Valor)\W*R\$?\s*(\d{1,2}[.,]\d{2,4})",
        texto, re.IGNORECASE,
    ):
        v = _to_float(m.group(2))
        if v and v > 3.0:
            resultado["papel_moeda_menor"] = v
            break

    # 2b) fallback: procura pela primeira linha "Papel Moeda" seguida de valor
    if resultado["papel_moeda_menor"] is None:
        # padrao mais simples que funciona no debug real:
        # "Taxas de câmbio turismo para comprar Euro em Salvador\nR$ 6,34\nPapel Moeda"
        m = re.search(
            r"comprar\s+Euro\s+em\s+\S+\W+R\$?\s*(\d{1,2}[.,]\d{2,4})\W+Papel\s+Moeda",
            texto, re.IGNORECASE,
        )
        if m:
            v = _to_float(m.group(1))
            if v and v > 3.0:
                resultado["papel_moeda_menor"] = v

    # 3) "Cartão Pré-Pago Menor Valor R$ 6,45"
    for m in re.finditer(
        r"Cart[ãa]o\s+Pr[ée][-\s]?Pago\s*Menor\s+Valor\W*R\$?\s*(\d{1,2}[.,]\d{2,4})",
        texto, re.IGNORECASE,
    ):
        v = _to_float(m.group(1))
        if v and v > 3.0:
            resultado["cartao_menor"] = v
            break

    # 4) "Valor com IOF R$ X,XXXX" - aparece 2x na pagina (papel e cartao)
    valores_com_iof = re.findall(r"Valor\s+com\s+IOF\W*R\$?\s*(\d{1,2}[.,]\d{2,4})", texto, re.IGNORECASE)
    if len(valores_com_iof) >= 1:
        v = _to_float(valores_com_iof[0])
        if v and v > 3.0:
            resultado["papel_moeda_com_iof"] = v
    if len(valores_com_iof) >= 2:
        v = _to_float(valores_com_iof[1])
        if v and v > 3.0:
            resultado["cartao_com_iof"] = v

    # 5) Nome da casa principal - aparece logo apos o valor R$ X,XX no bloco de papel
    #    No debug real: "R$ 6,34\n\nPapel Moeda  0,00%\n...\nR$ 6,29\nFaça oferta →\nSalvador Cãmbio"
    #    Vamos procurar antes de "Fazer uma oferta" ou "Faça oferta"
    m = re.search(
        r"Fa[çc]a\s+oferta\s*[→>»]?\s*\n?\s*([A-ZÀ-Ú][\w\sÃãáâàéêíóôõúçÇ\-]{3,60}?)\s*\n",
        texto,
    )
    if m:
        nome = m.group(1).strip()
        # normaliza "Salvador Cãmbio" -> "Salvador Câmbio"
        nome = nome.replace("Cãmbio", "Câmbio").replace("cãmbio", "câmbio")
        if len(nome) > 4 and "R$" not in nome:
            resultado["casa_principal"] = nome


def _to_float(s: str) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") <= 1
                     else s.replace(",", "."))
    except ValueError:
        return None


if __name__ == "__main__":
    import json
    for cidade in ["salvador", "sao-paulo", "rio-de-janeiro"]:
        print(f"\n=== {cidade} ===")
        print(json.dumps(scrape_cidade(cidade), indent=2, ensure_ascii=False))
