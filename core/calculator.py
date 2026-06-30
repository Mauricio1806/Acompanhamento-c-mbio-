"""
Calculos financeiros: custo efetivo, spread vs PTAX/Wise, variacao,
ranking por volume.
"""
from typing import Iterable


def calcular_custo_efetivo(valor_venda: float, iof: float = 0.011) -> float:
    """
    Custo final por EUR considerando IOF de operacao em especie.
    IOF padrao para especie e 1.1% (Decreto 12.499/2025); o config.yaml pode
    sobrescrever.
    """
    if valor_venda is None:
        return None
    return round(valor_venda * (1 + iof), 4)


def calcular_spread_ptax(valor_venda: float, ptax_venda: float) -> float | None:
    """Spread percentual da cotacao da casa vs PTAX venda (oficial)."""
    if not valor_venda or not ptax_venda:
        return None
    spread = ((valor_venda / ptax_venda) - 1) * 100
    return round(spread, 2)


def calcular_spread_wise(valor_venda: float, wise_rate: float) -> float | None:
    """Spread percentual da cotacao da casa vs Wise (benchmark digital)."""
    if not valor_venda or not wise_rate:
        return None
    spread = ((valor_venda / wise_rate) - 1) * 100
    return round(spread, 2)


def calcular_variacao(valor_atual: float, valor_anterior: float) -> tuple[float | None, float | None]:
    """Retorna (variacao_RS, variacao_pct) entre dois valores."""
    if not valor_atual or not valor_anterior:
        return (None, None)
    var_rs = round(valor_atual - valor_anterior, 4)
    var_pct = round(((valor_atual / valor_anterior) - 1) * 100, 2)
    return (var_rs, var_pct)


def verificar_discrepancia(valor_venda: float, ptax_venda: float, limite_pct: float = 3.0) -> bool:
    """True se spread vs PTAX > limite (flag para revisao manual)."""
    if not valor_venda or not ptax_venda:
        return False
    spread = abs(((valor_venda / ptax_venda) - 1) * 100)
    return spread > limite_pct


def gerar_ranking(cotacoes: Iterable[dict], volumes: list[int]) -> dict:
    """
    Gera ranking ordenado pelo menor custo efetivo, calculando o custo
    total para cada volume de referencia.
    """
    validas = [
        c for c in cotacoes
        if c.get("custo_efetivo") and c["custo_efetivo"] > 0
    ]
    if not validas:
        return {"top3": [], "completo": [], "por_volume": {}}

    # ordenar pelo menor custo efetivo
    ordenado = sorted(validas, key=lambda x: x["custo_efetivo"])

    top3 = ordenado[:3]
    pior = ordenado[-1]["custo_efetivo"] if ordenado else None

    por_volume = {}
    for vol in volumes:
        items = []
        for c in ordenado:
            custo_total = round(c["custo_efetivo"] * vol, 2)
            economia_vs_pior = round((pior - c["custo_efetivo"]) * vol, 2) if pior else 0
            items.append({
                "casa_slug": c.get("casa_slug") or c.get("slug"),
                "nome": c.get("nome"),
                "custo_efetivo": c["custo_efetivo"],
                "custo_total": custo_total,
                "economia_vs_pior": economia_vs_pior,
            })
        por_volume[str(vol)] = items

    return {
        "top3": [
            {
                "posicao": i + 1,
                "casa_slug": c.get("casa_slug") or c.get("slug"),
                "nome": c.get("nome"),
                "custo_efetivo": c["custo_efetivo"],
                "valor_venda": c.get("valor_venda_especie"),
                "spread_ptax": c.get("spread_ptax"),
            }
            for i, c in enumerate(top3)
        ],
        "completo": [
            {
                "posicao": i + 1,
                "casa_slug": c.get("casa_slug") or c.get("slug"),
                "nome": c.get("nome"),
                "custo_efetivo": c["custo_efetivo"],
            }
            for i, c in enumerate(ordenado)
        ],
        "por_volume": por_volume,
    }
