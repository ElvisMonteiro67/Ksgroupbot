import os
import logging
import psycopg2
import sys
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
from telegram.error import TelegramError, Conflict
from urllib.parse import urlparse
from contextlib import contextmanager

# Configuração básica
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Gerenciador de contexto para conexões com o banco de dados
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

# Verifica e atualiza a estrutura do banco de dados
def check_and_update_db_structure():
    """Verifica e atualiza a estrutura do banco de dados se necessário."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            
            # Verifica se a coluna username existe na tabela bot_admins
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='bot_admins' AND column_name='username'
            """)
            if not cur.fetchone():
                # Adiciona as colunas faltantes
                cur.execute("ALTER TABLE bot_admins ADD COLUMN username VARCHAR(255)")
                cur.execute("ALTER TABLE bot_admins ADD COLUMN full_name VARCHAR(255)")
                conn.commit()
                logger.info("Estrutura da tabela bot_admins atualizada com sucesso.")
                
    except Exception as e:
        logger.error(f"Erro ao verificar estrutura do banco: {e}")

# Inicialização do banco de dados
def init_db():
    """Cria as tabelas necessárias no banco de dados."""
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
                try:
                    cur.execute(command)
                except Exception as e:
                    logger.error(f"Erro ao executar comando SQL: {e}")
            conn.commit()
            
            # Verifica e atualiza a estrutura se necessário
            check_and_update_db_structure()
            
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")

# Funções auxiliares de banco de dados
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

def add_bot_admin(user_id: int, username: str, full_name: str) -> bool:
    """Adiciona um administrador do bot."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO bot_admins (user_id, username, full_name) 
                VALUES (%s, %s, %s) ON CONFLICT (user_id) 
                DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name""",
                (user_id, username, full_name)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao adicionar admin do bot: {e}")
        return False

def add_group_admin(user_id: int, chat_id: int, username: str, full_name: str) -> bool:
    """Adiciona um administrador de grupo."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO group_admins (user_id, chat_id, username, full_name) 
                VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (user_id, chat_id, username, full_name)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao adicionar admin de grupo: {e}")
        return False

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

def remove_verified_user(user_id: int) -> bool:
    """Remove um usuário verificado."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM verified_users WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao remover usuário verificado: {e}")
        return False

