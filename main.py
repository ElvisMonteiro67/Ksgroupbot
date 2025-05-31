import os
import logging
import psycopg2
import sys
import time
import signal
from typing import Dict, List, Optional
from telegram import (
    Update,
    Bot,
    ChatMember,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ChatMemberHandler,
    CallbackQueryHandler,
)
from telegram.error import TelegramError, Conflict, BadRequest
from urllib.parse import urlparse
from contextlib import contextmanager

# Configuração básica
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações aprimoradas para o Render
MAX_RETRIES = 5
RETRY_DELAY = 10
WEBHOOK_MODE = os.getenv('WEBHOOK_MODE', 'false').lower() == 'true'

# ==============================================
# FUNÇÕES DE BANCO DE DADOS
# ==============================================

@contextmanager
def db_connection():
    """Gerenciador de contexto para conexões com o banco de dados."""
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    except Exception as e:
        logger.error(f"Erro de banco de dados: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def get_db_connection():
    """Estabelece conexão com o banco de dados PostgreSQL."""
    try:
        result = urlparse(os.getenv('DATABASE_URL'))
        conn = psycopg2.connect(
            dbname=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

def init_db():
    """Inicializa o banco de dados criando as tabelas necessárias."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS bot_admins (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_admins (
            user_id BIGINT,
            chat_id BIGINT,
            username VARCHAR(255),
            full_name VARCHAR(255),
            PRIMARY KEY (user_id, chat_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS verification_requests (
            request_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            video_url VARCHAR(255),
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'pending',
            reviewed_by BIGINT,
            review_date TIMESTAMP
        )
        """
    )
    
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            for command in commands:
                cur.execute(command)
            conn.commit()
        logger.info("Banco de dados inicializado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
        raise

def setup_admin_users():
    """Configura os administradores iniciais do bot."""
    admin_ids = os.getenv('BOT_ADMINS', '').split(',')
    if not admin_ids:
        return

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            for admin_id in admin_ids:
                if admin_id.strip().isdigit():
                    admin_id_int = int(admin_id.strip())
                    try:
                        bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
                        try:
                            user = bot.get_chat(admin_id_int)
                            username = user.username or ''
                            full_name = user.full_name or ''
                            
                            cur.execute(
                                """INSERT INTO bot_admins (user_id, username, full_name) 
                                VALUES (%s, %s, %s) ON CONFLICT (user_id) 
                                DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name""",
                                (admin_id_int, username, full_name)
                            )
                        except (TelegramError, BadRequest) as e:
                            logger.error(f"Erro ao obter info do admin {admin_id}: {e}")
                            cur.execute(
                                "INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                                (admin_id_int,)
                            )
                    except Exception as e:
                        logger.error(f"Erro ao configurar admin {admin_id}: {e}")
            conn.commit()
    except Exception as e:
        logger.error(f"Erro ao configurar admins do bot: {e}")

# ==============================================
# FUNÇÕES PRINCIPAIS DO BOT
# ==============================================

def start(update: Update, context: CallbackContext) -> None:
    """Handler para o comando /start."""
    if update.effective_chat.type == "private":
        if is_bot_admin(update.effective_user.id):
            keyboard = [
                [InlineKeyboardButton("➕ Adicionar Verificada", callback_data='admin_add_verified')],
                [InlineKeyboardButton("➖ Remover Verificada", callback_data='admin_remove_verified')],
                [InlineKeyboardButton("👑 Adicionar Admin Grupo", callback_data='admin_add_group_admin')],
                [InlineKeyboardButton("👑 Remover Admin Grupo", callback_data='admin_remove_group_admin')],
                [InlineKeyboardButton("📋 Listar Verificadas", callback_data='admin_list_verified')],
                [InlineKeyboardButton("📋 Listar Admins Grupo", callback_data='admin_list_group_admins')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text("👑 Menu Admin:", reply_markup=reply_markup)
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Seja uma Verificada", callback_data='be_verified')],
                [InlineKeyboardButton("👑 Sobre Admins", callback_data='about_admins')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text("👋 Bem-vindo ao bot!", reply_markup=reply_markup)
    else:
        update.message.reply_text("🤖 Bot ativo! Digite /start no privado para opções.")

# ... (Adicione aqui TODAS as outras funções do seu bot originais)
# Incluindo: is_bot_admin, add_group_admin, add_verified_user, 
# remove_verified_user, remove_group_admin, get_user_by_username,
# button_handler, handle_text_input, handle_verification_keywords,
# handle_new_member, error_handler

# ==============================================
# SOLUÇÕES PARA O RENDER
# ==============================================

def ensure_single_instance(bot_token: str) -> bool:
    """Verifica se não há outra instância do bot em execução."""
    try:
        test_bot = Bot(token=bot_token)
        try:
            test_bot.get_me()  # Testa a conexão
            try:
                test_bot.get_updates(timeout=5)  # Verifica conflitos
                return True
            except Conflict:
                logger.warning("Conflito detectado - outra instância em execução")
                return False
        except Exception as e:
            logger.error(f"Erro ao verificar instância: {e}")
            return True
    except Exception as e:
        logger.error(f"Erro ao criar bot teste: {e}")
        return True

def start_webhook(updater: Updater):
    """Inicia o bot no modo webhook recomendado para o Render."""
    PORT = int(os.getenv('PORT', 10000))
    WEBHOOK_URL = f"{os.getenv('WEBHOOK_URL')}/{os.getenv('TELEGRAM_TOKEN')}"
    
    try:
        updater.bot.delete_webhook()
        time.sleep(1)
        updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=os.getenv('TELEGRAM_TOKEN'),
            webhook_url=WEBHOOK_URL,
            clean=True,
            drop_pending_updates=True
        )
        logger.info(f"Webhook ativo na porta {PORT}")
    except Exception as e:
        logger.error(f"Falha ao iniciar webhook: {e}")
        raise

def start_polling_safely(updater: Updater):
    """Inicia o bot no modo polling com tratamento de conflitos."""
    for attempt in range(MAX_RETRIES):
        try:
            if not ensure_single_instance(updater.bot.token):
                logger.warning(f"Tentativa {attempt + 1}/{MAX_RETRIES} - Instância duplicada detectada")
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError("Máximo de tentativas atingido com conflitos")
                time.sleep(RETRY_DELAY)
                continue
                
            updater.start_polling(
                drop_pending_updates=True,
                timeout=30,
                allowed_updates=['message', 'callback_query', 'chat_member'],
                bootstrap_retries=0,
                clean=True
            )
            logger.info("Bot iniciado via polling")
            return
            
        except Conflict as e:
            logger.warning(f"Conflito na tentativa {attempt + 1}/{MAX_RETRIES}: {e}")
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError("Máximo de tentativas atingido com conflitos")
            time.sleep(RETRY_DELAY)
            
        except Exception as e:
            logger.error(f"Erro inesperado: {e}")
            raise

def start_bot(updater: Updater):
    """Seleciona o método de inicialização baseado na configuração."""
    if WEBHOOK_MODE:
        logger.info("Iniciando no modo webhook...")
        start_webhook(updater)
    else:
        logger.info("Iniciando no modo polling...")
        start_polling_safely(updater)
    
    updater.idle()

def main() -> None:
    """Função principal com inicialização segura."""
    try:
        # Verificação inicial
        token = os.getenv('TELEGRAM_TOKEN')
        if not token:
            raise ValueError("Token do Telegram não configurado!")
        
        # Inicializações
        init_db()
        setup_admin_users()
        
        # Configuração do Updater
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30,
                'pool_timeout': 30
            }
        )
        
        # Registra handlers
        dispatcher = updater.dispatcher
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CallbackQueryHandler(button_handler))
        dispatcher.add_handler(MessageHandler(Filters.text & Filters.chat_type.private, handle_text_input))
        dispatcher.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
        dispatcher.add_error_handler(error_handler)
        
        # Inicia o bot
        start_bot(updater)
        
    except Exception as e:
        logger.critical(f"Falha na inicialização: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()