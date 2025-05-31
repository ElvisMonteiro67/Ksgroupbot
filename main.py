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
MAX_RETRIES = 5  # Aumentado para mais tentativas
RETRY_DELAY = 10  # Aumentado o tempo entre tentativas
WEBHOOK_MODE = os.getenv('WEBHOOK_MODE', 'false').lower() == 'true'  # Modo webhook opcional

# ==============================================
# FUNÇÕES ORIGINAIS DO BOT (MANTIDAS)
# ==============================================

@contextmanager
def db_connection():
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
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port

        conn = psycopg2.connect(
            dbname=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

# ... (Todas as outras funções originais permanecem EXATAMENTE IGUAIS)
# Incluindo: init_db, is_bot_admin, add_bot_admin, add_group_admin, 
# add_verified_user, remove_verified_user, remove_group_admin,
# get_user_by_username, start, button_handler, handle_text_input,
# handle_verification_keywords, handle_new_member, error_handler

# ==============================================
# SOLUÇÕES PARA O RENDER (ADICIONADAS)
# ==============================================

def ensure_single_instance(bot_token: str) -> bool:
    """Verifica se não há outra instância do bot em execução com tratamento aprimorado."""
    try:
        test_bot = Bot(token=bot_token)
        try:
            # Testa a conexão e verifica se há conflito
            test_bot.get_me()
            try:
                updates = test_bot.get_updates(timeout=5)
                if updates:
                    logger.warning("Outra instância detectada via updates. Encerrando...")
                    return False
            except Conflict:
                logger.warning("Conflito detectado diretamente. Encerrando...")
                return False
            return True
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
        # Limpa webhooks anteriores
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
        logger.info(f"Bot iniciado via webhook na porta {PORT}")
    except Exception as e:
        logger.error(f"Falha ao iniciar webhook: {e}")
        raise

def start_polling_safely(updater: Updater):
    """Inicia o bot no modo polling com tratamento de conflitos."""
    for attempt in range(MAX_RETRIES):
        try:
            if not ensure_single_instance(updater.bot.token):
                if attempt == MAX_RETRIES - 1:
                    logger.critical("Falha após várias tentativas. Encerrando.")
                    sys.exit(1)
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
                logger.critical("Máximo de tentativas atingido. Encerrando.")
                sys.exit(1)
            time.sleep(RETRY_DELAY)
            
        except Exception as e:
            logger.critical(f"Erro inesperado: {e}")
            sys.exit(1)

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
    # Verificação inicial
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.critical("Token do Telegram não configurado!")
        sys.exit(1)
    
    try:
        # Inicializações
        init_db()
        setup_admin_users()  # Mantenha sua função original de setup
        
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
        
        # Registra handlers (mantenha seus handlers originais)
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