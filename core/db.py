"""
Módulo de banco de dados SQLite para o monitor de câmbio EUR/BRL.
Gerencia tabelas de cotações e casas de câmbio.
"""
import sqlite3
import os
from datetime import datetime, timedelta


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cambio.db")


def get_connection():
    """Retorna conexão com o banco SQLite."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Inicializa tabelas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casas_cambio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            endereco TEXT,
            bairro TEXT,
            tipo TEXT,
            horario TEXT,
            telefone TEXT,
            whatsapp TEXT,
            google_maps TEXT,
            formas_pagamento TEXT,
            agendamento_acima REAL,
            ativo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', '-3 hours')),
            updated_at TEXT DEFAULT (datetime('now', '-3 hours'))
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cotacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            casa_slug TEXT NOT NULL,
            data TEXT NOT NULL,
            hora TEXT NOT NULL,
            valor_venda_especie REAL,
            valor_venda_cartao REAL,
            ptax_venda REAL,
            wise_rate REAL,
            spread_ptax REAL,
            spread_wise REAL,
            iof_especie REAL,
            custo_efetivo REAL,
            variacao_dia_anterior REAL,
            variacao_pct_dia_anterior REAL,
            estoque_disponivel INTEGER DEFAULT 1,
            fonte TEXT,
            observacao TEXT,
            created_at TEXT DEFAULT (datetime('now', '-3 hours')),
            FOREIGN KEY (casa_slug) REFERENCES casas_cambio(slug)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cotacoes_data 
        ON cotacoes(data, casa_slug)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cotacoes_casa_data 
        ON cotacoes(casa_slug, data DESC)
    """)
    
    conn.commit()
    conn.close()


def upsert_casa_cambio(casa_data):
    """Insere ou atualiza dados cadastrais de uma casa de câmbio."""
    conn = get_connection()
    cursor = conn.cursor()
    
    formas = ",".join(casa_data.get("formas_pagamento", []))
    
    cursor.execute("""
        INSERT INTO casas_cambio (slug, nome, endereco, bairro, tipo, horario, 
                                   telefone, whatsapp, google_maps, formas_pagamento, 
                                   agendamento_acima)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            nome = excluded.nome,
            endereco = excluded.endereco,
            bairro = excluded.bairro,
            tipo = excluded.tipo,
            horario = excluded.horario,
            telefone = excluded.telefone,
            whatsapp = excluded.whatsapp,
            google_maps = excluded.google_maps,
            formas_pagamento = excluded.formas_pagamento,
            agendamento_acima = excluded.agendamento_acima,
            updated_at = datetime('now', '-3 hours')
    """, (
        casa_data["slug"], casa_data["nome"], casa_data.get("endereco"),
        casa_data.get("bairro"), casa_data.get("tipo"), casa_data.get("horario"),
        casa_data.get("telefone"), casa_data.get("whatsapp"),
        casa_data.get("google_maps"), formas,
        casa_data.get("agendamento_acima")
    ))
    
    conn.commit()
    conn.close()


def insert_cotacao(cotacao_data):
    """Insere nova cotação no banco."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO cotacoes (casa_slug, data, hora, valor_venda_especie, 
                              valor_venda_cartao, ptax_venda, wise_rate,
                              spread_ptax, spread_wise, iof_especie, custo_efetivo,
                              variacao_dia_anterior, variacao_pct_dia_anterior,
                              estoque_disponivel, fonte, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cotacao_data["casa_slug"], cotacao_data["data"], cotacao_data["hora"],
        cotacao_data.get("valor_venda_especie"), cotacao_data.get("valor_venda_cartao"),
        cotacao_data.get("ptax_venda"), cotacao_data.get("wise_rate"),
        cotacao_data.get("spread_ptax"), cotacao_data.get("spread_wise"),
        cotacao_data.get("iof_especie"), cotacao_data.get("custo_efetivo"),
        cotacao_data.get("variacao_dia_anterior"), cotacao_data.get("variacao_pct_dia_anterior"),
        cotacao_data.get("estoque_disponivel", 1),
        cotacao_data.get("fonte"), cotacao_data.get("observacao")
    ))
    
    conn.commit()
    conn.close()


def get_ultima_cotacao(casa_slug):
    """Retorna a última cotação de uma casa de câmbio."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM cotacoes 
        WHERE casa_slug = ? 
        ORDER BY data DESC, hora DESC 
        LIMIT 1
    """, (casa_slug,))
    
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_cotacoes_dia(data):
    """Retorna todas as cotações de um dia específico."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*, cc.nome, cc.endereco, cc.bairro, cc.horario, 
               cc.telefone, cc.whatsapp, cc.google_maps, cc.formas_pagamento,
               cc.tipo, cc.agendamento_acima
        FROM cotacoes c
        JOIN casas_cambio cc ON c.casa_slug = cc.slug
        WHERE c.data = ?
        ORDER BY c.custo_efetivo ASC
    """, (data,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_historico(dias=90):
    """Retorna histórico de cotações dos últimos N dias."""
    conn = get_connection()
    cursor = conn.cursor()
    
    data_inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT c.data, c.hora, c.casa_slug, cc.nome, c.valor_venda_especie,
               c.custo_efetivo, c.ptax_venda, c.spread_ptax
        FROM cotacoes c
        JOIN casas_cambio cc ON c.casa_slug = cc.slug
        WHERE c.data >= ?
        ORDER BY c.data ASC, c.hora ASC
    """, (data_inicio,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_menor_custo_30_dias():
    """Retorna o menor custo efetivo dos últimos 30 dias."""
    conn = get_connection()
    cursor = conn.cursor()
    
    data_inicio = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT MIN(custo_efetivo) as menor_custo
        FROM cotacoes
        WHERE data >= ? AND custo_efetivo IS NOT NULL AND custo_efetivo > 0
    """, (data_inicio,))
    
    row = cursor.fetchone()
    conn.close()
    return row["menor_custo"] if row else None


def vacuum_db():
    """Executa VACUUM para otimizar o banco."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("VACUUM")
    conn.close()


def limpar_historico_antigo(dias=90):
    """Remove cotações mais antigas que N dias."""
    conn = get_connection()
    data_limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM cotacoes WHERE data < ?", (data_limite,))
    conn.commit()
    conn.close()
