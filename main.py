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

# Verifica e atualiza a estrutura do banco de dados
def check_and_update_db_structure():
    """Verifica e atualiza a estrutura do banco de dados se necessário."""
    try:
        conn = get_db_connection()
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
    finally:
        if conn is not None:
            conn.close()

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
        conn = get_db_connection()
        cur = conn.cursor()
        for command in commands:
            try:
                cur.execute(command)
            except Exception as e:
                logger.error(f"Erro ao executar comando SQL: {e}")
        cur.close()
        conn.commit()
        
        # Verifica e atualiza a estrutura se necessário
        check_and_update_db_structure()
        
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

def add_bot_admin(user_id: int, username: str, full_name: str) -> bool:
    """Adiciona um administrador do bot."""
    try:
        conn = get_db_connection()
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
    finally:
        if conn is not None:
            conn.close()

def add_group_admin(user_id: int, chat_id: int, username: str, full_name: str) -> bool:
    """Adiciona um administrador de grupo."""
    try:
        conn = get_db_connection()
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

def remove_verified_user(user_id: int) -> bool:
    """Remove um usuário verificado."""
    try:
        conn = get_db_connection()
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
    finally:
        if conn is not None:
            conn.close()

def remove_group_admin(user_id: int, chat_id: int) -> bool:
    """Remove um administrador de grupo."""
    try:
        conn = get_db_connection()
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
    finally:
        if conn is not None:
            conn.close()

