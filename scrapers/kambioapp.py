"""
Scraper KambioApp - agregador de cotacoes de casas de cambio.

URL: https://www.kambioapp.com.br/pt/cambio/comprar-euro-com-real/brasil/ba/salvador

Retorna lista de casas de Salvador com cotacao de EUR.
Formato do HTML (extraido em 03/07/26):

    ### {NomeCasa}
    Fechado / Aberto
    {Endereco}
    Atualizado ha X horas
    Cotacao CompraR$ 6,XXXX
    [Ver Contatos](url)

IMPORTANTE: valores JA VEM COM IOF (o site diz "Valores COM IOF").
Nosso pipeline vai dividir pelo IOF pra registrar o "valor bruto".
"""
import re
import requests
from datetime import datetime

from bs4 import BeautifulSoup


URL = "https://www.kambioapp.com.br/pt/cambio/comprar-euro-com-real/brasil/ba/salvador"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

TIMEOUT = 20


def scrape_kambioapp() -> dict:
    """
    Retorna dict:
    {
      "fonte": "kambioapp",
      "timestamp": "...",
      "casas": [
        {
          "nome_kambio": "Confidence",
          "endereco": "Avenida Tancredo Neves, 2915 - PISO L1 - Caminho das Árvores",
          "valor_com_iof": 6.4953,   # ja inclui IOF
          "url_detalhe": "https://www.kambioapp.com.br/pt/casas-de-cambio/..."
        }, ...
      ],
      "casas_count": N,
      "erro": None
    }
    """
    resultado = {
        "fonte": "kambioapp",
        "url": URL,
        "timestamp": datetime.now().isoformat(),
        "casas": [],
        "casas_count": 0,
        "erro": None,
    }

    try:
        r = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        resultado["erro"] = f"erro request: {e}"
        return resultado

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        # cada casa aparece como um bloco. Estrutura vista:
        #   h3 com nome + parágrafo com endereco + span com "Cotacao Compra R$ X,XXXX"
        #   + link "Ver Contatos"
        # abordagem robusta: procurar por TODOS os "Cotação Compra R$" e voltar pro pai

        casas = []
        # padrao 1: procurar por links "Ver Contatos" pra achar os blocos
        for link in soup.find_all("a", string=re.compile(r"Ver\s+Contatos", re.IGNORECASE)):
            url_detalhe = link.get("href", "")
            if url_detalhe and not url_detalhe.startswith("http"):
                url_detalhe = "https://www.kambioapp.com.br" + url_detalhe

            # sobe ate o container e extrai texto
            container = link.parent
            # sobe umas 3-4 vezes ate ter todo o card
            for _ in range(5):
                if container is None:
                    break
                texto = container.get_text(" ", strip=True)
                if "Cotação Compra" in texto or "Cotacao Compra" in texto:
                    break
                container = container.parent

            if container is None:
                continue

            texto = container.get_text("\n", strip=True)
            info = _parse_bloco(texto, url_detalhe)
            if info:
                casas.append(info)

        # dedup por (nome + endereco)
        vistos = set()
        casas_dedup = []
        for c in casas:
            chave = (c["nome_kambio"].lower().strip(), (c["endereco"] or "").lower().strip()[:80])
            if chave in vistos:
                continue
            vistos.add(chave)
            casas_dedup.append(c)

        resultado["casas"] = casas_dedup
        resultado["casas_count"] = len(casas_dedup)

        # Fallback: se BS4 nao pegou, tentar via regex direto
        if not casas_dedup:
            casas_regex = _parse_via_regex(r.text)
            resultado["casas"] = casas_regex
            resultado["casas_count"] = len(casas_regex)

    except Exception as e:
        resultado["erro"] = f"erro parsing: {e}"

    return resultado


def _parse_bloco(texto: str, url_detalhe: str) -> dict | None:
    """
    Parseia o texto de um card de casa. Espera algo como:
      Confidence
      Fechado
      Avenida Tancredo Neves, 2915 - PISO L1 - Caminho das Árvores
      Atualizado ha 14 horas
      Cotacao Compra R$ 6,4953
      Ver Contatos
    """
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]

    nome = None
    endereco = None
    valor = None

    for i, linha in enumerate(linhas):
        # nome vem antes de "Fechado" ou "Aberto"
        if linha in ("Fechado", "Aberto") and i > 0 and nome is None:
            candidato = linhas[i - 1]
            # ignora iniciais como "CO", "LA", "DA", "LU"
            if len(candidato) > 3:
                nome = candidato

        # endereco: depois de Fechado/Aberto, tipicamente contem "Av." ou "R." ou "Rua"
        if endereco is None and ("Av." in linha or "Avenida" in linha or "Rua" in linha
                                  or "R." in linha):
            if "Cotação" not in linha and "Compra" not in linha:
                endereco = linha

        # valor
        m = re.search(r"Cota[çc][ãa]o\s+Compra\s*R?\$?\s*(\d{1,2}[.,]\d{2,4})", linha)
        if m:
            try:
                valor = float(m.group(1).replace(",", "."))
            except ValueError:
                pass

    if not valor:
        return None
    if valor < 4.0 or valor > 15.0:
        return None
    if not nome:
        # fallback: pega primeira linha nao vazia que nao seja Fechado/Aberto
        for linha in linhas:
            if linha not in ("Fechado", "Aberto") and len(linha) > 3:
                nome = linha
                break

    return {
        "nome_kambio": nome or "Desconhecido",
        "endereco": endereco,
        "valor_com_iof": valor,
        "url_detalhe": url_detalhe,
    }


def _parse_via_regex(html: str) -> list:
    """Fallback: extrai casas via regex direta no HTML."""
    casas = []
    # padrao: nome (h3) ... endereco ... "Cotacao Compra R$ X,XXXX" ... link
    pattern = re.compile(
        r"<h3[^>]*>([^<]+)</h3>[\s\S]{0,300}?"
        r"([^<>\n]{15,200}?)[\s\S]{0,150}?"
        r"Cota[çc][ãa]o\s+Compra[^\d]*R?\$?\s*(\d{1,2}[.,]\d{2,4})",
        re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        try:
            valor = float(m.group(3).replace(",", "."))
            if 4.0 <= valor <= 15.0:
                casas.append({
                    "nome_kambio": m.group(1).strip(),
                    "endereco": m.group(2).strip()[:200],
                    "valor_com_iof": valor,
                    "url_detalhe": None,
                })
        except ValueError:
            continue
    return casas


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_kambioapp(), indent=2, ensure_ascii=False))
