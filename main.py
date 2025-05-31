import os
import logging
from typing import Dict, List, Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    ChatMember,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ChatMemberHandler,
)
from telegram.error import BadRequest
import json
from config import TOKEN, ADMIN_IDS

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Caminhos dos arquivos de dados
WELCOME_MSG_FILE = 'data/welcome_messages.json'
VERIFIED_USERS_FILE = 'data/verified_users.json'
GROUP_SETTINGS_FILE = 'data/group_settings.json'

# Carregar dados
def load_data(file_path: str, default_data=None):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data if default_data is not None else {}

# Salvar dados
def save_data(file_path: str, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

# Carregar dados iniciais
welcome_messages = load_data(WELCOME_MSG_FILE, {})
verified_users = load_data(VERIFIED_USERS_FILE, {})
group_settings = load_data(GROUP_SETTINGS_FILE, {})

# Funções auxiliares
def is_admin(update: Update, context: CallbackContext) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    
    if user.id in ADMIN_IDS:
        return True
    
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]
    except:
        return False

def is_verified(user_id: int) -> bool:
    return str(user_id) in verified_users

def delete_message(update: Update, context: CallbackContext):
    try:
        update.message.delete()
    except BadRequest as e:
        logger.warning(f"Failed to delete message: {e}")

# Comandos de administração
def warn_user(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text("Por favor, responda à mensagem do usuário que deseja advertir.")
        return

    warned_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    # Adicionar advertência (implementar lógica de contagem se desejar)
    context.bot.send_message(
        chat_id,
        f"⚠️ {warned_user.mention_html()} foi advertido por {update.effective_user.mention_html()}.",
        parse_mode='HTML'
    )
    delete_message(update, context)

def mute_user(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text("Por favor, responda à mensagem do usuário que deseja silenciar.")
        return

    user_to_mute = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        context.bot.restrict_chat_member(
            chat_id,
            user_to_mute.id,
            ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        )
        context.bot.send_message(
            chat_id,
            f"🔇 {user_to_mute.mention_html()} foi silenciado por {update.effective_user.mention_html()}.",
            parse_mode='HTML'
        )
    except BadRequest as e:
        context.bot.send_message(chat_id, f"Erro ao silenciar usuário: {e}")
    
    delete_message(update, context)

def ban_user(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text("Por favor, responda à mensagem do usuário que deseja banir.")
        return

    user_to_ban = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        context.bot.ban_chat_member(chat_id, user_to_ban.id)
        context.bot.send_message(
            chat_id,
            f"🚫 {user_to_ban.mention_html()} foi banido por {update.effective_user.mention_html()}.",
            parse_mode='HTML'
        )
    except BadRequest as e:
        context.bot.send_message(chat_id, f"Erro ao banir usuário: {e}")
    
    delete_message(update, context)

# Gerenciamento de mensagens de boas-vindas
def set_welcome(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    chat_id = str(update.effective_chat.id)
    if not context.args:
        update.message.reply_text("Por favor, forneça a mensagem de boas-vindas.\nExemplo: /setwelcome Olá {name}, bem-vindo ao grupo!")
        return

    welcome_message = ' '.join(context.args)
    welcome_messages[chat_id] = welcome_message
    save_data(WELCOME_MSG_FILE, welcome_messages)
    
    update.message.reply_text("Mensagem de boas-vindas atualizada com sucesso!")
    delete_message(update, context)

def welcome_new_member(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    
    # Verificar se é uma mensagem de novo membro
    for new_member in update.message.new_chat_members:
        # Verificar se é um usuário verificado e promover se necessário
        if str(new_member.id) in verified_users:
            try:
                context.bot.promote_chat_member(
                    chat_id=update.effective_chat.id,
                    user_id=new_member.id,
                    can_change_info=False,
                    can_post_messages=False,
                    can_edit_messages=False,
                    can_delete_messages=False,
                    can_invite_users=False,
                    can_restrict_members=False,
                    can_pin_messages=False,
                    can_promote_members=False,
                    can_manage_video_chats=False,
                    can_manage_chat=False
                )
                context.bot.set_chat_administrator_custom_title(
                    chat_id=update.effective_chat.id,
                    user_id=new_member.id,
                    custom_title="Verificado"
                )
            except BadRequest as e:
                logger.error(f"Erro ao promover usuário verificado: {e}")
        
        # Enviar mensagem de boas-vindas
        welcome_msg = welcome_messages.get(chat_id, "Olá {name}, bem-vindo ao grupo!")
        welcome_msg = welcome_msg.replace("{name}", new_member.mention_html())
        
        keyboard = [
            [
                InlineKeyboardButton("📢 Canal", url="https://t.me/seucanal"),
                InlineKeyboardButton("📚 Regras", callback_data="rules")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_msg,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Configuração para apagar mensagens antigas de boas-vindas
        if group_settings.get(chat_id, {}).get('delete_old_welcome', False):
            if 'last_welcome_message_id' in context.chat_data:
                try:
                    context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=context.chat_data['last_welcome_message_id']
                    )
                except BadRequest as e:
                    logger.warning(f"Failed to delete old welcome message: {e}")
            
            context.chat_data['last_welcome_message_id'] = sent_msg.message_id

# Configurações do grupo
def toggle_welcome_delete(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    chat_id = str(update.effective_chat.id)
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    
    current = group_settings[chat_id].get('delete_old_welcome', False)
    group_settings[chat_id]['delete_old_welcome'] = not current
    save_data(GROUP_SETTINGS_FILE, group_settings)
    
    status = "ativada" if not current else "desativada"
    update.message.reply_text(f"Exclusão automática de mensagens antigas de boas-vindas {status}.")
    delete_message(update, context)

# Gerenciamento de links e encaminhamentos
def filter_messages(update: Update, context: CallbackContext):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    chat_id = str(update.effective_chat.id)
    settings = group_settings.get(chat_id, {})
    
    # Verificar se o filtro de links está ativado
    if settings.get('block_links', False):
        # Verificar se a mensagem contém links
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type in ['url', 'text_link']:
                    if not is_admin(update, context):
                        update.message.delete()
                        context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"❌ Links não são permitidos neste grupo. {update.effective_user.mention_html()} sua mensagem foi removida.",
                            parse_mode='HTML'
                        )
                        return
    
    # Verificar se o filtro de encaminhamentos está ativado
    if settings.get('block_forwards', False) and update.message.forward_from_chat:
        if not is_admin(update, context):
            update.message.delete()
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Encaminhamentos de outros chats não são permitidos. {update.effective_user.mention_html()} sua mensagem foi removida.",
                parse_mode='HTML'
            )
            return

# Gerenciamento de usuários verificados
def add_verified(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if not context.args:
        update.message.reply_text("Por favor, forneça o ID do usuário a ser verificado.\nExemplo: /addverified 123456789")
        return

    user_id = context.args[0]
    verified_users[user_id] = True
    save_data(VERIFIED_USERS_FILE, verified_users)
    
    update.message.reply_text(f"Usuário {user_id} adicionado à lista de verificados.")
    delete_message(update, context)

def remove_verified(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if not context.args:
        update.message.reply_text("Por favor, forneça o ID do usuário a ser removido.\nExemplo: /removeverified 123456789")
        return

    user_id = context.args[0]
    if user_id in verified_users:
        del verified_users[user_id]
        save_data(VERIFIED_USERS_FILE, verified_users)
        update.message.reply_text(f"Usuário {user_id} removido da lista de verificados.")
    else:
        update.message.reply_text(f"Usuário {user_id} não está na lista de verificados.")
    
    delete_message(update, context)

# Comandos básicos
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Olá! Eu sou um bot de gerenciamento de grupos. Use /help para ver meus comandos.")

def help_command(update: Update, context: CallbackContext):
    if is_admin(update, context):
        help_text = """
        👮‍♂️ *Comandos de Administrador*:
        /warn - Advertir um usuário (responda a uma mensagem)
        /mute - Silenciar um usuário (responda a uma mensagem)
        /ban - Banir um usuário (responda a uma mensagem)
        /setwelcome [mensagem] - Definir mensagem de boas-vindas
        /togglewelcome - Ativar/desativar exclusão de mensagens antigas de boas-vindas
        /blocklinks - Ativar/desativar bloqueio de links
        /blockforwards - Ativar/desativar bloqueio de encaminhamentos
        
        🛡️ *Comandos de Dono* (apenas para donos do bot):
        /addverified [id] - Adicionar usuário verificado
        /removeverified [id] - Remover usuário verificado
        """
    else:
        help_text = "Você não tem permissão para usar comandos de administrador."
    
    update.message.reply_text(help_text, parse_mode='Markdown')

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        update.effective_message.reply_text("Ocorreu um erro ao processar seu comando.")

def main():
    # Criar o Updater e passar o token do bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers de comandos
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    
    # Comandos de administração
    dp.add_handler(CommandHandler("warn", warn_user))
    dp.add_handler(CommandHandler("mute", mute_user))
    dp.add_handler(CommandHandler("ban", ban_user))
    dp.add_handler(CommandHandler("setwelcome", set_welcome))
    dp.add_handler(CommandHandler("togglewelcome", toggle_welcome_delete))
    
    # Comandos de dono
    dp.add_handler(CommandHandler("addverified", add_verified))
    dp.add_handler(CommandHandler("removeverified", remove_verified))
    
    # Handlers de mensagens
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, welcome_new_member))
    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.groups, filter_messages))
    
    # Handler de erros
    dp.add_error_handler(error_handler)

    # Iniciar o bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()