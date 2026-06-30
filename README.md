# 💱 Monitor de Câmbio EUR/BRL — Salvador, BA

Sistema autônomo de monitoramento de cotações do Euro (espécie) em casas de câmbio de Salvador.

📊 **Dashboard:** https://mauricio1806.github.io/Acompanhamento-c-mbio-/

## Como funciona

1. **GitHub Actions roda 2x/dia** (10h e 16h BRT)
2. **PTAX + Wise** coletados como referência (BCB + Wise API)
3. **MelhorCâmbio Salvador** raspado para cotações reais de casas locais
4. **Cotações manuais** (data/manual_quotes.json) processadas se existirem
5. Cálculos: IOF 1,1%, custo efetivo, spread PTAX/Wise, variação dia anterior
6. JSONs estáticos gerados em `docs/data/` e dashboard publicado via GitHub Pages

## Estrutura

```
.
├── .github/workflows/coleta-cambio.yml   # cron 2x/dia
├── scrapers/
│   ├── bcb_ptax.py        # PTAX (BCB) + Wise
│   └── melhorcambio.py    # casas de Salvador (HTML scraping)
├── core/
│   ├── db.py              # SQLite
│   ├── calculator.py      # IOF, spread, ranking, custo efetivo
│   └── builder.py         # gera latest/history/ranking.json
├── docs/                  # dashboard (GitHub Pages, pasta /docs)
│   ├── index.html
│   ├── assets/{style.css, app.js}
│   └── data/{latest,history,ranking}.json
├── data/
│   ├── cambio.db                       # SQLite versionado (histórico)
│   └── manual_quotes.example.json      # template para entrada manual
├── config.yaml            # IOF, casas, volumes de referência
├── main.py                # pipeline principal
└── requirements.txt
```

## Uso local

```bash
pip install -r requirements.txt
python main.py              # pipeline completo (coleta + JSONs)
python main.py --dry-run    # coleta e mostra sem persistir
python main.py --init       # só inicializa banco e cadastra casas
python main.py --build-json # só regenera JSONs do banco existente
python main.py --vacuum     # remove histórico antigo + vacuum
```

## Cotações manuais

Para casas que não aparecem no MelhorCâmbio (ex: Confidence, Get Money, agências bancárias), você pode adicionar cotações manualmente:

```bash
cp data/manual_quotes.example.json data/manual_quotes.json
# edite com as cotações que você consultou (WhatsApp, telefone, presencial)
git add data/manual_quotes.json && git commit -m "feat: cotações manuais hoje" && git push
```

Na próxima execução, essas cotações serão incorporadas ao banco e ao dashboard.

Formato:
```json
[
  {
    "casa_slug": "confidence-shopping-barra",
    "valor_venda_especie": 6.42,
    "valor_venda_cartao": 6.55,
    "fonte": "manual_whatsapp",
    "observacao": "consultado em 29/06"
  }
]
```

`casa_slug` precisa existir em `config.yaml` (ou ser adicionado lá).

## Stack

- Python 3.11 + requests + BeautifulSoup + lxml + pyyaml
- SQLite (versionado no repo, ~90 dias de histórico)
- GitHub Actions (cron 2x/dia)
- GitHub Pages (pasta `/docs`)
- Chart.js (CDN, sem build)

## Notas

- IOF 1,1% aplicado a operação em **espécie** (notas físicas)
- Valor "custo efetivo" = `venda * (1 + IOF)` — é o que você efetivamente paga por EUR
- O MelhorCâmbio agrega cotações de várias casas em Salvador; pode mostrar 1 ou várias dependendo do dia
- Spread vs PTAX > 5% é flagado como alerta (configurável em `config.yaml`)
