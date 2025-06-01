import os
import logging
import asyncio
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ConversationHandler,
    filters,
    ContextTypes
)
from sqlalchemy import create_engine, Column, Integer, String, or_
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from threading import Lock

# ==================================================
# CONFIGURAÇÃO INICIAL
# ==================================================

# Configuração de logging detalhada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_ADMIN_ID = int(os.getenv("BOT_ADMIN_ID", "0"))

# Configuração do SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300
)

# Sessão thread-safe
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

# Lock para operações de banco de dados
db_lock = Lock()

# Base declarativa
Base = declarative_base()

class UserRole(Base):
    __tablename__ = 'user_roles'
    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=False)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" ou "verified"

# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def init_db():
    """Inicializa o banco de dados"""
    try:
        with db_lock:
            Base.metadata.create_all(engine)
            logger.info("Banco de dados inicializado com sucesso.")
    except Exception as e:
        logger.error(f"Falha ao inicializar banco de dados: {e}")
        raise

# ==================================================
# COMANDOS PÚBLICOS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas"""
    help_text = """
    🤖 *Bot de Gerenciamento de Grupos* 🤖

    *Comandos disponíveis:*
    /addgroupadmin @username - Adiciona admin
    /addverified @username - Adiciona verificada
    /manage - Menu interativo (privado)
    /help - Ajuda detalhada
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe ajuda detalhada"""
    help_text = """
    📚 *Ajuda do Bot* 📚

    *Comandos:*
    - /addgroupadmin @username - Adiciona administrador
    - /addverified @username - Adiciona verificada
    - /manage - Menu interativo (apenas admin)
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================================================
# GERENCIAMENTO DE USUÁRIOS
# ==================================================

async def add_user_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    """Adiciona usuário à lista"""
    if update.effective_user.id != BOT_ADMIN_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return

    try:
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = (target_user.username or target_user.first_name or "").lower()
        elif context.args:
            username = context.args[0].lstrip('@').lower()
            user_id = 0
        else:
            await update.message.reply_text("ℹ️ Use respondendo ou com @username.")
            return

        with db_lock:
            session = Session()
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            if existing:
                await update.message.reply_text("ℹ️ Já está na lista.")
                return

            new_entry = UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()

        role_name = "administrador" if role == "admin" else "verificada"
        await update.message.reply_text(f"✅ @{username} adicionado(a) como {role_name}!")

    except Exception as e:
        logger.error(f"Erro em add_user_to_list: {e}")
        await update.message.reply_text("❌ Erro ao processar.")
    finally:
        Session.remove()

async def add_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona administrador"""
    await add_user_to_list(update, context, "admin")

async def add_verified(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona verificada"""
    await add_user_to_list(update, context, "verified")

# ==================================================
# GERENCIAMENTO DE NOVOS MEMBROS
# ==================================================

async def new_member_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica novos membros"""
    if not update.message or not update.message.new_chat_members:
        return

    try:
        for new_member in update.message.new_chat_members:
            user_id = new_member.id
            username = (new_member.username or new_member.first_name or "").lower()

            with db_lock:
                session = Session()
                is_admin = session.query(UserRole).filter(
                    UserRole.role == "admin",
                    or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
                ).first()

                is_verified = session.query(UserRole).filter(
                    UserRole.role == "verified",
                    or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
                ).first()
                Session.remove()

            if is_admin:
                await promote_to_admin(context, update.effective_chat.id, user_id, username)
            elif is_verified:
                await verify_user(context, update.effective_chat.id, user_id, username)

    except Exception as e:
        logger.error(f"Erro em new_member_check: {e}")

async def promote_to_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, username: str):
    """Promove a administrador"""
    try:
        await context.bot.promote_chat_member(
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
            is_anonymous=False
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👑 Bem-vindo admin @{username}!"
        )
    except Exception as e:
        logger.error(f"Erro ao promover admin: {e}")

async def verify_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, username: str):
    """Define como verificado"""
    try:
        await context.bot.promote_chat_member(
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
            is_anonymous=True
        )
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title="Verificada"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🌸 Bem-vinda @{username}!"
        )
    except Exception as e:
        logger.error(f"Erro ao verificar usuário: {e}")

# ==================================================
# INTERFACE INTERATIVA
# ==================================================

