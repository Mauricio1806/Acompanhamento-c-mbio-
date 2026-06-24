"""
Módulo base de scraping para casas de câmbio.
Utiliza requests + BeautifulSoup para sites acessíveis via HTTP,
e fornece estrutura para coleta via browser automation pelo agente.
"""
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
}


def extract_price_from_text(text):
    """
    Extrai valor numérico de um texto com preço.
    Ex: "R$ 6,45" -> 6.45, "6.4500" -> 6.45
    """
    if not text:
        return None
    
    # Limpar texto
    text = text.strip().replace("R$", "").strip()
    
    # Formato brasileiro: 6,4500 ou 6.450,00
    match = re.search(r'(\d{1,2})[.,](\d{2,4})', text)
    if match:
        inteiro = match.group(1)
        decimal = match.group(2)
        try:
            return float(f"{inteiro}.{decimal}")
        except ValueError:
            pass
    
    # Formato decimal padrão
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    
    return None


def scrape_confidence():
    """
    Tenta extrair cotação EUR da Confidence Câmbio via HTTP.
    Nota: O site usa lazy loading pesado, pode não funcionar sem JS.
    """
    try:
        url = "https://www.confidencecambio.com.br/euro-hoje/"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'lxml')
        
        # Procurar por valores de cotação
        # A Confidence geralmente mostra valores em spans ou divs específicas
        price_elements = soup.find_all(text=re.compile(r'R\$\s*\d'))
        
        for elem in price_elements:
            price = extract_price_from_text(elem)
            if price and 4.0 < price < 15.0:  # Faixa razoável EUR/BRL
                return {
                    "valor_venda_especie": price,
                    "fonte": "confidence_http",
                    "timestamp": datetime.now().isoformat()
                }
        
        return None
    
    except Exception as e:
        print(f"[Confidence] Erro HTTP: {e}")
        return None


def scrape_melhorcambio_salvador():
    """
    Tenta extrair cotações do MelhorCâmbio para Salvador.
    """
    try:
        url = "https://www.melhorcambio.com/euro/salvador"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.text, 'lxml')
        resultados = []
        
        # Procurar por cards de casas de câmbio
        # MelhorCâmbio tipicamente lista casas com nome e valor
        store_cards = soup.find_all(class_=re.compile(r'store|casa|cambio|card', re.I))
        
        for card in store_cards:
            nome_elem = card.find(class_=re.compile(r'name|nome|title', re.I))
            price_elem = card.find(class_=re.compile(r'price|valor|rate|cotacao', re.I))
            
            if nome_elem and price_elem:
                nome = nome_elem.get_text(strip=True)
                price = extract_price_from_text(price_elem.get_text())
                
                if price and 4.0 < price < 15.0:
                    resultados.append({
                        "nome": nome,
                        "valor_venda_especie": price,
                        "fonte": "melhorcambio",
                        "timestamp": datetime.now().isoformat()
                    })
        
        return resultados
    
    except Exception as e:
        print(f"[MelhorCâmbio] Erro: {e}")
        return []


def get_cotacoes_web_search():
    """
    Estrutura para cotações obtidas via web search pelo agente.
    O agente preenche estes dados via busca e browser automation.
    """
    return {
        "method": "agent_web_search",
        "description": "Cotações coletadas via pesquisa web e automação de browser pelo agente",
        "casas": []
    }
