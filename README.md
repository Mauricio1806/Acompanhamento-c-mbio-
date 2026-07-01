# 💱 Monitor de Câmbio EUR/BRL — Salvador, BA

Sistema autônomo de monitoramento de cotações do Euro (espécie) em **25 casas de câmbio de Salvador**.

📊 **Dashboard:** https://mauricio1806.github.io/Acompanhamento-c-mbio-/

## Cobertura

- **1 casa** com coleta automática via MelhorCâmbio (Salvador Câmbio - Itaigara)
- **24 casas** com botões diretos de **WhatsApp / Telefone / Site / Google Maps** pra consulta manual rápida (30 segundos por casa)
- **2 referências** automáticas: PTAX (BCB) e Wise

### Casas catalogadas

**Travelex Confidence (5):** Salvador Shopping, Shopping Barra, Shopping da Bahia, Paralela, Aeroporto SSA  
**DayCâmbio:** Shopping da Bahia + Salvador Câmbio Itaigara (auto)  
**Lúmina Corretora:** Shopping Barra, Salvador Shopping  
**Conecta Câmbio:** Salvador Shopping, Salvador Trade Center  
**Western Union:** Salvador Norte Shopping, Shopping Lapa, Premier (Iguatemi), Itaigara Câmbio  
**Outras:** Labor Câmbio, Bahia Câmbio, Voamais (Barra), Gradual (Aeroporto SSA)  
**Bancos:** BB, Itaú, Bradesco (turismo para correntistas)  
**Online:** Get Money, Frente Corretora, Ourominas

## Como funciona

1. **GitHub Actions roda 2x/dia** (10h e 16h BRT)
2. **PTAX + Wise** coletados como referência
3. **MelhorCâmbio Salvador** raspado automaticamente
4. **Cotações manuais** (data/manual_quotes.json) processadas se você adicionar
5. Cálculos: IOF 1,1%, custo efetivo, spread PTAX/Wise, variação dia anterior
6. JSONs estáticos em `docs/data/` + dashboard publicado via GitHub Pages

## Estrutura

```
.
├── .github/workflows/coleta-cambio.yml   # cron 2x/dia
├── scrapers/
│   ├── bcb_ptax.py        # PTAX (BCB) + Wise
│   └── melhorcambio.py    # MelhorCâmbio Salvador
├── core/
│   ├── db.py              # SQLite
│   ├── calculator.py      # IOF, spread, ranking
│   └── builder.py         # gera latest/history/ranking.json
├── docs/                  # dashboard GitHub Pages
│   ├── index.html
│   ├── assets/
│   └── data/
├── data/
│   ├── cambio.db
│   └── manual_quotes.example.json
├── config.yaml            # 25 casas catalogadas
├── main.py
└── requirements.txt
```

## Como adicionar cotação manual

Você consulta a casa (WhatsApp/telefone/site - botões no dashboard) e adiciona ao arquivo:

```bash
# 1. Copia o template
cp data/manual_quotes.example.json data/manual_quotes.json

# 2. Edita com as cotações consultadas hoje
# (use os slugs do config.yaml: confidence-shopping-barra, daycambio-shopping-bahia, etc)
```

Formato:
```json
[
  {
    "casa_slug": "confidence-shopping-barra",
    "valor_venda_especie": 6.42,
    "valor_venda_cartao": 6.55,
    "fonte": "manual_whatsapp",
    "observacao": "consultado 29/06 via WhatsApp"
  }
]
```

```bash
# 3. Commit e push
git add data/manual_quotes.json
git commit -m "feat: cotacoes manuais $(date +%Y-%m-%d)"
git push
```

Na próxima execução (ou rodando manualmente via Actions → Run workflow), essas cotações entram no banco e dashboard.

## Uso local

```bash
pip install -r requirements.txt
python main.py              # pipeline completo
python main.py --dry-run    # sem persistir
python main.py --init       # só inicializa banco
python main.py --build-json # só regenera JSONs
python main.py --vacuum     # limpa histórico antigo
```

## Stack

Python 3.11 • requests • BeautifulSoup • SQLite • GitHub Actions • GitHub Pages • Chart.js

## Notas

- IOF 1,1% incluso no custo efetivo (operação em espécie)
- Casas sem cotação hoje aparecem no dashboard com botão de consulta direta (WhatsApp/telefone/site)
- Histórico de 90 dias mantido automaticamente
- Spread > 5% vs PTAX flagado como alerta