def remove_group_admin(user_id: int, chat_id: int) -> bool:
    """Remove um administrador de grupo."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM group_admins WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao remover admin de grupo: {e}")
        return False

def get_user_by_username(context: CallbackContext, username: str, chat_id: int = None):
    """Obtém informações do usuário por @username."""
    try:
        if not username.startswith('@'):
            username = '@' + username
        
        # Remove o @ para a busca
        clean_username = username[1:]
        
        # Tenta encontrar por username (só funciona se o usuário tiver iniciado chat com o bot)
        try:
            user = context.bot.get_chat(username)
            return user.id, user.username, user.full_name
        except TelegramError:
            pass
        
        # Se estiver em um grupo, tenta encontrar pelo username
        if chat_id:
            try:
                member = context.bot.get_chat_member(chat_id, clean_username)
                return member.user.id, member.user.username, member.user.full_name
            except TelegramError:
                pass
        
        return None
    except Exception as e:
        logger.error(f"Erro ao obter informações do usuário: {e}")
        return None

# Comandos do bot
def start(update: Update, context: CallbackContext) -> None:
    """Envia mensagem de boas-vindas quando o comando /start é acionado."""
    if update.effective_chat.type == "private":
        if is_bot_admin(update.effective_user.id):
            # Menu para administradores do bot
            keyboard = [
                [InlineKeyboardButton("➕ Adicionar Verificada", callback_data='admin_add_verified')],
                [InlineKeyboardButton("➖ Remover Verificada", callback_data='admin_remove_verified')],
                [InlineKeyboardButton("👑 Adicionar Admin Grupo", callback_data='admin_add_group_admin')],
                [InlineKeyboardButton("👑 Remover Admin Grupo", callback_data='admin_remove_group_admin')],
                [InlineKeyboardButton("📋 Listar Verificadas", callback_data='admin_list_verified')],
                [InlineKeyboardButton("📋 Listar Admins Grupo", callback_data='admin_list_group_admins')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_message = (
                "👑 Olá administrador do bot!\n\n"
                "Escolha uma opção abaixo para gerenciar as listas:"
            )
            update.message.reply_text(welcome_message, reply_markup=reply_markup)
        else:
            # Menu para usuários normais
            keyboard = [
                [InlineKeyboardButton("✅ Seja uma Verificada", callback_data='be_verified')],
                [InlineKeyboardButton("👑 Sobre Admins", callback_data='about_admins')]
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
    
    elif query.data == 'about_admins':
        response = (
            "👑 Sobre administradores:\n\n"
            "Se você é administrador de algum grupo da KS Entretenimento, "
            "entre em contato com @KarolzinhaSapeca para configurar "
            "suas permissões de administrador."
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_add_verified':
        # Pede o @username do usuário a ser adicionado
        context.user_data['action'] = 'add_verified'
        query.edit_message_text(
            text="🔹 Digite o @username da conta que deseja adicionar como Verificada:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'admin_remove_verified':
        # Pede o @username do usuário a ser removido
        context.user_data['action'] = 'remove_verified'
        query.edit_message_text(
            text="🔹 Digite o @username da conta que deseja remover das Verificadas:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'admin_add_group_admin':
        # Pede o @username do admin e ID do grupo
        context.user_data['action'] = 'add_group_admin'
        query.edit_message_text(
            text="🔹 Digite o @username do novo admin e o ID do grupo (separados por espaço):\n\nExemplo: @username -100123456789",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'admin_remove_group_admin':
        # Pede o @username do admin e ID do grupo
        context.user_data['action'] = 'remove_group_admin'
        query.edit_message_text(
            text="🔹 Digite o @username do admin e o ID do grupo (separados por espaço):\n\nExemplo: @username -100123456789",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Cancelar", callback_data='cancel_action')]])
        )
    
    elif query.data == 'admin_list_verified':
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT user_id, username, full_name FROM verified_users WHERE status = 'approved'")
                verified_users = cur.fetchall()
                
                if not verified_users:
                    query.edit_message_text("ℹ️ Não há usuários verificados no momento.")
                    return

                response = ["✅ Lista de usuários verificados:\n"]
                for user_id, username, full_name in verified_users:
                    username_display = f"@{username}" if username else "(sem username)"
                    response.append(f"- {full_name} ({username_display}) - ID: {user_id}")
                
                # Divide a mensagem se for muito longa
                message = "\n".join(response)
                for i in range(0, len(message), 4096):
                    query.edit_message_text(text=message[i:i+4096])
        except Exception as e:
            logger.error(f"Erro ao listar usuários verificados: {e}")
            query.edit_message_text("❌ Ocorreu um erro ao listar os usuários verificados.")
    
    elif query.data == 'admin_list_group_admins':
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT user_id, chat_id, username, full_name FROM group_admins")
                group_admins = cur.fetchall()
                
                if not group_admins:
                    query.edit_message_text("ℹ️ Não há administradores de grupo configurados no momento.")
                    return

                response = ["👑 Lista de administradores de grupo:\n"]
                for user_id, chat_id, username, full_name in group_admins:
                    username_display = f"@{username}" if username else "(sem username)"
                    response.append(f"- {full_name} ({username_display}) - ID: {user_id} no grupo {chat_id}")
                
                # Divide a mensagem se for muito longa
                message = "\n".join(response)
                for i in range(0, len(message), 4096):
                    query.edit_message_text(text=message[i:i+4096])
        except Exception as e:
            logger.error(f"Erro ao listar administradores de grupo: {e}")
            query.edit_message_text("❌ Ocorreu um erro ao listar os administradores de grupo.")
    
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
    
    if action == 'add_verified' or action == 'remove_verified':
        if not text.startswith('@'):
            update.message.reply_text("❌ Por favor, insira um @username válido (começando com @).")
            return
        
        username = text[1:] if text.startswith('@') else text
        user_info = get_user_by_username(context, username)
        
        if not user_info:
            update.message.reply_text("❌ Não foi possível encontrar o usuário. Verifique se o @username está correto.")
            return
        
        user_id, username, full_name = user_info
        
        if action == 'add_verified':
            if add_verified_user(user_id, username, full_name):
                update.message.reply_text(
                    f"✅ Usuário {full_name} (@{username}) adicionado como verificado."
                )
            else:
                update.message.reply_text(f"ℹ️ Usuário {full_name} já está na lista de verificados.")
        else:
            if remove_verified_user(user_id):
                update.message.reply_text(
                    f"✅ Usuário {full_name} (@{username}) removido da lista de verificados."
                )
            else:
                update.message.reply_text(f"ℹ️ Usuário {full_name} não estava na lista de verificados.")
        
        del context.user_data['action']
    
    elif action == 'add_group_admin' or action == 'remove_group_admin':
        parts = text.split()
        if len(parts) < 2:
            update.message.reply_text("❌ Formato incorreto. Digite o @username e o ID do grupo separados por espaço.")
            return
        
        username_part = parts[0]
        chat_id_part = parts[1]
        
        if not username_part.startswith('@'):
            update.message.reply_text("❌ O username deve começar com @.")
            return
        
        try:
            chat_id = int(chat_id_part)
        except ValueError:
            update.message.reply_text("❌ O ID do grupo deve ser um número.")
            return
        
        username = username_part[1:] if username_part.startswith('@') else username_part
        user_info = get_user_by_username(context, username)
        
        if not user_info:
            update.message.reply_text("❌ Não foi possível encontrar o usuário. Verifique se o @username está correto.")
            return
        
        user_id, username, full_name = user_info
        
        if action == 'add_group_admin':
            if add_group_admin(user_id, chat_id, username, full_name):
                update.message.reply_text(
                    f"✅ Usuário {full_name} (@{username}) adicionado como administrador do grupo {chat_id}."
                )
            else:
                update.message.reply_text(f"ℹ️ Usuário {full_name} já é administrador do grupo {chat_id}.")
        else:
            if remove_group_admin(user_id, chat_id):
                update.message.reply_text(
                    f"✅ Usuário {full_name} (@{username}) removido como administrador do grupo {chat_id}."
                )
            else:
                update.message.reply_text(f"ℹ️ Usuário {full_name} não era administrador do grupo {chat_id}.")
        
        del context.user_data['action']

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
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM group_admins WHERE user_id = %s AND chat_id = %s",
                    (user_id, chat_id)
                )
                is_group_admin = cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar admin de grupo: {e}")
            is_group_admin = False

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
    """Lida com erros de forma segura."""
    try:
        error = context.error
        logger.error(f'Erro não tratado: {error}', exc_info=error)
        
        # Trata especificamente o erro de conflito
        if isinstance(error, Conflict) and "terminated by other getUpdates request" in str(error):
            logger.warning("Conflito detectado - outra instância em execução. Saindo...")
            sys.exit(0)
            
        # Tenta responder ao usuário se possível
        if update and hasattr(update, 'effective_message') and update.effective_message:
            update.effective_message.reply_text("❌ Ocorreu um erro ao processar seu comando.")
    except Exception as e:
        logger.error(f'Erro no manipulador de erros: {e}')

def ensure_single_instance(bot_token: str):
    """Verifica se não há outra instância do bot em execução."""
    try:
        test_bot = Bot(token=bot_token)
        try:
            test_bot.get_me()  # Testa a conexão com o Telegram
        except Conflict:
            logger.warning("Outra instância do bot já está em execução. Encerrando...")
            sys.exit(0)  # Encerra o programa normalmente
    except Exception as e:
        logger.error(f"Erro ao verificar instância única: {e}")
        raise

def main() -> None:
    """Inicia o bot com verificação de instância única."""
    # Configuração do bot
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("Por favor, defina a variável de ambiente TELEGRAM_TOKEN")
    
    # Verifica se já existe outra instância em execução
    ensure_single_instance(token)
    
    # Inicializa o banco de dados
    init_db()
    
    # Configura administradores do bot
    admin_ids = os.getenv('BOT_ADMINS', '').split(',')
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            
            for admin_id in admin_ids:
                if admin_id.strip().isdigit():
                    admin_id_int = int(admin_id.strip())
                    try:
                        temp_bot = Bot(token=token)
                        try:
                            user = temp_bot.get_chat(admin_id_int)
                            username = user.username if user.username else ''
                            full_name = user.full_name if user.full_name else ''
                            
                            cur.execute(
                                """INSERT INTO bot_admins (user_id, username, full_name) 
                                VALUES (%s, %s, %s) ON CONFLICT (user_id) 
                                DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name""",
                                (admin_id_int, username, full_name)
                            )
                        except TelegramError as e:
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

    # Configuração do Updater com parâmetros adicionais
    updater = Updater(
        token=token,
        use_context=True,
        request_kwargs={
            'read_timeout': 30,
            'connect_timeout': 30
        }
    )
    
    dispatcher = updater.dispatcher

    # Configuração dos handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command) & Filters.chat_type.private, handle_text_input))
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), handle_verification_keywords))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    dispatcher.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
    dispatcher.add_error_handler(error_handler)

    # Inicia o bot com tratamento de exceções
    try:
        updater.start_polling(
            drop_pending_updates=True,  # Ignora atualizações pendentes
            timeout=30,
            allowed_updates=[
                'message',
                'callback_query',
                'chat_member'
            ]
        )
        logger.info("Bot iniciado e aguardando mensagens...")
        updater.idle()
        
    except Conflict:
        logger.warning("Conflito detectado durante inicialização. Encerrando...")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Erro fatal ao iniciar o bot: {e}")
        raise

if __name__ == '__main__':
    main()