def get_user_info(context: CallbackContext, user_ref: str, chat_id: int = None):
    """Obtém informações do usuário por ID, @username ou resposta a mensagem."""
    try:
        # Se for uma resposta a mensagem
        if user_ref == 'reply':
            if not context.message.reply_to_message:
                return None
            user = context.message.reply_to_message.from_user
            return user.id, user.username, user.full_name
        
        # Se for um ID numérico
        if user_ref.isdigit():
            user_id = int(user_ref)
            user = context.bot.get_chat(user_id)
            return user.id, user.username, user.full_name
        
        # Se for um @username (remove o @ se presente)
        if user_ref.startswith('@'):
            user_ref = user_ref[1:]
        
        # Tenta encontrar por username (só funciona se o usuário tiver iniciado chat com o bot)
        try:
            user = context.bot.get_chat(user_ref)
            return user.id, user.username, user.full_name
        except TelegramError:
            pass
        
        # Se estiver em um grupo, tenta encontrar pelo username
        if chat_id:
            try:
                member = context.bot.get_chat_member(chat_id, user_ref)
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
                [InlineKeyboardButton("Adicionar Verificada", callback_data='admin_add_verified')],
                [InlineKeyboardButton("Remover Verificada", callback_data='admin_remove_verified')],
                [InlineKeyboardButton("Adicionar Admin Grupo", callback_data='admin_add_group_admin')],
                [InlineKeyboardButton("Remover Admin Grupo", callback_data='admin_remove_group_admin')],
                [InlineKeyboardButton("Listar Verificadas", callback_data='admin_list_verified')],
                [InlineKeyboardButton("Listar Admins Grupo", callback_data='admin_list_group_admins')]
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
            "Por favor, entre em contato com @KarolzinhaSapeca para configurar "
            "suas permissões de administrador."
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_add_verified':
        response = (
            "👑 Adicionar conta verificada:\n\n"
            "Você pode adicionar de três formas:\n"
            "1. Respondendo a mensagem do usuário com /addverified\n"
            "2. Usando /addverified [ID_DO_USUÁRIO]\n"
            "3. Usando /addverified @username\n\n"
            "Exemplo:\n"
            "/addverified 123456789\n"
            "ou\n"
            "/addverified @username"
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_remove_verified':
        response = (
            "👑 Remover conta verificada:\n\n"
            "Você pode remover de três formas:\n"
            "1. Respondendo a mensagem do usuário com /removeverified\n"
            "2. Usando /removeverified [ID_DO_USUÁRIO]\n"
            "3. Usando /removeverified @username\n\n"
            "Exemplo:\n"
            "/removeverified 123456789\n"
            "ou\n"
            "/removeverified @username"
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_add_group_admin':
        response = (
            "👑 Adicionar administrador de grupo:\n\n"
            "Você pode adicionar de três formas:\n"
            "1. Respondendo a mensagem do usuário com /addgroupadmin [ID_DO_GRUPO]\n"
            "2. Usando /addgroupadmin [ID_USUÁRIO] [ID_GRUPO]\n"
            "3. Usando /addgroupadmin @username [ID_GRUPO]\n\n"
            "Exemplo:\n"
            "/addgroupadmin 123456789 -100987654321\n"
            "ou\n"
            "/addgroupadmin @username -100987654321"
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_remove_group_admin':
        response = (
            "👑 Remover administrador de grupo:\n\n"
            "Você pode remover de três formas:\n"
            "1. Respondendo a mensagem do usuário com /removegroupadmin [ID_DO_GRUPO]\n"
            "2. Usando /removegroupadmin [ID_USUÁRIO] [ID_GRUPO]\n"
            "3. Usando /removegroupadmin @username [ID_GRUPO]\n\n"
            "Exemplo:\n"
            "/removegroupadmin 123456789 -100987654321\n"
            "ou\n"
            "/removegroupadmin @username -100987654321"
        )
        query.edit_message_text(text=response)
    
    elif query.data == 'admin_list_verified':
        context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Use o comando /listverified para ver a lista de contas verificadas."
        )
    
    elif query.data == 'admin_list_group_admins':
        context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Use o comando /listgroupadmins para ver a lista de administradores de grupo."
        )

def add_verified_command(update: Update, context: CallbackContext) -> None:
    """Adiciona um usuário à lista de verificados."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    user_ref = context.args[0] if context.args else 'reply'
    user_info = get_user_info(context, user_ref)
    
    if not user_info:
        update.message.reply_text(
            "❌ Não foi possível identificar o usuário.\n"
            "Você pode:\n"
            "1. Responder a mensagem do usuário com /addverified\n"
            "2. Usar /addverified [ID_DO_USUÁRIO]\n"
            "3. Usar /addverified @username"
        )
        return

    user_id, username, full_name = user_info
    
    if add_verified_user(user_id, username, full_name):
        update.message.reply_text(
            f"✅ Usuário {full_name} (@{username}) adicionado como verificado.\n"
            f"Ele receberá o status 'Verificada' quando entrar em qualquer grupo."
        )
    else:
        update.message.reply_text(f"ℹ️ Usuário {full_name} já está na lista de verificados.")

def remove_verified_command(update: Update, context: CallbackContext) -> None:
    """Remove um usuário da lista de verificados."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    user_ref = context.args[0] if context.args else 'reply'
    user_info = get_user_info(context, user_ref)
    
    if not user_info:
        update.message.reply_text(
            "❌ Não foi possível identificar o usuário.\n"
            "Você pode:\n"
            "1. Responder a mensagem do usuário com /removeverified\n"
            "2. Usar /removeverified [ID_DO_USUÁRIO]\n"
            "3. Usar /removeverified @username"
        )
        return

    user_id, username, full_name = user_info
    
    if remove_verified_user(user_id):
        update.message.reply_text(
            f"✅ Usuário {full_name} (@{username}) removido da lista de verificados."
        )
    else:
        update.message.reply_text(f"ℹ️ Usuário {full_name} não estava na lista de verificados.")

def add_group_admin_command(update: Update, context: CallbackContext) -> None:
    """Adiciona um administrador de grupo."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    # Se for reply, o primeiro argumento é o chat_id
    if not context.args or (len(context.args) == 1 and update.message.reply_to_message):
        if not update.message.reply_to_message:
            update.message.reply_text("❌ Você precisa responder a mensagem do usuário ou fornecer ID/@username e ID do grupo.")
            return
        
        chat_id = context.args[0]
        user_info = get_user_info(context, 'reply')
    else:
        # Se não for reply, espera user_ref e chat_id
        if len(context.args) < 2:
            update.message.reply_text("❌ Você precisa fornecer ID/@username do usuário e ID do grupo.")
            return
        
        user_ref = context.args[0]
        chat_id = context.args[1]
        user_info = get_user_info(context, user_ref)

    try:
        chat_id = int(chat_id)
    except ValueError:
        update.message.reply_text("❌ ID do grupo deve ser um número.")
        return

    if not user_info:
        update.message.reply_text("❌ Não foi possível identificar o usuário.")
        return

    user_id, username, full_name = user_info
    
    if add_group_admin(user_id, chat_id, username, full_name):
        update.message.reply_text(
            f"✅ Usuário {full_name} (@{username}) adicionado como administrador do grupo {chat_id}.\n"
            f"Ele receberá permissões de admin quando entrar no grupo."
        )
    else:
        update.message.reply_text(f"ℹ️ Usuário {full_name} já é administrador do grupo {chat_id}.")

def remove_group_admin_command(update: Update, context: CallbackContext) -> None:
    """Remove um administrador de grupo."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    # Se for reply, o primeiro argumento é o chat_id
    if len(context.args) == 1 and update.message.reply_to_message:
        chat_id = context.args[0]
        user_info = get_user_info(context, 'reply')
    else:
        # Se não for reply, espera user_ref e chat_id
        if len(context.args) < 2:
            update.message.reply_text("❌ Você precisa fornecer ID/@username do usuário e ID do grupo.")
            return
        
        user_ref = context.args[0]
        chat_id = context.args[1]
        user_info = get_user_info(context, user_ref)

    try:
        chat_id = int(chat_id)
    except ValueError:
        update.message.reply_text("❌ ID do grupo deve ser um número.")
        return

    if not user_info:
        update.message.reply_text("❌ Não foi possível identificar o usuário.")
        return

    user_id, username, full_name = user_info
    
    if remove_group_admin(user_id, chat_id):
        update.message.reply_text(
            f"✅ Usuário {full_name} (@{username}) removido como administrador do grupo {chat_id}."
        )
    else:
        update.message.reply_text(f"ℹ️ Usuário {full_name} não era administrador do grupo {chat_id}.")

def list_verified_command(update: Update, context: CallbackContext) -> None:
    """Lista todos os usuários verificados."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, full_name FROM verified_users WHERE status = 'approved'")
        verified_users = cur.fetchall()
        
        if not verified_users:
            update.message.reply_text("ℹ️ Não há usuários verificados no momento.")
            return

        response = ["✅ Lista de usuários verificados:\n"]
        for user_id, username, full_name in verified_users:
            username_display = f"@{username}" if username else "(sem username)"
            response.append(f"- {full_name} ({username_display}) - ID: {user_id}")
        
        update.message.reply_text("\n".join(response))
    except Exception as e:
        logger.error(f"Erro ao listar usuários verificados: {e}")
        update.message.reply_text("❌ Ocorreu um erro ao listar os usuários verificados.")
    finally:
        if conn is not None:
            conn.close()

def list_group_admins_command(update: Update, context: CallbackContext) -> None:
    """Lista todos os administradores de grupo."""
    if not is_bot_admin(update.effective_user.id):
        update.message.reply_text("❌ Você não tem permissão para executar este comando.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, chat_id, username, full_name FROM group_admins")
        group_admins = cur.fetchall()
        
        if not group_admins:
            update.message.reply_text("ℹ️ Não há administradores de grupo configurados no momento.")
            return

        response = ["👑 Lista de administradores de grupo:\n"]
        for user_id, chat_id, username, full_name in group_admins:
            username_display = f"@{username}" if username else "(sem username)"
            response.append(f"- {full_name} ({username_display}) - ID: {user_id} no grupo {chat_id}")
        
        update.message.reply_text("\n".join(response))
    except Exception as e:
        logger.error(f"Erro ao listar administradores de grupo: {e}")
        update.message.reply_text("❌ Ocorreu um erro ao listar os administradores de grupo.")
    finally:
        if conn is not None:
            conn.close()

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
                admin_id_int = int(admin_id.strip())
                try:
                    # Cria uma instância temporária do bot para obter informações
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
                        # Insere apenas o ID se não conseguir obter informações
                        cur.execute(
                            "INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                            (admin_id_int,)
                        )
                except Exception as e:
                    logger.error(f"Erro ao configurar admin {admin_id}: {e}")
        
        conn.commit()
    except Exception as e:
        logger.error(f"Erro ao configurar admins do bot: {e}")
        # Tenta continuar mesmo com erro na configuração dos admins
    finally:
        if conn is not None:
            conn.close()

    updater = Updater(token)
    dispatcher = updater.dispatcher

    # Handlers de comandos
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("addverified", add_verified_command))
    dispatcher.add_handler(CommandHandler("removeverified", remove_verified_command))
    dispatcher.add_handler(CommandHandler("addgroupadmin", add_group_admin_command))
    dispatcher.add_handler(CommandHandler("removegroupadmin", remove_group_admin_command))
    dispatcher.add_handler(CommandHandler("listverified", list_verified_command))
    dispatcher.add_handler(CommandHandler("listgroupadmins", list_group_admins_command))
    
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