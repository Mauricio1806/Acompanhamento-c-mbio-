"""
Camada de banco SQLite.

Tabelas:
- casas_cambio: cadastro estatico das casas (do config.yaml)
- cotacoes: cada coleta gera 1 linha por casa
"""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "cambio.db",
)


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Cria tabelas se nao existirem."""
    con = _conn()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS casas_cambio (
        slug              TEXT PRIMARY KEY,
        nome              TEXT NOT NULL,
        url               TEXT,
        endereco          TEXT,
        bairro            TEXT,
        tipo              TEXT,
        horario           TEXT,
        telefone          TEXT,
        whatsapp          TEXT,
        google_maps       TEXT,
        formas_pagamento  TEXT,
        agendamento_acima INTEGER,
        ativo             INTEGER DEFAULT 1,
        atualizado_em     TEXT
    );

    CREATE TABLE IF NOT EXISTS cotacoes (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        casa_slug                   TEXT NOT NULL,
        data                        TEXT NOT NULL,
        hora                        TEXT,
        valor_venda_especie         REAL,
        valor_venda_cartao          REAL,
        ptax_venda                  REAL,
        wise_rate                   REAL,
        spread_ptax                 REAL,
        spread_wise                 REAL,
        iof_especie                 REAL,
        custo_efetivo               REAL,
        variacao_dia_anterior       REAL,
        variacao_pct_dia_anterior   REAL,
        estoque_disponivel          INTEGER DEFAULT 1,
        fonte                       TEXT,
        observacao                  TEXT,
        FOREIGN KEY(casa_slug) REFERENCES casas_cambio(slug)
    );

    CREATE INDEX IF NOT EXISTS idx_cot_data       ON cotacoes(data);
    CREATE INDEX IF NOT EXISTS idx_cot_casa_data  ON cotacoes(casa_slug, data);
    """)
    con.commit()
    con.close()


def upsert_casa_cambio(casa: dict[str, Any]):
    """Insere ou atualiza casa de cambio."""
    con = _conn()
    cur = con.cursor()
    formas = casa.get("formas_pagamento")
    if isinstance(formas, list):
        formas = ",".join(formas)
    cur.execute("""
        INSERT INTO casas_cambio (
            slug, nome, url, endereco, bairro, tipo, horario,
            telefone, whatsapp, google_maps, formas_pagamento,
            agendamento_acima, ativo, atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(slug) DO UPDATE SET
            nome              = excluded.nome,
            url               = excluded.url,
            endereco          = excluded.endereco,
            bairro            = excluded.bairro,
            tipo              = excluded.tipo,
            horario           = excluded.horario,
            telefone          = excluded.telefone,
            whatsapp          = excluded.whatsapp,
            google_maps       = excluded.google_maps,
            formas_pagamento  = excluded.formas_pagamento,
            agendamento_acima = excluded.agendamento_acima,
            atualizado_em     = excluded.atualizado_em
    """, (
        casa["slug"],
        casa.get("nome"),
        casa.get("url"),
        casa.get("endereco"),
        casa.get("bairro"),
        casa.get("tipo"),
        casa.get("horario"),
        casa.get("telefone"),
        casa.get("whatsapp"),
        casa.get("google_maps"),
        formas,
        casa.get("agendamento_acima"),
        datetime.now().isoformat(timespec="seconds"),
    ))
    con.commit()
    con.close()


def insert_cotacao(data: dict[str, Any]):
    """Insere uma cotacao nova."""
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO cotacoes (
            casa_slug, data, hora,
            valor_venda_especie, valor_venda_cartao,
            ptax_venda, wise_rate,
            spread_ptax, spread_wise,
            iof_especie, custo_efetivo,
            variacao_dia_anterior, variacao_pct_dia_anterior,
            estoque_disponivel, fonte, observacao
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["casa_slug"],
        data["data"],
        data.get("hora"),
        data.get("valor_venda_especie"),
        data.get("valor_venda_cartao"),
        data.get("ptax_venda"),
        data.get("wise_rate"),
        data.get("spread_ptax"),
        data.get("spread_wise"),
        data.get("iof_especie"),
        data.get("custo_efetivo"),
        data.get("variacao_dia_anterior"),
        data.get("variacao_pct_dia_anterior"),
        data.get("estoque_disponivel", 1),
        data.get("fonte"),
        data.get("observacao"),
    ))
    con.commit()
    con.close()


def get_ultima_cotacao(casa_slug: str) -> dict | None:
    """Ultima cotacao registrada para a casa (qualquer data)."""
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        SELECT * FROM cotacoes
        WHERE casa_slug = ?
        ORDER BY data DESC, hora DESC
        LIMIT 1
    """, (casa_slug,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def get_cotacoes_dia(data: str) -> list[dict]:
    """
    Todas as cotacoes do dia + dados cadastrais da casa.
    Se houver mais de uma coleta no mesmo dia para a mesma casa,
    retorna a mais recente.
    """
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        SELECT c.*, cc.nome, cc.endereco, cc.bairro, cc.tipo, cc.horario,
               cc.telefone, cc.whatsapp, cc.google_maps, cc.formas_pagamento,
               cc.agendamento_acima, cc.url
        FROM cotacoes c
        JOIN casas_cambio cc ON cc.slug = c.casa_slug
        WHERE c.data = ?
          AND c.id IN (
            SELECT MAX(id) FROM cotacoes
            WHERE data = ?
            GROUP BY casa_slug
          )
        ORDER BY c.custo_efetivo ASC
    """, (data, data))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def get_historico(dias: int = 90) -> list[dict]:
    """Historico para a serie temporal."""
    inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        SELECT c.data, c.casa_slug, c.valor_venda_especie, c.custo_efetivo,
               c.spread_ptax, c.ptax_venda, cc.nome
        FROM cotacoes c
        JOIN casas_cambio cc ON cc.slug = c.casa_slug
        WHERE c.data >= ?
        ORDER BY c.data ASC
    """, (inicio,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def get_menor_custo_30_dias() -> float | None:
    """Menor custo efetivo registrado nos ultimos 30 dias (qualquer casa)."""
    inicio = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        SELECT MIN(custo_efetivo) AS minimo
        FROM cotacoes
        WHERE data >= ? AND custo_efetivo > 0
    """, (inicio,))
    row = cur.fetchone()
    con.close()
    return row["minimo"] if row and row["minimo"] else None


def limpar_historico_antigo(dias: int = 90):
    """Remove cotacoes mais antigas que N dias."""
    limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    con = _conn()
    cur = con.cursor()
    cur.execute("DELETE FROM cotacoes WHERE data < ?", (limite,))
    con.commit()
    con.close()


def vacuum_db():
    """Compacta o banco."""
    con = _conn()
    con.execute("VACUUM")
    con.close()
