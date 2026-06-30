"""
Scraper do MelhorCambio para Salvador (BA).

A pagina https://www.melhorcambio.com/cotacao/compra/euro/salvador lista as
casas de cambio de Salvador com cotacoes EUR turismo (papel moeda) e
cartao pre-pago (VTM).

O scraper extrai:
- Cotacao papel moeda menor valor (referencia principal)
- Cotacao cartao pre-pago menor valor
- Cambio comercial de referencia
- Lista de casas com nome, endereco, horario e cotacao individual
"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional


URL_MELHORCAMBIO_SALVADOR = "https://www.melhorcambio.com/cotacao/compra/euro/salvador"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}


def _parse_brl(text: Optional[str]) -> Optional[float]:
    """Converte string 'R$ 6,2705' ou '6,27' em float 6.2705."""
    if not text:
        return None
    text = text.strip().replace("R$", "").replace("\xa0", "").strip()
    # padrao brasileiro: virgula como decimal
    match = re.search(r"(\d{1,2})[.,](\d{2,4})", text)
    if not match:
        match = re.search(r"(\d+)", text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    inteiro, decimal = match.group(1), match.group(2)
    try:
        return float(f"{inteiro}.{decimal}")
    except ValueError:
        return None


def _slugify(text: str) -> str:
    """Gera slug simples a partir do nome da casa."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "casa-desconhecida"


def scrape_melhorcambio_salvador() -> dict:
    """
    Faz scraping da pagina do MelhorCambio para Salvador.

    Retorna dict no formato:
    {
      "fonte": "melhorcambio",
      "url": "...",
      "timestamp": "...",
      "cambio_comercial": 5.8357,
      "papel_moeda_menor": 6.27,
      "cartao_prepago_menor": 6.38,
      "casas": [
        {
          "nome": "Salvador Cambio",
          "slug": "salvador-cambio-mc",
          "endereco": "Av Ant Carlos Magalhaes, 656...",
          "horario": "SEG/SEX - 09h as 19h...",
          "valor_venda_especie": 6.2705,
          "valor_venda_cartao": 6.3804,
          "correspondente": "BCO DAYCOVAL S.A"
        }
      ],
      "casas_count": 1
    }
    """
    resultado = {
        "fonte": "melhorcambio",
        "url": URL_MELHORCAMBIO_SALVADOR,
        "timestamp": datetime.now().isoformat(),
        "cambio_comercial": None,
        "papel_moeda_menor": None,
        "cartao_prepago_menor": None,
        "casas": [],
        "casas_count": 0,
        "erro": None,
    }

    try:
        resp = requests.get(URL_MELHORCAMBIO_SALVADOR, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        resultado["erro"] = f"Erro ao baixar pagina: {e}"
        return resultado

    soup = BeautifulSoup(html, "lxml")

    # ----- 1. Tabela resumo: papel moeda menor/maior, comercial, cartao -----
    # No HTML real existe uma <table> com:
    # Papel Moeda Menor Valor | R$6,27
    # Cambio Comercial        | R$5,8357
    # Cartao Pre-Pago Menor   | R$6,38
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).lower()
            value_text = cells[1].get_text(" ", strip=True)
            value = _parse_brl(value_text)
            if value is None or value <= 0:
                continue
            if "papel" in label and "menor" in label:
                resultado["papel_moeda_menor"] = value
            elif "cartao" in label and "menor" in label or ("cart" in label and "menor" in label):
                resultado["cartao_prepago_menor"] = value
            elif "comercial" in label:
                resultado["cambio_comercial"] = value

    # ----- 2. Lista de casas (cards) -----
    # O MelhorCambio renderiza cada casa em um bloco com nome, endereco, horario
    # e dois valores (papel moeda e cartao pre-pago, ja com IOF).
    # Heuristica: procurar elementos com texto "Valor com IOF" e subir na arvore.
    casas_vistas = set()
    iof_nodes = soup.find_all(string=re.compile(r"Valor\s+com\s+IOF", re.IGNORECASE))
    for node in iof_nodes:
        # subir ate achar um bloco que contenha endereco/horario
        bloco = node
        for _ in range(8):
            if bloco is None or bloco.parent is None:
                break
            bloco = bloco.parent
            texto_bloco = bloco.get_text(" ", strip=True) if hasattr(bloco, "get_text") else ""
            if "Salvador" in texto_bloco and ("BA" in texto_bloco or "Bahia" in texto_bloco):
                break

        if bloco is None or not hasattr(bloco, "get_text"):
            continue

        texto = bloco.get_text("\n", strip=True)

        # nome: primeira linha relevante (geralmente acima do endereco)
        nome = _extrair_nome_casa(bloco, texto)
        if not nome:
            continue

        # evitar duplicatas
        chave = nome.lower()
        if chave in casas_vistas:
            continue
        casas_vistas.add(chave)

        endereco = _extrair_endereco(texto)
        horario = _extrair_horario(texto)
        correspondente = _extrair_correspondente(texto)
        valores = _extrair_valores_iof(texto)

        casa = {
            "nome": nome,
            "slug": _slugify(nome) + "-mc",  # sufixo pra nao colidir com config
            "endereco": endereco,
            "horario": horario,
            "correspondente": correspondente,
            "valor_venda_especie": valores.get("especie"),
            "valor_venda_cartao": valores.get("cartao"),
        }
        # so adiciona se pelo menos um valor for plausivel
        if casa["valor_venda_especie"] or casa["valor_venda_cartao"]:
            resultado["casas"].append(casa)

    resultado["casas_count"] = len(resultado["casas"])

    # Fallback: se nao achou casa nenhuma mas tem papel_moeda_menor,
    # cria casa "anonima" para nao perder o dado.
    if not resultado["casas"] and resultado["papel_moeda_menor"]:
        resultado["casas"].append({
            "nome": "MelhorCambio (agregado Salvador)",
            "slug": "melhorcambio-agregado",
            "endereco": "Salvador, BA (multiplas casas)",
            "horario": "Variavel",
            "correspondente": None,
            "valor_venda_especie": resultado["papel_moeda_menor"],
            "valor_venda_cartao": resultado["cartao_prepago_menor"],
        })
        resultado["casas_count"] = 1

    return resultado


