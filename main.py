import os
import logging
from typing import Dict, Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    ChatMember,
    BotCommand,
    ParseMode
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ChatMemberHandler,
    ConversationHandler
)
from telegram.error import BadRequest, Unauthorized
import json
from config import TOKEN, ADMIN_IDS

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversa
SETTING_WELCOME, SETTING_RULES = range(2)

# Caminhos dos arquivos de dados
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
WELCOME_MSG_FILE = os.path.join(DATA_DIR, 'welcome_messages.json')
VERIFIED_USERS_FILE = os.path.join(DATA_DIR, 'verified_users.json')
GROUP_SETTINGS_FILE = os.path.join(DATA_DIR, 'group_settings.json')

# Carregar dados
def load_data(file_path: str, default_data=None):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data if default_data is not None else {}

# Salvar dados
def save_data(file_path: str, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

# Carregar dados iniciais
welcome_messages = load_data(WELCOME_MSG_FILE, {})
verified_users = load_data(VERIFIED_USERS_FILE, {})
group_settings = load_data(GROUP_SETTINGS_FILE, {})

# Funções auxiliares
def is_admin(update: Update, context: CallbackContext) -> bool:
    user = update.effective_user
    if user.id in ADMIN_IDS:
        return True
    
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return False
    
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]
    except:
        return False

def delete_message(update: Update, context: CallbackContext):
    try:
        update.message.delete()
    except (BadRequest, Unauthorized) as e:
        logger.warning(f"Failed to delete message: {e}")

def get_group_settings(chat_id: int) -> Dict:
    return group_settings.get(str(chat_id), {
        'delete_old_welcome': False,
        'block_links': True,
        'block_forwards': True,
        'welcome_buttons': {
            'rules': True,
            'channel': True,
            'website': False
        }
    })

# Mensagem de boas-vindas melhorada
def send_enhanced_welcome(update: Update, context: CallbackContext, new_member):
    chat_id = update.effective_chat.id
    settings = get_group_settings(chat_id)
    
    default_welcome = (
        f"🌟 Bem-vindo(a), {new_member.mention_html()}! 🌟\n\n"
        "Você acabou de entrar em um grupo especial! Aqui estão algumas coisas que posso fazer:\n"
        "✅ Manter o grupo seguro e organizado\n"
        "🛡️ Bloquear links e spam automaticamente\n"
        "👋 Personalizar mensagens de boas-vindas\n"
        "⚡ Gerenciar usuários problemáticos\n\n"
        "Por favor, leia as regras abaixo e aproveite sua estadia!"
    )
    
    welcome_msg = welcome_messages.get(str(chat_id), default_welcome)
    
    # Construir teclado de botões
    buttons = []
    if settings['welcome_buttons'].get('rules', True):
        buttons.append(InlineKeyboardButton("📜 Regras", callback_data="show_rules"))
    if settings['welcome_buttons'].get('channel', True):
        buttons.append(InlineKeyboardButton("📢 Canal", url="https://t.me/seucanal"))
    if settings['welcome_buttons'].get('website', False):
        buttons.append(InlineKeyboardButton("🌐 Site", url="https://seusite.com"))
    
    keyboard = [buttons] if buttons else None
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    sent_msg = context.bot.send_message(
        chat_id=chat_id,
        text=welcome_msg,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    # Gerenciar mensagens antigas se configurado
    if settings.get('delete_old_welcome', False):
        if 'last_welcome_message_id' in context.chat_data:
            try:
                context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=context.chat_data['last_welcome_message_id']
                )
            except BadRequest as e:
                logger.warning(f"Failed to delete old welcome message: {e}")
        context.chat_data['last_welcome_message_id'] = sent_msg.message_id

