import os
import logging
import psycopg2
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
from telegram.error import TelegramError
from urllib.parse import urlparse

# Configuração básica
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conexão com o banco de dados
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

# Inicialização do banco de dados
def init_db():
    """Cria as tabelas necessárias no banco de dados."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS bot_admins (
            user_id BIGINT PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_admins (
            user_id BIGINT,
            chat_id BIGINT,
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
        conn = get_db_connection()
        cur = conn.cursor()
        for command in commands:
            cur.execute(command)
        cur.close()
        conn.commit()
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
    finally:
        if conn is not None:
            conn.close()

# Funções auxiliares de banco de dados
def is_bot_admin(user_id: int) -> bool:
    """Verifica se o usuário é administrador do bot."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM bot_admins WHERE user_id = %s", (user_id,))
        return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Erro ao verificar admin do bot: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()

def add_group_admin(user_id: int, chat_id: int) -> bool:
    """Adiciona um administrador de grupo."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO group_admins (user_id, chat_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, chat_id)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao adicionar admin de grupo: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()

def add_verified_user(user_id: int, username: str, full_name: str) -> bool:
    """Adiciona um usuário verificado."""
    try:
        conn = get_db_connection()
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
    finally:
        if conn is not None:
            conn.close()

def create_verification_request(user_id: int, video_url: str) -> bool:
    """Cria uma solicitação de verificação."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO verification_requests (user_id, video_url) 
            VALUES (%s, %s)""",
            (user_id, video_url)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao criar solicitação de verificação: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()

# Nova função auxiliar para buscar ID por username
def get_user_id_by_username(bot: Bot, username: str) -> Optional[int]:
    """Obtém o ID do usuário pelo @username."""
    try:
        # Remove o '@' se presente
        username = username.lstrip('@')
        user = bot.get_chat(f"@{username}")
        return user.id
    except TelegramError as e:
        logger.error(f"Erro ao buscar usuário por username: {e}")
        return None

# Comandos do bot
def start(update: Update, context: CallbackContext) -> None:
    """Envia mensagem de boas-vindas quando o comando /start é acionado."""
    if update.effective_chat.type == "private":
        # Mensagem privada com botões
        keyboard = [
            [InlineKeyboardButton("Seja uma Verificada", callback_data='be_verified')],
            [InlineKeyboardButton("Sou um Admin", callback_data='i_am_admin')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_message = (
            "👋 Olá! Eu sou o KSgroupbot, seu assistente para a KS Entretenimento.\n\n"
            "🔹 Se você deseja se tornar uma conta VERIFICADA, clique no botão abaixo.\n"
            "🔹 Se você é um ADMINISTRADOR, clique no botão correspondente."
        )
        update.message.reply_text(welcome_message, reply_markup=reply_markup)
    else:
        # Mensagem em grupo
        welcome_message = (
            "👋 Olá grupo! Eu sou o KSgroupbot.\n\n"
            "📌 Se você mencionar 'verificada' ou variações, eu posso te explicar "
            "como se tornar uma conta verificada pela Agência KS!"
        )
        update.message.reply_text(welcome_message)

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
    elif query.data == 'i_am_admin':
        response = (
            "👑 Você é um administrador?\n\n"
            "Comandos disponíveis:\n"
            "/addverified @username - Adiciona um usuário como verificado\n"
            "/setgroupadmin @username ID_GRUPO - Define um admin de grupo\n\n"
            "Obs: Você precisa ser admin do bot para usar esses comandos."
        )
        query.edit_message_text(text=response)

def set_group_admin(update: Update, context: CallbackContext) -> None:
    """Define um usuário como administrador de grupo."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    if len(context.args) < 2:
        update.message.reply_text("❌ Uso: /setgroupadmin @username ID_GRUPO")
        return

    try:
        username = context.args[0]
        chat_id = int(context.args[1])
        
        user_id = get_user_id_by_username(context.bot, username)
        if not user_id:
            update.message.reply_text("❌ Não foi possível encontrar o usuário. Verifique se o @username está correto.")
            return
        
        if add_group_admin(user_id, chat_id):
            update.message.reply_text(
                f"✅ Usuário @{username} adicionado como administrador do grupo {chat_id}.\n"
                f"Ele receberá permissões de admin quando entrar no grupo."
            )
        else:
            update.message.reply_text(f"ℹ️ O usuário @{username} já é administrador do grupo {chat_id}.")
    except ValueError:
        update.message.reply_text("❌ ID do grupo inválido. Forneça um número válido.")

