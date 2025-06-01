
import os
import psycopg2
from psycopg2 import sql
import logging

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_connection():
    """Retorna uma conexão com o banco de dados"""
    try:
        return psycopg2.connect(os.getenv("DATABASE_URL"))
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

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
        logger.error(f"Erro ao inicializar banco de dados: {error}")
    finally:
        if conn is not None:
            conn.close()

def add_verified_user(username: str, added_by: int):
    """Adiciona um usuário à lista de verificados"""
    try:
        # Normaliza o username
        username = username.strip().lower()
        if not username.startswith('@'):
            username = f'@{username}'
        
        # Validação básica
        if len(username) < 2 or not username[1:].isalnum():
            return False
        
        sql_query = """
        INSERT INTO verified_users (username, added_by)
        VALUES (%s, %s)
        ON CONFLICT (username) DO UPDATE
        SET added_by = EXCLUDED.added_by
        RETURNING username
        """
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (username, added_by))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            return result is not None
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao adicionar usuário {username}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar username {username}: {e}")
        return False

def remove_verified_user(username: str):
    """Remove um usuário da lista de verificados"""
    try:
        # Normaliza o username
        username = username.strip().lower()
        if not username.startswith('@'):
            username = f'@{username}'
        
        sql_query = "DELETE FROM verified_users WHERE username = %s RETURNING username"
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (username,))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            return result is not None
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao remover usuário {username}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar username {username}: {e}")
        return False

def is_user_verified(username: str) -> bool:
    """Verifica se um usuário está na lista de verificados"""
    if not username:
        return False
    
    try:
        # Normaliza o username
        username = username.strip().lower()
        if not username.startswith('@'):
            username = f'@{username}'
        
        sql_query = "SELECT 1 FROM verified_users WHERE username = %s"
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (username,))
            result = cur.fetchone() is not None
            cur.close()
            return result
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao verificar usuário {username}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar username {username}: {e}")
        return False

def get_verified_users():
    """Retorna todos os usuários verificados"""
    sql_query = "SELECT username FROM verified_users ORDER BY added_at DESC"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query)
        users = [row[0] for row in cur.fetchall()]
        cur.close()
        return users
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Erro ao obter usuários verificados: {error}")
        return []
    finally:
        if conn is not None:
            conn.close()

def get_all_groups():
    """Retorna todos os grupos cadastrados"""
    sql_query = "SELECT chat_id FROM groups ORDER BY added_at DESC"
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query)
        groups = [row[0] for row in cur.fetchall()]
        cur.close()
        return groups
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Erro ao obter grupos: {error}")
        return []
    finally:
        if conn is not None:
            conn.close()

def add_group(chat_id: str, added_by: int):
    """Adiciona um grupo à lista"""
    try:
        # Remove caracteres não numéricos e converte para string
        clean_chat_id = ''.join(c for c in str(chat_id) if c.isdigit())
        
        if not clean_chat_id:
            return False
        
        sql_query = """
        INSERT INTO groups (chat_id, added_by)
        VALUES (%s, %s)
        ON CONFLICT (chat_id) DO NOTHING
        RETURNING chat_id
        """
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (clean_chat_id, added_by))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            return result is not None
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao adicionar grupo {clean_chat_id}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar chat_id {chat_id}: {e}")
        return False

def remove_group(chat_id: str):
    """Remove um grupo da lista"""
    try:
        # Limpa o chat_id para garantir correspondência
        clean_chat_id = ''.join(c for c in str(chat_id) if c.isdigit())
        
        sql_query = "DELETE FROM groups WHERE chat_id = %s RETURNING chat_id"
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (clean_chat_id,))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            return result is not None
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao remover grupo {clean_chat_id}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar chat_id {chat_id}: {e}")
        return False

def is_group_registered(chat_id: str) -> bool:
    """Verifica se um grupo está registrado"""
    try:
        # Limpa o chat_id para garantir correspondência
        clean_chat_id = ''.join(c for c in str(chat_id) if c.isdigit())
        
        sql_query = "SELECT 1 FROM groups WHERE chat_id = %s"
        
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql_query, (clean_chat_id,))
            result = cur.fetchone() is not None
            cur.close()
            return result
        except (Exception, psycopg2.DatabaseError) as error:
            logger.error(f"Erro ao verificar grupo {clean_chat_id}: {error}")
            return False
        finally:
            if conn is not None:
                conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar chat_id {chat_id}: {e}")
        return False

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
        logger.error(f"Erro ao obter canal de origem: {error}")
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
    RETURNING channel_id
    """
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql_query, (str(channel_id),))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        return result is not None
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Erro ao definir canal de origem {channel_id}: {error}")
        return False
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    init_db()