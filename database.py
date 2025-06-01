import os
import psycopg2
from psycopg2 import sql

# Configuração do banco de dados
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Retorna uma conexão com o banco de dados"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Inicializa o banco de dados com as tabelas necessárias"""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS verified_users (
            username TEXT PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS groups (
            chat_id TEXT PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS source_channel (
            channel_id TEXT PRIMARY KEY
        )
        """
    )
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        for command in commands:
            cur.execute(command)
        
        cur.close()
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

def add_verified_user(username: str, added_by: int):
    """Adiciona um usuário à lista de verificados"""
    sql_query = """
    INSERT INTO verified_users (username, added_by)
    VALUES (%s, %s)
    ON CONFLICT (username) DO NOTHING
    """
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (username.lower(), added_by))
        conn.commit()
        cur.close()
        return True
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()

def remove_verified_user(username: str):
    """Remove um usuário da lista de verificados"""
    sql_query = "DELETE FROM verified_users WHERE username = %s"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (username.lower(),))
        conn.commit()
        cur.close()
        return cur.rowcount > 0
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()

def is_user_verified(username: str) -> bool:
    """Verifica se um usuário está na lista de verificados"""
    if not username:
        return False
    
    sql_query = "SELECT 1 FROM verified_users WHERE username = %s"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (username.lower(),))
        result = cur.fetchone() is not None
        cur.close()
        return result
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()

def get_all_groups():
    """Retorna todos os grupos cadastrados"""
    sql_query = "SELECT chat_id FROM groups"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query)
        groups = [row[0] for row in cur.fetchall()]
        cur.close()
        return groups
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return []
    finally:
        if conn is not None:
            conn.close()

def add_group(chat_id: str, added_by: int):
    """Adiciona um grupo à lista"""
    sql_query = """
    INSERT INTO groups (chat_id, added_by)
    VALUES (%s, %s)
    ON CONFLICT (chat_id) DO NOTHING
    """
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (chat_id, added_by))
        conn.commit()
        cur.close()
        return True
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()

def remove_group(chat_id: str):
    """Remove um grupo da lista"""
    sql_query = "DELETE FROM groups WHERE chat_id = %s"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (chat_id,))
        conn.commit()
        cur.close()
        return cur.rowcount > 0
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()

def get_source_channel():
    """Retorna o ID do canal de origem"""
    sql_query = "SELECT channel_id FROM source_channel LIMIT 1"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query)
        result = cur.fetchone()
        cur.close()
        return result[0] if result else None
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return None
    finally:
        if conn is not None:
            conn.close()

def set_source_channel(channel_id: str):
    """Define o canal de origem"""
    sql_query = """
    INSERT INTO source_channel (channel_id)
    VALUES (%s)
    ON CONFLICT (channel_id) DO UPDATE
    SET channel_id = EXCLUDED.channel_id
    """
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (str(channel_id),))
        conn.commit()
        cur.close()
        return True
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return False
    finally:
        if conn is not None:
            conn.close()