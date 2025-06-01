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
        """,
        """
        CREATE TABLE IF NOT EXISTS group_admins (
            user_id BIGINT,
            chat_id BIGINT,
            username VARCHAR(255),
            full_name VARCHAR(255),
            PRIMARY KEY (user_id, chat_id))
        """,
        """
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending')
        """,
        """
        CREATE TABLE IF NOT EXISTS verification_requests (
            request_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            video_url VARCHAR(255),
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'pending',
            reviewed_by BIGINT,
            review_date TIMESTAMP)
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

def is_bot_admin(user_id: int) -> bool:
    """Verifica se o usuário é administrador do bot."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM bot_admins WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Erro ao verificar admin do bot: {e}")
        return False

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

def button_handler(update: Update, context: CallbackContext) -> None:
    """Lida com cliques nos botões inline."""
    query = update.callback_query
    query.answer()

    if query.data == 'be_verified':
        response = (
            "📌 Para se tornar uma VERIFICADA, siga estes passos:\n\n"
            "1. Grave um vídeo e poste no canal @KScanal\n"
            "2. No vídeo, diga a frase:\n"
            "\"Sou [seu nome] e eu quero ser uma Verificada na KS Entretenimento\"\n"
            "3. Inclua uma prévia do seu conteúdo\n\n"
            "⏳ Em breve algum administrador avaliará sua solicitação!"
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'about_admins':
        response = (
            "👑 Sobre administradores:\n\n"
            "Se você é administrador de algum grupo da KS Entretenimento, "
            "entre em contato com @KarolzinhaSapeca para configurar "
            "suas permissões de administrador."
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_add_verified':
        context.user_data['action'] = 'add_verified'
        query.edit_message_text(
            text="🔹 Digite o @username da conta que deseja adicionar como Verificada:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'admin_remove_verified':
        context.user_data['action'] = 'remove_verified'
        query.edit_message_text(
            text="🔹 Digite o @username da conta que deseja remover das Verificadas:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'cancel_action':
        if 'action' in context.user_data:
            del context.user_data['action']
        query.edit_message_text("❌ Ação cancelada.")

def handle_text_input(update: Update, context: CallbackContext) -> None:
    """Lida com entradas de texto após seleção de ações."""
    if update.effective_chat.type != "private" or 'action' not in context.user_data:
        return
    
    user_id = update.effective_user.id
    if not is_bot_admin(user_id):
        update.message.reply_text("❌ Você não tem permissão para executar esta ação.")
        return
    
    text = update.message.text.strip()
    action = context.user_data['action']
    
    if action == 'add_verified':
        if not text.startswith('@'):
            update.message.reply_text("❌ Por favor, insira um @username válido (começando com @).")
            return
        
        username = text[1:] if text.startswith('@') else text
        try:
            user = context.bot.get_chat(username)
            if add_verified_user(user.id, user.username or '', user.full_name or ''):
                update.message.reply_text(f"✅ {user.full_name} adicionado como verificado!")
            else:
                update.message.reply_text("⚠️ Usuário já verificado")
        except TelegramError:
            update.message.reply_text("❌ Usuário não encontrado")
        
        del context.user_data['action']

def add_verified_user(user_id: int, username: str, full_name: str) -> bool:
    """Adiciona um usuário verificado."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO verified_users (user_id, username, full_name, status) 
                VALUES (%s, %s, %s, 'approved') 
                ON CONFLICT (user_id) DO UPDATE 
                SET status = 'approved'""",
                (user_id, username, full_name)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário verificado: {e}")
        return False

def handle_new_member(update: Update, context: CallbackContext) -> None:
    """Lida com novos membros no grupo."""
    if not update.chat_member or not update.chat_member.new_chat_members:
        return

    chat_id = update.effective_chat.id
    for member in update.chat_member.new_chat_members:
        user_id = member.id
        
        # Verifica se é um usuário verificado
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM verified_users WHERE user_id = %s AND status = 'approved'",
                    (user_id,)
                )
                is_verified = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar usuário verificado: {e}")
            is_verified = False

        if is_verified:
            try:
                context.bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title="Verificada"
                )
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Bem-vindo {member.full_name}! Esta é uma conta verificada."
                )
            except TelegramError as e:
                logger.error(f"Erro ao promover verificado: {e}")

def error_handler(update: Update, context: CallbackContext) -> None:
    """Lida com erros de forma segura."""
    try:
        error = context.error
        logger.error(f'Erro não tratado: {error}', exc_info=error)
        
        if isinstance(error, Conflict):
            logger.warning("Conflito detectado - outra instância em execução")
            
        if update and hasattr(update, 'effective_message') and update.effective_message:
            update.effective_message.reply_text("❌ Ocorreu um erro ao processar seu comando.")
    except Exception as e:
        logger.error(f'Erro no manipulador de erros: {e}')

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
                bootstrap_retries=-1,  # Corrigido: valor compatível
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
        
        # Configuração do Updater (removido pool_timeout que causava erro)
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30
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