# ---------- helpers de extracao ----------

def _extrair_nome_casa(bloco, texto: str) -> Optional[str]:
    """Tenta extrair o nome da casa a partir do bloco HTML."""
    # 1. procurar headings
    for tag in ["h2", "h3", "h4", "strong", "b"]:
        el = bloco.find(tag) if hasattr(bloco, "find") else None
        if el:
            nome = el.get_text(" ", strip=True)
            if nome and 3 < len(nome) < 80 and "Euro" not in nome and "Valor" not in nome:
                return nome
    # 2. heuristica de texto: primeira linha "limpa"
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    blacklist = ("R$", "Euro", "Papel", "Cartao", "Cartão", "Valor", "IOF",
                 "Faca", "Faça", "Ligar", "Site", "Voltar", "SEG", "SAB",
                 "Habilitado", "Correspondente")
    for linha in linhas:
        if any(b.lower() in linha.lower() for b in blacklist):
            continue
        if 3 < len(linha) < 80:
            return linha
    return None


def _extrair_endereco(texto: str) -> Optional[str]:
    """Endereco geralmente tem 'Av', 'Rua', 'R.', 'Praca' + 'Salvador' / 'BA'."""
    # capturar linhas com indicador de logradouro + Salvador/BA
    padrao = re.compile(
        r"((?:Av\.?|Avenida|Rua|R\.|Praca|Praça|Estrada|Rod\.?|Rodovia)[^\n]{5,150}?(?:Salvador\s*-\s*BA|Salvador/BA|Salvador,\s*BA))",
        re.IGNORECASE,
    )
    m = padrao.search(texto)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def _extrair_horario(texto: str) -> Optional[str]:
    """Horario geralmente vem como 'SEG/SEX - 09h as 19h'."""
    padrao = re.compile(
        r"((?:SEG|SAB|DOM|TER|QUA|QUI|SEX)[A-Z/\s-]*\d{1,2}\s*h[^\n]{0,80})",
        re.IGNORECASE,
    )
    m = padrao.search(texto)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def _extrair_correspondente(texto: str) -> Optional[str]:
    """Linha do tipo 'Correspondente Cambial BCO DAYCOVAL S.A [31707]'."""
    padrao = re.compile(r"Correspondente\s+Cambial\s+([^\[\n]{3,80})", re.IGNORECASE)
    m = padrao.search(texto)
    if m:
        return m.group(1).strip()
    padrao2 = re.compile(r"(BCO\s+\w[\w\s\.]{3,40})", re.IGNORECASE)
    m2 = padrao2.search(texto)
    if m2:
        return m2.group(1).strip()
    return None


def _extrair_valores_iof(texto: str) -> dict:
    """
    Extrai os dois valores 'Valor com IOF R$ X,XXXX' (especie e cartao).
    Convencao no site: primeiro = papel moeda, segundo = cartao pre-pago.
    """
    padrao = re.compile(r"Valor\s+com\s+IOF\s*R?\$?\s*(\d{1,2}[.,]\d{2,4})", re.IGNORECASE)
    matches = padrao.findall(texto)
    valores = [_parse_brl(m) for m in matches if _parse_brl(m)]
    out = {"especie": None, "cartao": None}
    if len(valores) >= 1:
        out["especie"] = valores[0]
    if len(valores) >= 2:
        out["cartao"] = valores[1]
    return out


if __name__ == "__main__":
    import json
    dados = scrape_melhorcambio_salvador()
    print(json.dumps(dados, indent=2, ensure_ascii=False))
