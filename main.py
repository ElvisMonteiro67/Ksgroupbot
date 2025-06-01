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
    CallbackContext, 
    CallbackQueryHandler, 
    ConversationHandler,
    filters
)
from sqlalchemy import create_engine, Column, Integer, String, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from threading import Lock

# ==================================================
# CONFIGURAÇÃO INICIAL
# ==================================================

# Configuração de logging detalhada para o Render
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

# Configuração do SQLAlchemy otimizada para Render
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Reconecta automaticamente
    pool_recycle=300     # Reconectar a cada 5 minutos
)

# Sessão thread-safe
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

# ==================================================
# FUNÇÕES AUXILIARES E DE BANCO DE DADOS
# ==================================================

def init_db():
    """Inicializa o banco de dados criando as tabelas se não existirem"""
    try:
        with db_lock:
            Base.metadata.create_all(engine)
            logger.info("Banco de dados inicializado com sucesso.")
    except Exception as e:
        logger.error(f"Falha ao inicializar banco de dados: {e}")
        raise

def get_db_session():
    """Retorna uma nova sessão de banco de dados"""
    return Session()

# ==================================================
# COMANDOS PÚBLICOS E MENSAGENS DE AJUDA
# ==================================================

def start(update: Update, context: CallbackContext):
    """Mensagem de boas-vindas e explicação do bot"""
    help_text = """
    🤖 *Bot de Gerenciamento de Grupos* 🤖

    *Para administradores:*
    /addgroupadmin @username - Adiciona um admin
    /addverified @username - Adiciona uma verificada
    /manage - Menu interativo (no privado)

    *Funcionalidades:*
    - Promove automaticamente usuários da lista de admins
    - Define título "Verificada" para usuárias verificadas
    - Interface amigável para gerenciamento

    Desenvolvido para facilitar a moderação de grupos!
    """
    update.message.reply_text(help_text, parse_mode='Markdown')

def help_command(update: Update, context: CallbackContext):
    """Exibe ajuda detalhada"""
    help_text = """
    📚 *Ajuda do Bot* 📚

    *Comandos disponíveis:*
    
    👨‍💻 *No grupo:*
    /addgroupadmin @username - Adiciona um usuário à lista de administradores
    /addverified @username - Adiciona uma usuária à lista de verificadas
    (Responda a uma mensagem do usuário ou mencione o @username)

    🔒 *No privado (apenas admin):*
    /manage - Menu interativo para gerenciamento
    /help - Exibe esta mensagem

    O bot automaticamente:
    - Promove administradores quando entram no grupo
    - Define o título "Verificada" para usuárias verificadas
    """
    update.message.reply_text(help_text, parse_mode='Markdown')

# ==================================================
# FUNÇÕES DE GERENCIAMENTO DE USUÁRIOS
# ==================================================

def add_user_to_list(update: Update, context: CallbackContext, role: str):
    """Adiciona um usuário à lista especificada (admin ou verified)"""
    if update.effective_user.id != BOT_ADMIN_ID:
        update.message.reply_text("❌ Você não tem permissão para este comando.")
        return

    try:
        # Verifica se foi respondendo a uma mensagem
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = (target_user.username or target_user.first_name or "").lower()
        # Ou se foi passado um username como argumento
        elif context.args:
            username = context.args[0].lstrip('@').lower()
            user_id = 0  # Não temos o ID real
        else:
            update.message.reply_text("ℹ️ Use respondendo a uma mensagem ou informando o @username.")
            return

        with db_lock:
            session = get_db_session()
            
            # Verifica se já existe
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            if existing:
                update.message.reply_text("ℹ️ Este usuário já está na lista.")
                return

            # Adiciona novo usuário
            new_entry = UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()

        # Mensagem de confirmação
        role_name = "administrador" if role == "admin" else "verificada"
        update.message.reply_text(f"✅ @{username} foi adicionado(a) como {role_name}!")

    except Exception as e:
        logger.error(f"Erro em add_user_to_list: {e}")
        update.message.reply_text("❌ Ocorreu um erro ao processar sua solicitação.")
    finally:
        Session.remove()

def add_group_admin(update: Update, context: CallbackContext):
    """Adiciona um administrador"""
    add_user_to_list(update, context, "admin")

def add_verified(update: Update, context: CallbackContext):
    """Adiciona uma usuária verificada"""
    add_user_to_list(update, context, "verified")

# ==================================================
# GERENCIAMENTO DE NOVOS MEMBROS
# ==================================================

def new_member_check(update: Update, context: CallbackContext):
    """Verifica novos membros e aplica as permissões conforme a lista"""
    if not update.message or not update.message.new_chat_members:
        return

    try:
        for new_member in update.message.new_chat_members:
            user_id = new_member.id
            username = (new_member.username or new_member.first_name or "").lower()

            with db_lock:
                session = get_db_session()
                
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

            # Aplica as permissões conforme o tipo de usuário
            if is_admin:
                promote_to_admin(context, update.effective_chat.id, user_id, username)
            elif is_verified:
                verify_user(context, update.effective_chat.id, user_id, username)

    except Exception as e:
        logger.error(f"Erro em new_member_check: {e}")