def add_verified(update: Update, context: CallbackContext) -> None:
    """Adiciona um usuário à lista de verificados usando @username."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    if len(context.args) < 1:
        update.message.reply_text("❌ Uso: /addverified @username")
        return

    username = context.args[0]
    if not username.startswith('@'):
        update.message.reply_text("❌ Por favor, forneça um @username válido (começando com @).")
        return

    try:
        user_id = get_user_id_by_username(context.bot, username)
        if not user_id:
            update.message.reply_text("❌ Não foi possível encontrar o usuário. Verifique se o @username está correto.")
            return

        # Obter informações do usuário
        user = context.bot.get_chat(user_id)
        
        if add_verified_user(user_id, user.username, user.full_name):
            update.message.reply_text(
                f"✅ Usuário {user.full_name} (@{user.username}) adicionado como verificado.\n"
                f"Ele receberá o status 'Verificada' quando entrar em qualquer grupo."
            )
        else:
            update.message.reply_text(f"ℹ️ Usuário @{user.username} já está na lista de verificados.")
    except TelegramError as e:
        update.message.reply_text(f"❌ Erro: {str(e)}")

def handle_verification_keywords(update: Update, context: CallbackContext) -> None:
    """Responde a mensagens contendo palavras-chave sobre verificação."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    message_text = update.message.text.lower()
    keywords = ["verificada", "verificado", "verificar", "verificação"]
    
    if any(keyword in message_text for keyword in keywords):
        response = (
            "📢 Informação sobre contas VERIFICADAS:\n\n"
            "Para se tornar uma conta verificada pela Agência KS:\n"
            "1. Chame o @KSgroupbot no privado\n"
            "2. Clique em 'Seja uma Verificada'\n"
            "3. Siga as instruções para enviar seu vídeo\n\n"
            "✅ Contas verificadas recebem um selo especial no grupo!"
        )
        update.message.reply_text(response)

def handle_new_member(update: Update, context: CallbackContext) -> None:
    """Lida com novos membros no grupo."""
    if not update.chat_member or not update.chat_member.new_chat_members:
        return

    chat_id = update.effective_chat.id
    for member in update.chat_member.new_chat_members:
        user_id = member.id
        
        # Verifica se é um administrador de grupo
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM group_admins WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id)
            )
            is_group_admin = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar admin de grupo: {e}")
            is_group_admin = False
        finally:
            if conn is not None:
                conn.close()

        if is_group_admin:
            try:
                context.bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    can_change_info=True,
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_restrict_members=True,
                    can_pin_messages=True,
                    can_promote_members=True,
                    can_manage_chat=True,
                    can_manage_video_chats=True,
                    can_manage_topics=True
                )
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Bem-vindo administrador {member.full_name}! Permissões concedidas."
                )
            except TelegramError as e:
                logger.error(f"Erro ao promover admin: {e}")
        
        # Verifica se é um usuário verificado
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM verified_users WHERE user_id = %s AND status = 'approved'",
                (user_id,)
            )
            is_verified = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar usuário verificado: {e}")
            is_verified = False
        finally:
            if conn is not None:
                conn.close()

        if is_verified:
            try:
                context.bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    can_change_info=False,
                    can_post_messages=False,
                    can_edit_messages=False,
                    can_delete_messages=False,
                    can_invite_users=False,
                    can_restrict_members=False,
                    can_pin_messages=False,
                    can_promote_members=False,
                    can_manage_chat=False,
                    can_manage_video_chats=False,
                    can_manage_topics=False,
                    is_anonymous=False
                )
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
    """Lida com erros."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        update.effective_message.reply_text("❌ Ocorreu um erro ao processar seu comando.")

def main() -> None:
    """Inicia o bot."""
    # Inicializa o banco de dados
    init_db()
    
    # Configuração do bot
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("Por favor, defina a variável de ambiente TELEGRAM_TOKEN")
    
    # Configura administradores do bot
    admin_ids = os.getenv('BOT_ADMINS', '').split(',')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for admin_id in admin_ids:
            if admin_id.strip().isdigit():
                cur.execute(
                    "INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (int(admin_id.strip()),)
                )
        conn.commit()
    except Exception as e:
        logger.error(f"Erro ao configurar admins do bot: {e}")
    finally:
        if conn is not None:
            conn.close()

    updater = Updater(token)
    dispatcher = updater.dispatcher

    # Handlers de comandos
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("setgroupadmin", set_group_admin))
    dispatcher.add_handler(CommandHandler("addverified", add_verified))
    
    # Handlers de mensagens
    dispatcher.add_handler(MessageHandler(
        Filters.text & (~Filters.command), 
        handle_verification_keywords
    ))
    
    # Handler para botões
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    
    # Handler para novos membros
    dispatcher.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
    
    # Handler de erros
    dispatcher.add_error_handler(error_handler)

    # Inicia o bot
    updater.start_polling()
    logger.info("Bot iniciado e aguardando mensagens...")
    updater.idle()

if __name__ == '__main__':
    main()