# Configuração via chat privado
def start_private_chat(update: Update, context: CallbackContext):
    if update.effective_chat.type != 'private':
        return
    
    user = update.effective_user
    if not is_admin(update, context):
        update.message.reply_text(
            "Olá! Eu sou um bot de gerenciamento de grupos. "
            "Apenas administradores podem me configurar."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Configurar Mensagem de Boas-vindas", callback_data="setup_welcome")],
        [InlineKeyboardButton("🔧 Configurações do Grupo", callback_data="group_settings")],
        [InlineKeyboardButton("👥 Gerenciar Usuários Verificados", callback_data="manage_verified")]
    ]
    
    update.message.reply_text(
        "🛠️ *Painel de Controle do Bot* 🛠️\n\n"
        "Escolha uma opção abaixo para configurar o bot:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def setup_welcome_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "✍️ *Configuração de Boas-vindas*\n\n"
        "Por favor, envie a nova mensagem de boas-vindas. Você pode usar:\n"
        "- `{name}`: Nome do usuário\n"
        "- `{username}`: @username (se disponível)\n"
        "- `{id}`: ID do usuário\n\n"
        "Exemplo:\n"
        "`Olá {name}! Bem-vindo ao nosso grupo!`",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return SETTING_WELCOME

def setting_welcome(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    welcome_messages[chat_id] = update.message.text
    save_data(WELCOME_MSG_FILE, welcome_messages)
    
    update.message.reply_text(
        "✅ Mensagem de boas-vindas atualizada com sucesso!\n\n"
        "Pré-visualização:\n" + update.message.text.replace('{name}', 'NovoMembro')
    )
    
    return ConversationHandler.END

# Comandos administrativos com botões
def admin_panel(update: Update, context: CallbackContext):
    if not is_admin(update, context):
        return
    
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Advertir", callback_data="warn_user"),
            InlineKeyboardButton("🔇 Silenciar", callback_data="mute_user")
        ],
        [
            InlineKeyboardButton("🚫 Banir", callback_data="ban_user"),
            InlineKeyboardButton("🛡️ Verificados", callback_data="verified_list")
        ],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="group_settings_main")]
    ]
    
    update.message.reply_text(
        "👮 *Painel de Administração* 👮\n\n"
        "Selecione uma ação:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    delete_message(update, context)

def show_group_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    settings = get_group_settings(chat_id)
    
    text = (
        "⚙️ *Configurações do Grupo* ⚙️\n\n"
        f"🔹 Apagar mensagens antigas: {'✅' if settings['delete_old_welcome'] else '❌'}\n"
        f"🔹 Bloquear links: {'✅' if settings['block_links'] else '❌'}\n"
        f"🔹 Bloquear encaminhamentos: {'✅' if settings['block_forwards'] else '❌'}\n\n"
        "Botões de boas-vindas:\n"
        f"- Regras: {'✅' if settings['welcome_buttons'].get('rules', True) else '❌'}\n"
        f"- Canal: {'✅' if settings['welcome_buttons'].get('channel', True) else '❌'}\n"
        f"- Website: {'✅' if settings['welcome_buttons'].get('website', False) else '❌'}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Alternar Apagar Mensagens", callback_data="toggle_delete"),
            InlineKeyboardButton("🔗 Alternar Links", callback_data="toggle_links")
        ],
        [
            InlineKeyboardButton("↩️ Alternar Encaminhamentos", callback_data="toggle_forwards"),
            InlineKeyboardButton("👋 Botões Boas-vindas", callback_data="welcome_buttons")
        ],
        [InlineKeyboardButton("🔙 Voltar", callback_data="back_to_main")]
    ]
    
    query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    data = query.data
    
    if data == "setup_welcome":
        setup_welcome_callback(update, context)
    elif data == "group_settings":
        show_group_settings(update, context)
    elif data == "manage_verified":
        query.edit_message_text("Funcionalidade de gerenciar usuários verificados será implementada em breve!")
    elif data == "toggle_delete":
        toggle_setting(update, context, 'delete_old_welcome')
    elif data == "toggle_links":
        toggle_setting(update, context, 'block_links')
    elif data == "toggle_forwards":
        toggle_setting(update, context, 'block_forwards')
    elif data == "back_to_main":
        start_private_chat(update, context)

def toggle_setting(update: Update, context: CallbackContext, setting_name: str):
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    
    if chat_id not in group_settings:
        group_settings[chat_id] = get_group_settings(chat_id)
    
    group_settings[chat_id][setting_name] = not group_settings[chat_id].get(setting_name, False)
    save_data(GROUP_SETTINGS_FILE, group_settings)
    
    show_group_settings(update, context)

def main():
    # Criar o Updater e passar o token do bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Configurar comandos do bot
    commands = [
        BotCommand("start", "Iniciar o bot"),
        BotCommand("admin", "Painel de administração"),
        BotCommand("help", "Ajuda e informações")
    ]
    updater.bot.set_my_commands(commands)

    # Handlers de conversação para configuração
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_welcome_callback, pattern='^setup_welcome$')],
        states={
            SETTING_WELCOME: [MessageHandler(Filters.text & ~Filters.command, setting_welcome)],
        },
        fallbacks=[CommandHandler('cancel', lambda u,c: ConversationHandler.END)]
    )
    dp.add_handler(conv_handler)

    # Handlers principais
    dp.add_handler(CommandHandler("start", start_private_chat))
    dp.add_handler(CommandHandler("admin", admin_panel))
    dp.add_handler(CallbackQueryHandler(button_handler))
    
    # Handler para novos membros
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, 
                               lambda u,c: [send_enhanced_welcome(u,c, member) for member in u.message.new_chat_members]))

    # Iniciar o bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()