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
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    ChatMemberHandler,
    CallbackQueryHandler,
    filters
)
from telegram.error import TelegramError
from urllib.parse import urlparse

# Configuração básica
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente necessárias
REQUIRED_ENV_VARS = {
    'TELEGRAM_TOKEN': 'Token do bot Telegram',
    'DATABASE_URL': 'URL de conexão com o PostgreSQL',
    'BOT_ADMINS': 'IDs dos administradores do bot (separados por vírgula)',
    'LOG_LEVEL': 'Nível de log (INFO, DEBUG, etc.) - Opcional'
}

# Verifica variáveis de ambiente
for var, desc in REQUIRED_ENV_VARS.items():
    if var not in os.environ and var != 'LOG_LEVEL':
        raise EnvironmentError(f"Variável de ambiente necessária não encontrada: {var} ({desc})")

# Configura nível de log
if 'LOG_LEVEL' in os.environ:
    logging.basicConfig(level=os.environ['LOG_LEVEL'])

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
    
    conn = None
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
    conn = None
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
    conn = None
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
    conn = None
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
    conn = None
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

# Função auxiliar corrigida para buscar ID por username (agora assíncrona)
async def get_user_id_by_username(bot: Bot, username: str) -> Optional[int]:
    """Obtém o ID do usuário pelo @username."""
    try:
        username = username.lstrip('@')
        user = await bot.get_chat(f"@{username}")
        return user.id
    except TelegramError as e:
        logger.error(f"Erro ao buscar usuário por username: {e}")
        return None

# Comandos do bot
async def start(update: Update, context: CallbackContext) -> None:
    """Mensagem de boas-vindas."""
    if update.effective_chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("Seja uma Verificada", callback_data='be_verified')],
            [InlineKeyboardButton("Sou um Admin", callback_data='i_am_admin')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        welcome_message = (
            "👋 Olá! Eu sou o KSgroupbot, seu assistente para a KS Entretenimento.\n\n"
            "🔹 Seja uma VERIFICADA ou clique em 'Sou um Admin'."
        )
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text("👋 Olá grupo! Eu sou o KSgroupbot.")

async def button_handler(update: Update, context: CallbackContext) -> None:
    """Lida com cliques nos botões inline."""
    query = update.callback_query
    await query.answer()

    if query.data == 'be_verified':
        response = (
            "📌 Para se tornar uma VERIFICADA:\n"
            "1. Grave um vídeo e poste no @KScanal\n"
            "2. Diga: \"Sou [seu nome] e quero ser uma Verificada\"\n"
            "3. Inclua uma prévia do seu conteúdo"
        )
        await query.edit_message_text(text=response)
    elif query.data == 'i_am_admin':
        response = (
            "👑 Comandos de admin:\n"
            "/addverified @username\n"
            "/setgroupadmin @username ID_GRUPO"
        )
        await query.edit_message_text(text=response)

async def set_group_admin(update: Update, context: CallbackContext) -> None:
    """Define um admin de grupo."""
    if not is_bot_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sem permissão.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Uso: /setgroupadmin @username ID_GRUPO")
        return

    try:
        username = context.args[0]
        chat_id = int(context.args[1])
        user_id = await get_user_id_by_username(context.bot, username)
        if not user_id:
            await update.message.reply_text("❌ Usuário não encontrado.")
            return
        
        if add_group_admin(user_id, chat_id):
            await update.message.reply_text(f"✅ @{username} adicionado como admin do grupo {chat_id}.")
        else:
            await update.message.reply_text(f"ℹ️ @{username} já é admin.")
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")

# Função corrigida para adicionar verificados (totalmente assíncrona)
async def add_verified(update: Update, context: CallbackContext) -> None:
    """Adiciona um usuário verificado."""
    if not is_bot_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sem permissão.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("❌ Uso: /addverified @username")
        return

    username = context.args[0]
    if not username.startswith('@'):
        await update.message.reply_text("❌ Use @username.")
        return

    try:
        user_id = await get_user_id_by_username(context.bot, username)
        if not user_id:
            await update.message.reply_text("❌ Usuário não encontrado.")
            return

        user = await context.bot.get_chat(user_id)
        
        if add_verified_user(user_id, user.username, user.full_name):
            await update.message.reply_text(f"✅ {user.full_name} (@{user.username}) verificado!")
        else:
            await update.message.reply_text(f"ℹ️ @{user.username} já está verificado.")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")

async def handle_verification_keywords(update: Update, context: CallbackContext) -> None:
    """Responde a mensagens sobre verificação."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    if any(kw in update.message.text.lower() for kw in ["verificada", "verificado"]):
        await update.message.reply_text(
            "📢 Para ser VERIFICADA:\n"
            "1. Chame @KSgroupbot no PV\n"
            "2. Clique em 'Seja uma Verificada'\n"
            "3. Siga as instruções"
        )

async def handle_new_member(update: Update, context: CallbackContext) -> None:
    """Lida com novos membros."""
    if not update.chat_member or not update.chat_member.new_chat_members:
        return

    chat_id = update.effective_chat.id
    for member in update.chat_member.new_chat_members:
        user_id = member.id
        
        # Verifica se é admin de grupo
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM group_admins WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id)
            )
            is_group_admin = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar admin: {e}")
            is_group_admin = False
        finally:
            if conn is not None:
                conn.close()

        if is_group_admin:
            try:
                await context.bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    can_manage_chat=True,
                    can_delete_messages=True,
                    can_restrict_members=True,
                    can_promote_members=True
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Bem-vindo admin {member.full_name}!"
                )
            except TelegramError as e:
                logger.error(f"Erro ao promover admin: {e}")
        
        # Verifica se é verificado
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM verified_users WHERE user_id = %s AND status = 'approved'",
                (user_id,)
            )
            is_verified = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar verificado: {e}")
            is_verified = False
        finally:
            if conn is not None:
                conn.close()

        if is_verified:
            try:
                await context.bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title="Verificada"
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Bem-vindo {member.full_name} (Verificada)!"
                )
            except TelegramError as e:
                logger.error(f"Erro ao definir verificado: {e}")

async def error_handler(update: Update, context: CallbackContext) -> None:
    """Lida com erros."""
    logger.error(f"Erro: {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text("❌ Ocorreu um erro.")

def main() -> None:
    """Inicia o bot."""
    init_db()
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("Token não configurado")

    # Configura admins
    admin_ids = os.getenv('BOT_ADMINS', '').split(',')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for admin_id in admin_ids:
            if admin_id.strip().isdigit():
                cur.execute(
                    "INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (int(admin_id.strip()),)
        conn.commit()
    except Exception as e:
        logger.error(f"Erro ao configurar admins: {e}")
    finally:
        if conn is not None:
            conn.close()

    application = Application.builder().token(token).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setgroupadmin", set_group_admin))
    application.add_handler(CommandHandler("addverified", add_verified))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_verification_keywords))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_error_handler(error_handler)

    application.run_polling()
    logger.info("Bot iniciado!")

if __name__ == '__main__':
    main()