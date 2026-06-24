"""
Módulo de cálculos financeiros para o monitor de câmbio.
IOF, spread, custo efetivo e comparativos por volume.
"""


def calcular_custo_efetivo(valor_venda, iof_rate=0.011):
    """
    Calcula custo efetivo final por EUR incluindo IOF.
    Para espécie: IOF = 1,1%
    Fórmula: valor_venda × (1 + IOF)
    """
    if valor_venda is None or valor_venda <= 0:
        return None
    return round(valor_venda * (1 + iof_rate), 4)


def calcular_spread_ptax(valor_venda, ptax_venda):
    """
    Calcula spread percentual em relação ao PTAX.
    Spread = ((valor_venda / ptax_venda) - 1) × 100
    """
    if not valor_venda or not ptax_venda or ptax_venda <= 0:
        return None
    return round(((valor_venda / ptax_venda) - 1) * 100, 2)


def calcular_spread_wise(valor_venda, wise_rate):
    """
    Calcula spread percentual em relação à taxa Wise.
    """
    if not valor_venda or not wise_rate or wise_rate <= 0:
        return None
    return round(((valor_venda / wise_rate) - 1) * 100, 2)


def calcular_variacao(valor_atual, valor_anterior):
    """
    Calcula variação em R$ e % vs dia anterior.
    Retorna (variacao_rs, variacao_pct)
    """
    if not valor_atual or not valor_anterior or valor_anterior <= 0:
        return (None, None)
    
    variacao_rs = round(valor_atual - valor_anterior, 4)
    variacao_pct = round((variacao_rs / valor_anterior) * 100, 2)
    return (variacao_rs, variacao_pct)


def calcular_custo_volume(custo_efetivo, volume_eur):
    """
    Calcula custo total em R$ para um volume em EUR.
    """
    if not custo_efetivo or custo_efetivo <= 0:
        return None
    return round(custo_efetivo * volume_eur, 2)


def calcular_economia_volume(custo_efetivo_casa, custo_efetivo_pior, volume_eur):
    """
    Calcula economia em R$ comparando com a casa mais cara.
    """
    if not custo_efetivo_casa or not custo_efetivo_pior:
        return None
    diferenca = custo_efetivo_pior - custo_efetivo_casa
    return round(diferenca * volume_eur, 2)


def verificar_discrepancia(valor_venda, ptax_venda, max_spread=3.0):
    """
    Verifica se há discrepância significativa vs PTAX.
    Retorna True se spread > max_spread%.
    """
    spread = calcular_spread_ptax(valor_venda, ptax_venda)
    if spread is None:
        return False
    return abs(spread) > max_spread


def gerar_ranking(cotacoes, volumes=[5000, 10000, 20000]):
    """
    Gera ranking das melhores cotações (menor custo efetivo).
    Retorna top 3 com diferenças por volume.
    """
    # Filtrar cotações válidas
    validas = [c for c in cotacoes if c.get("custo_efetivo") and c["custo_efetivo"] > 0]
    
    if not validas:
        return {"top3": [], "volumes": {}}
    
    # Ordenar por custo efetivo
    validas.sort(key=lambda x: x["custo_efetivo"])
    
    top3 = validas[:3]
    pior = validas[-1] if validas else None
    
    resultado = {
        "top3": [],
        "pior_custo": pior["custo_efetivo"] if pior else None,
        "volumes": {}
    }
    
    for i, casa in enumerate(top3):
        entry = {
            "posicao": i + 1,
            "casa_slug": casa.get("casa_slug"),
            "nome": casa.get("nome"),
            "custo_efetivo": casa["custo_efetivo"],
            "valor_venda": casa.get("valor_venda_especie"),
            "spread_ptax": casa.get("spread_ptax"),
            "diferenca_por_volume": {}
        }
        
        for vol in volumes:
            custo_casa = calcular_custo_volume(casa["custo_efetivo"], vol)
            custo_pior = calcular_custo_volume(pior["custo_efetivo"], vol) if pior else None
            economia = calcular_economia_volume(casa["custo_efetivo"], pior["custo_efetivo"], vol) if pior else None
            
            entry["diferenca_por_volume"][str(vol)] = {
                "custo_total_brl": custo_casa,
                "economia_vs_pior": economia
            }
        
        resultado["top3"].append(entry)
    
    return resultado
