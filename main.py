import os
import logging
import json
from typing import Dict, Optional, List
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    BotCommand,
    ParseMode,
    ChatMember,
    Chat
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    ChatMemberHandler
)
from config import TOKEN, ADMIN_IDS, BOT_CONFIG, DATABASE, RENDER_CONFIG, SECURITY

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversação
CONFIG_WELCOME_MSG, CONFIG_WELCOME_MEDIA, CONFIG_WELCOME_BUTTONS = range(3)

# Carregar dados
def load_data(file_path: str) -> Dict:
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Salvar dados
def save_data(file_path: str, data: Dict):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}")

# Inicializar dados
welcome_data = load_data(DATABASE['WELCOME_FILE'])
group_settings = load_data(DATABASE['GROUP_SETTINGS_FILE'])
warnings_data = load_data(DATABASE['WARNINGS_FILE'])

# Funções auxiliares
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_group_settings(chat_id: int) -> Dict:
    return group_settings.get(str(chat_id), {
        'block_links': True,
        'block_forwards': True,
        'block_bots': True,
        'welcome_enabled': True,
        'max_warnings': SECURITY['MAX_WARNINGS']
    })

def delete_message(update: Update):
    try:
        update.message.delete()
    except Exception as e:
        logger.warning(f"Não foi possível deletar mensagem: {e}")

# Handler de erros
def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Erro: {context.error}", exc_info=True)
    if update and update.effective_message:
        update.effective_message.reply_text("⚠️ Ocorreu um erro. Tente novamente.")

# MENSAGEM DE APRESENTAÇÃO DO BOT ---------------------------------

def bot_added_to_group(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            keyboard = [
                [InlineKeyboardButton("⚙️ Configurar Grupo", 
                    callback_data=f"config_group_{update.effective_chat.id}")],
                [InlineKeyboardButton("📜 Ver Comandos", callback_data="bot_help")]
            ]
            
            update.message.reply_text(
                f"🤖 *Obrigado por me adicionar ao grupo!*\n\n"
                f"Eu sou um bot de moderação completo. Para configurar minhas funções, "
                f"clique no botão abaixo ou me chame no privado.\n\n"
                f"Grupo: {update.effective_chat.title}\n"
                f"ID: `{update.effective_chat.id}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            break

# CONFIGURAÇÃO VIA BOTÕES (PV) -----------------------------------

def start_private(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⚠️ Você não tem permissão para configurar o bot.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👋 Configurar Boas-vindas", callback_data="config_welcome")],
        [InlineKeyboardButton("🛡️ Configurar Grupo", callback_data="list_groups")]
    ]
    
    update.message.reply_text(
        "🛠 *Painel de Controle do Bot* 🛠\n\n"
        "Escolha o que deseja configurar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def list_groups(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    # Simulação - na prática você precisaria armazenar os grupos onde o bot foi adicionado
    groups = {
        "12345": "Grupo Principal",
        "67890": "Grupo Secundário"
    }
    
    keyboard = []
    for chat_id, title in groups.items():
        keyboard.append([InlineKeyboardButton(
            f"{title} (ID: {chat_id})", 
            callback_data=f"config_group_{chat_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")])
    
    query.edit_message_text(
        "📋 *Selecione um grupo para configurar* 📋\n\n"
        "Lista de grupos onde estou presente:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def config_group_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    chat_id = query.data.split('_')[2]
    
    try:
        chat = context.bot.get_chat(chat_id)
        chat_title = chat.title
    except Exception as e:
        logger.error(f"Erro ao obter informações do chat: {e}")
        chat_title = f"Grupo (ID: {chat_id})"
    
    settings = get_group_settings(int(chat_id))
    
    keyboard = [
        [
            InlineKeyboardButton(f"🔗 Links: {'✅' if settings['block_links'] else '❌'}", 
                callback_data=f"toggle_links_{chat_id}"),
            InlineKeyboardButton(f"↩️ Encaminhamentos: {'✅' if settings['block_forwards'] else '❌'}", 
                callback_data=f"toggle_forwards_{chat_id}")
        ],
        [
            InlineKeyboardButton(f"🤖 Bots: {'✅' if settings['block_bots'] else '❌'}", 
                callback_data=f"toggle_bots_{chat_id}"),
            InlineKeyboardButton(f"👋 Boas-vindas: {'✅' if settings['welcome_enabled'] else '❌'}", 
                callback_data=f"toggle_welcome_{chat_id}")
        ],
        [InlineKeyboardButton("🔙 Voltar", callback_data="list_groups")]
    ]
    
    text = (
        f"⚙️ *Configurações do Grupo* ⚙️\n\n"
        f"📛 Nome: {chat_title}\n"
        f"🆔 ID: `{chat_id}`\n\n"
        f"Escolha o que deseja modificar:"
    )
    
    query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def toggle_setting(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    action, chat_id = query.data.split('_')[1], query.data.split('_')[2]
    settings = get_group_settings(int(chat_id))
    
    settings[action] = not settings[action]
    group_settings[chat_id] = settings
    save_data(DATABASE['GROUP_SETTINGS_FILE'], group_settings)
    
    config_group_menu(update, context)

# MAIN FUNCTION ---------------------------------------------------

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Registrar handler de erros
    dp.add_error_handler(error_handler)

    # Handlers de grupo
    dp.add_handler(MessageHandler(
        Filters.status_update.new_chat_members,
        bot_added_to_group
    ))
    
    # Handlers de comandos
    dp.add_handler(CommandHandler("start", start_private))
    
    # Handlers de callback
    dp.add_handler(CallbackQueryHandler(list_groups, pattern='^list_groups$'))
    dp.add_handler(CallbackQueryHandler(config_group_menu, pattern='^config_group_'))
    dp.add_handler(CallbackQueryHandler(toggle_setting, pattern='^toggle_'))
    dp.add_handler(CallbackQueryHandler(start_private, pattern='^main_menu$'))
    
    # Configurar comandos
    commands = [
        BotCommand("start", "Abrir painel de controle"),
        BotCommand("warn", "Advertir usuário"),
        BotCommand("mute", "Silenciar usuário"),
        BotCommand("ban", "Banir usuário")
    ]
    updater.bot.set_my_commands(commands)
    
    # Iniciar bot
    if RENDER_CONFIG['WEBHOOK_URL']:
        updater.start_webhook(
            listen=RENDER_CONFIG['HOST'],
            port=RENDER_CONFIG['PORT'],
            url_path=TOKEN,
            webhook_url=f"{RENDER_CONFIG['WEBHOOK_URL']}/{TOKEN}",
            drop_pending_updates=True
        )
    else:
        updater.start_polling(drop_pending_updates=True)
    
    logger.info("Bot iniciado com sucesso")
    updater.idle()

if __name__ == '__main__':
    main()