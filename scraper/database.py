"""Persistência em SQLite: progresso e projetos relevantes coletados."""

import sqlite3

from scraper.config import COLUNAS_EXCEL


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projetos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo        TEXT,
            titulo        TEXT,
            coordenador   TEXT,
            centro        TEXT,
            unidade       TEXT,
            area_tematica TEXT,
            scraped_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    # Garante compatibilidade com banco existente sem a coluna codigo
    try:
        conn.execute("ALTER TABLE projetos ADD COLUMN codigo TEXT")
        conn.commit()
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS centros_concluidos (
            centro TEXT PRIMARY KEY
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projetos_visitados (
            chave TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    return conn


def salvar_projeto(conn: sqlite3.Connection, dados: dict):
    conn.execute("""
        INSERT INTO projetos (codigo, titulo, coordenador, centro, unidade, area_tematica)
        VALUES (:codigo, :titulo, :coordenador, :centro, :unidade, :area_tematica)
    """, dados)
    conn.commit()


def marcar_centro_concluido(conn: sqlite3.Connection, centro: str):
    conn.execute("INSERT OR IGNORE INTO centros_concluidos (centro) VALUES (?)", (centro,))
    conn.commit()


def centros_ja_concluidos(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT centro FROM centros_concluidos").fetchall()}


def marcar_visitado(conn: sqlite3.Connection, chave: str):
    conn.execute("INSERT OR IGNORE INTO projetos_visitados (chave) VALUES (?)", (chave,))
    conn.commit()


def ja_visitados(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT chave FROM projetos_visitados").fetchall()}


def carregar_projetos_db(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    rows = conn.execute(
        "SELECT codigo, titulo, coordenador, centro, unidade, area_tematica FROM projetos ORDER BY centro"
    ).fetchall()
    resultado: dict[str, list[dict]] = {}
    for row in rows:
        d = dict(zip(COLUNAS_EXCEL, row))
        resultado.setdefault(d["centro"], []).append(d)
    return resultado
