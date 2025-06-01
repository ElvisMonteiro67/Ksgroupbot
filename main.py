import os
import logging
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    Updater, 
    CommandHandler, 
    MessageHandler, 
    Filters, 
    CallbackContext, 
    CallbackQueryHandler, 
    ConversationHandler
)
from sqlalchemy import create_engine, Column, Integer, String, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from threading import Lock

# Configuração avançada de logging para o Render
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente (configuradas no Render)
DATABASE_URL = os.getenv("DATABASE_URL")  # Render fornece automaticamente para PostgreSQL
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_ADMIN_ID = int(os.getenv("BOT_ADMIN_ID", "0"))  # ID do admin como número

# Configuração do SQLAlchemy com pool de conexões otimizado para Render
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Importante para Render
    pool_recycle=300     # Reconectar a cada 5 minutos
)

# Sessão thread-safe para o Render
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

# Lock para operações de banco de dados
db_lock = Lock()

Base = declarative_base()

class UserRole(Base):
    __tablename__ = 'user_roles'
    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=False)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" ou "verified"

def init_db():
    """Cria as tabelas se não existirem, com tratamento de erro para Render"""
    try:
        with db_lock:
            Base.metadata.create_all(engine)
            logger.info("Tabelas do banco de dados verificadas/criadas com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
        raise

# -------------------------------------------------
# Funções para os comandos de administração no grupo
# -------------------------------------------------

def add_user_to_list(update: Update, context: CallbackContext, role: str):
    """Função auxiliar para adicionar um usuário à lista desejada."""
    if update.effective_user.id != BOT_ADMIN_ID:
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    try:
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            telegram_user_id = target_user.id
            username = (target_user.username or target_user.first_name or "").lower()
        elif context.args:
            username = context.args[0].lstrip('@').lower()
            telegram_user_id = 0
        else:
            update.message.reply_text("Utilize respondendo a uma mensagem ou com um username.")
            return

        with db_lock:
            session = Session()
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == telegram_user_id, UserRole.username == username)
            ).first()

            if existing:
                update.message.reply_text("Usuário já está na lista.")
                Session.remove()
                return

            new_entry = UserRole(
                telegram_user_id=telegram_user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()
            Session.remove()

        reply_text = {
            "admin": f"@{username} adicionado à lista de administradores.",
            "verified": f"@{username} adicionado à lista de verificadas."
        }.get(role, "Operação concluída.")

        update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Erro em add_user_to_list: {e}")
        update.message.reply_text("Ocorreu um erro ao processar sua solicitação.")
        Session.remove()

def add_group_admin(update: Update, context: CallbackContext):
    """Comando para adicionar um usuário à lista de administradores de grupo."""
    add_user_to_list(update, context, "admin")

def add_verified(update: Update, context: CallbackContext):
    """Comando para adicionar um usuário à lista de verificadas."""
    add_user_to_list(update, context, "verified")

# -------------------------------------------------
# Handler para verificação de novos membros no grupo
# -------------------------------------------------

def new_member_check(update: Update, context: CallbackContext):
    """Verifica novos membros e aplica as permissões conforme a lista."""
    if not update.message or not update.message.new_chat_members:
        return

    try:
        for new_member in update.message.new_chat_members:
            user_id = new_member.id
            username = (new_member.username or new_member.first_name or "").lower()

            with db_lock:
                session = Session()
                
                # Verifica se é admin
                is_admin = session.query(UserRole).filter(
                    UserRole.role == "admin",
                    or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
                ).first()

                # Verifica se é verificado
                is_verified = session.query(UserRole).filter(
                    UserRole.role == "verified",
                    or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
                ).first()
                
                Session.remove()

            if is_admin:
                try:
                    context.bot.promote_chat_member(
                        chat_id=update.effective_chat.id,
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
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Bem-vindo admin @{username}!"
                    )
                except Exception as e:
                    logger.error(f"Erro ao promover admin: {e}")

            elif is_verified:
                try:
                    context.bot.promote_chat_member(
                        chat_id=update.effective_chat.id,
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
                    context.bot.set_chat_administrator_custom_title(
                        chat_id=update.effective_chat.id,
                        user_id=user_id,
                        custom_title="Verificada"
                    )
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Bem-vinda @{username}! Você foi verificada."
                    )
                except Exception as e:
                    logger.error(f"Erro ao verificar usuário: {e}")

    except Exception as e:
        logger.error(f"Erro em new_member_check: {e}")

# -------------------------------------------------
# Conversa interativa em privado para adicionar usuários
# -------------------------------------------------

CHOOSING_ACTION, WAITING_FOR_USERNAME = range(2)

def manage(update: Update, context: CallbackContext) -> int:
    """Inicia o menu de gerenciamento."""
    if update.effective_user.id != BOT_ADMIN_ID:
        update.message.reply_text("Acesso negado.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Adicionar Administrador", callback_data='add_admin')],
        [InlineKeyboardButton("Adicionar Verificada", callback_data='add_verified')]
    ]
    update.message.reply_text(
        "Escolha a ação:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION

def action_choice_callback(update: Update, context: CallbackContext) -> int:
    """Processa a escolha do menu."""
    query = update.callback_query
    query.answer()

    if query.data == 'add_admin':
        context.user_data['target_role'] = "admin"
        query.edit_message_text("Envie o username ou encaminhe uma mensagem do usuário para adicionar como Admin:")
    elif query.data == 'add_verified':
        context.user_data['target_role'] = "verified"
        query.edit_message_text("Envie o username ou encaminhe uma mensagem do usuário para adicionar como Verificada:")
    else:
        query.edit_message_text("Ação cancelada.")
        return ConversationHandler.END

    return WAITING_FOR_USERNAME

def receive_username(update: Update, context: CallbackContext) -> int:
    """Processa o username recebido."""
    role = context.user_data.get('target_role')
    if not role:
        update.message.reply_text("Erro: role não definida.")
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
                update.message.reply_text("Usuário já está na lista.")
                Session.remove()
                return ConversationHandler.END

            new_entry = UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()
            Session.remove()

        update.message.reply_text(f"@{username} adicionado como {'admin' if role == 'admin' else 'verificada'}!")
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro em receive_username: {e}")
        update.message.reply_text("Ocorreu um erro. Tente novamente.")
        return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancela a operação."""
    update.message.reply_text('Operação cancelada.')
    return ConversationHandler.END

# -------------------------------------------------
# Configuração principal do bot
# -------------------------------------------------

def main():
    # Inicialização segura para o Render
    try:
        init_db()
        logger.info("Banco de dados inicializado com sucesso.")
    except Exception as e:
        logger.error(f"Falha crítica ao inicializar banco de dados: {e}")
        return

    # Configuração do Updater com parâmetros otimizados para Render
    updater = Updater(
        BOT_TOKEN,
        use_context=True,
        workers=4,  # Número adequado para o plano básico do Render
        request_kwargs={
            'read_timeout': 30,
            'connect_timeout': 30
        }
    )

    dp = updater.dispatcher

    # Handlers para comandos de grupo
    dp.add_handler(CommandHandler("addgroupadmin", add_group_admin))
    dp.add_handler(CommandHandler("addverified", add_verified))
    dp.add_handler(MessageHandler(
        Filters.status_update.new_chat_members,
        new_member_check
    ))

    # Conversa interativa para admin
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice_callback)],
            WAITING_FOR_USERNAME: [
                MessageHandler(Filters.text | Filters.forwarded, receive_username)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    dp.add_handler(conv_handler)

    # Inicia o bot com tratamento de erros
    try:
        # Polling otimizado para Render
        updater.start_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True  # Importante para evitar processamento duplicado
        )
        logger.info("Bot iniciado com sucesso no modo polling.")
        updater.idle()
    except Exception as e:
        logger.error(f"Falha crítica ao iniciar o bot: {e}")
    finally:
        # Garante que a sessão seja removida ao encerrar
        Session.remove()

if __name__ == '__main__':
    main()