def promote_to_admin(context: CallbackContext, chat_id: int, user_id: int, username: str):
    """Promove um usuário a administrador"""
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
            is_anonymous=False
        )
        context.bot.send_message(
            chat_id=chat_id,
            text=f"👑 Bem-vindo admin @{username}! Você foi promovido automaticamente."
        )
    except Exception as e:
        logger.error(f"Erro ao promover admin: {e}")

def verify_user(context: CallbackContext, chat_id: int, user_id: int, username: str):
    """Define um usuário como verificado"""
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
            is_anonymous=True
        )
        context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title="Verificada"
        )
        context.bot.send_message(
            chat_id=chat_id,
            text=f"🌸 Bem-vinda @{username}! Seu status foi definido como Verificada."
        )
    except Exception as e:
        logger.error(f"Erro ao verificar usuário: {e}")

# ==================================================
# INTERFACE INTERATIVA DE GERENCIAMENTO
# ==================================================

# Estados da conversa
CHOOSING_ACTION, WAITING_FOR_USERNAME = range(2)

def manage(update: Update, context: CallbackContext) -> int:
    """Inicia o menu interativo de gerenciamento"""
    if update.effective_user.id != BOT_ADMIN_ID:
        update.message.reply_text("❌ Acesso restrito ao administrador.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Administrador", callback_data='add_admin')],
        [InlineKeyboardButton("➕ Adicionar Verificada", callback_data='add_verified')],
        [InlineKeyboardButton("❌ Cancelar", callback_data='cancel')]
    ]
    
    update.message.reply_text(
        "🔧 *Menu de Gerenciamento* 🔧\n"
        "Selecione a ação desejada:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CHOOSING_ACTION

def action_choice(update: Update, context: CallbackContext) -> int:
    """Processa a seleção do menu"""
    query = update.callback_query
    query.answer()

    if query.data == 'add_admin':
        context.user_data['target_role'] = "admin"
        query.edit_message_text(
            "👨‍💻 *Adicionar Administrador*\n"
            "Envie o @username ou encaminhe uma mensagem do usuário:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_USERNAME
        
    elif query.data == 'add_verified':
        context.user_data['target_role'] = "verified"
        query.edit_message_text(
            "🌸 *Adicionar Verificada*\n"
            "Envie o @username ou encaminhe uma mensagem da usuária:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_USERNAME
        
    else:  # Cancelar
        query.edit_message_text("❌ Operação cancelada.")
        return ConversationHandler.END

def process_username(update: Update, context: CallbackContext) -> int:
    """Processa o username recebido na conversa interativa"""
    role = context.user_data.get('target_role')
    if not role:
        update.message.reply_text("❌ Erro: tipo de usuário não definido.")
        return ConversationHandler.END

    try:
        # Se a mensagem foi encaminhada
        if update.message.forward_from:
            target_user = update.message.forward_from
            user_id = target_user.id
            username = (target_user.username or target_user.first_name or "").lower()
        else:
            # Se foi enviado o username diretamente
            username = update.message.text.strip().lstrip('@').lower()
            user_id = 0  # Não temos o ID real

        with db_lock:
            session = get_db_session()
            
            # Verifica se já existe
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            if existing:
                update.message.reply_text("ℹ️ Este usuário já está na lista.")
                return ConversationHandler.END

            # Adiciona novo registro
            new_entry = UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            )
            session.add(new_entry)
            session.commit()

        # Mensagem de sucesso
        role_name = "administrador" if role == "admin" else "verificada"
        update.message.reply_text(f"✅ @{username} adicionado(a) como {role_name} com sucesso!")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro em process_username: {e}")
        update.message.reply_text("❌ Ocorreu um erro. Tente novamente.")
        return ConversationHandler.END
    finally:
        Session.remove()

def cancel_operation(update: Update, context: CallbackContext) -> int:
    """Cancela a operação em andamento"""
    update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END

# ==================================================
# CONFIGURAÇÃO PRINCIPAL DO BOT
# ==================================================

def main():
    """Função principal que configura e inicia o bot"""
    try:
        # Inicializa o banco de dados
        init_db()
        logger.info("Banco de dados inicializado com sucesso.")
    except Exception as e:
        logger.error(f"Falha crítica ao inicializar banco de dados: {e}")
        return

    # Configura o updater com parâmetros otimizados para Render
    updater = Updater(
        BOT_TOKEN,
        use_context=True,
        workers=4,
        request_kwargs={
            'read_timeout': 30,
            'connect_timeout': 30
        }
    )

    dp = updater.dispatcher

    # Adiciona os handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("addgroupadmin", add_group_admin))
    dp.add_handler(CommandHandler("addverified", add_verified))
    
    # Handler para novos membros
    dp.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        new_member_check
    ))

    # Conversa interativa para gerenciamento
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice)],
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT | filters.FORWARDED, process_username)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_operation)],
        allow_reentry=True
    )
    dp.add_handler(conv_handler)

    # Inicia o bot com tratamento de erros
    try:
        updater.start_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True
        )
        logger.info("🤖 Bot iniciado com sucesso!")
        updater.idle()
    except Exception as e:
        logger.error(f"Falha ao iniciar o bot: {e}")
    finally:
        Session.remove()

if __name__ == '__main__':
    main()