CHOOSING_ACTION, WAITING_FOR_USERNAME = range(2)

async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia menu interativo"""
    if update.effective_user.id != BOT_ADMIN_ID:
        await update.message.reply_text("❌ Acesso restrito.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Administrador", callback_data='add_admin')],
        [InlineKeyboardButton("➕ Adicionar Verificada", callback_data='add_verified')],
        [InlineKeyboardButton("❌ Cancelar", callback_data='cancel')]
    ]
    
    await update.message.reply_text(
        "🔧 Menu de Gerenciamento:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

async def action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa seleção do menu"""
    query = update.callback_query
    await query.answer()

    if query.data == 'add_admin':
        context.user_data['target_role'] = "admin"
        await query.edit_message_text("👨‍💻 Envie o @username ou encaminhe uma mensagem:")
        return WAITING_FOR_USERNAME
        
    elif query.data == 'add_verified':
        context.user_data['target_role'] = "verified"
        await query.edit_message_text("🌸 Envie o @username ou encaminhe uma mensagem:")
        return WAITING_FOR_USERNAME
        
    else:
        await query.edit_message_text("❌ Operação cancelada.")
        return ConversationHandler.END

async def process_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa username recebido"""
    role = context.user_data.get('target_role')
    if not role:
        await update.message.reply_text("❌ Erro.")
        return ConversationHandler.END

    try:
        if update.message.forward_from:
            target_user = update.message.forward_from
            user_id = target_user.id
            username = (target_user.username or target_user.first_name or "").lower()
        else:
            username = update.message.text.strip().lstrip('@').lower()
            user_id = 0

        with db_lock:
            session = Session()
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            if existing:
                await update.message.reply_text("ℹ️ Já está na lista.")
                return ConversationHandler.END

            new_entry = UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()

        role_name = "administrador" if role == "admin" else "verificada"
        await update.message.reply_text(f"✅ @{username} adicionado(a) como {role_name}!")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro em process_username: {e}")
        await update.message.reply_text("❌ Ocorreu um erro.")
        return ConversationHandler.END
    finally:
        Session.remove()

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela operação"""
    await update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END

# ==================================================
# CONFIGURAÇÃO PRINCIPAL
# ==================================================

async def post_init(application: Application) -> None:
    """Executa após a inicialização"""
    logger.info("Bot iniciado com sucesso!")

async def post_stop(application: Application) -> None:
    """Executa ao parar o bot"""
    logger.info("Bot encerrado")

async def main():
    """Função principal"""
    try:
        init_db()
        logger.info("Banco de dados inicializado.")
    except Exception as e:
        logger.error(f"Falha ao inicializar banco de dados: {e}")
        return

    # Cria a aplicação com configurações para evitar conflitos
    application = Application.builder() \
        .token(BOT_TOKEN) \
        .post_init(post_init) \
        .post_stop(post_stop) \
        .read_timeout(30) \
        .write_timeout(30) \
        .connect_timeout(30) \
        .pool_timeout(30) \
        .get_updates_read_timeout(30) \
        .build()

    # Adiciona os handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addgroupadmin", add_group_admin))
    application.add_handler(CommandHandler("addverified", add_verified))
    
    # Handler para novos membros
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        new_member_check
    ))

    # Conversa interativa com configuração otimizada
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice, pattern='^(add_admin|add_verified|cancel)$')],
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT | filters.FORWARDED, process_username)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_operation)],
        per_message=True  # Alterado para True para evitar o warning
    )
    application.add_handler(conv_handler)

    # Adiciona handler de erros
    application.add_error_handler(error_handler)

    # Executa o bot com polling configurado
    await application.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        close_loop=False
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loga erros e tenta evitar conflitos"""
    logger.error(f"Erro durante a atualização {update}: {context.error}")
    
    # Verifica se é um erro de conflito (outra instância rodando)
    if "Conflict" in str(context.error):
        logger.warning("Conflito detectado - aguardando 10 segundos antes de tentar novamente")
        await asyncio.sleep(10)
        # Reinicia o polling
        if context.application.running:
            await context.application.stop()
            await asyncio.sleep(1)
            await context.application.initialize()
            await context.application.start()
            await context.application.updater.start_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
    except Exception as e:
        logger.error(f"Falha ao iniciar o bot: {e}")