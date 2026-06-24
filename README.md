# 💱 Monitor de Câmbio EUR/BRL — Salvador, BA

Sistema autônomo de monitoramento de cotações do Euro (espécie) em casas de câmbio físicas de Salvador, Bahia.

## 📊 Dashboard

Acesse o dashboard interativo em: **[GitHub Pages](https://mauricio1806.github.io/Acompanhamento-c-mbio-/)**

## 🎯 Objetivo

Monitorar o valor de venda do EURO (compra pelo cliente) em todas as principais casas de câmbio físicas de Salvador, gerando um quadro comparativo atualizado automaticamente duas vezes ao dia (10h e 16h, horário de Brasília).

## 🏪 Casas Monitoradas

- **Confidence Câmbio** — Salvador Shopping, Shopping Barra, Shopping da Bahia, Aeroporto SSA
- **Cotação Câmbio e Turismo**
- **Get Money Câmbio**
- **Frente Corretora de Câmbio**
- **Daycoval Câmbio**
- **Ourominas (OM DTVM)**
- **Treviso Câmbio**
- **Bancos** — Banco do Brasil, Itaú, Bradesco (agências centrais)

### Referências
- **PTAX** — Taxa oficial do Banco Central do Brasil
- **Wise** — Benchmark digital

## 💰 Funcionalidades

**Quadro Comparativo** com: valor de venda EUR (espécie), spread vs PTAX, spread vs Wise, IOF 1,1%, custo efetivo final, variação vs dia anterior.

**Ranking Top 3** com diferenças em R$ para volumes de EUR 5.000, EUR 10.000 e EUR 20.000.

**Dashboard Interativo**: tabela com ordenação, filtros por bairro/tipo, gráfico histórico (30/60/90 dias), input de volume customizável, alerta de threshold.

## 📁 Estrutura

```
├── scrapers/         # Scripts de coleta de dados
├── core/             # Banco de dados, cálculos, gerador de JSONs
├── data/             # Banco SQLite com histórico
├── docs/             # Dashboard HTML (GitHub Pages)
│   ├── index.html
│   ├── assets/       # CSS e JavaScript
│   └── data/         # JSONs estáticos (latest, history, ranking)
├── config.yaml       # Configuração geral
├── main.py           # Script principal
└── requirements.txt  # Dependências Python
```

## ⚙️ Como Funciona

1. **Coleta**: O agente busca cotações EUR de cada casa via web scraping e APIs
2. **Referências**: PTAX (Banco Central) e Wise são coletados como benchmark
3. **Cálculos**: Spread, IOF (1,1%), custo efetivo, variação dia anterior
4. **Banco de dados**: Cotações salvas em SQLite com histórico de 90 dias
5. **JSONs**: Geração de `latest.json`, `history.json`, `ranking.json`
6. **Commit**: Push automático para GitHub → GitHub Pages atualiza o dashboard

## 🔄 Atualização Automática

Execução via Scheduled Task: **10h e 16h (Brasília)**

---

*Dados coletados automaticamente. IOF 1,1% incluso no custo efetivo. Valores para operação em espécie (notas físicas).*
