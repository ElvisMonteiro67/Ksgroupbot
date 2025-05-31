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
    InputMediaPhoto
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
CONFIG_GROUP_SETTINGS = 1

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
                [InlineKeyboardButton("⚙️ Configurar Grupo", url=f"t.me/{context.bot.username}?start=config_{update.effective_chat.id}")],
                [InlineKeyboardButton("📜 Ver Comandos", callback_data="bot_help")]
            ]
            
            update.message.reply_text(
                f"🤖 *Obrigado por me adicionar ao grupo!*\n\n"
                f"Eu sou um bot de moderação completo. Para configurar minhas funções, "
                f"clique no botão abaixo ou me chame no privado.\n\n"
                f"Use /help para ver todos os comandos.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            break

# CONFIGURAÇÃO VIA BOTÕES (PV) -----------------------------------

def start_private(update: Update, context: CallbackContext):
    args = context.args
    if args and args[0].startswith('config_'):
        chat_id = args[0].split('_')[1]
        return config_group_menu(update, context, chat_id)
    
    keyboard = [
        [InlineKeyboardButton("👋 Configurar Boas-vindas", callback_data="config_welcome")],
        [InlineKeyboardButton("🛡️ Configurar Grupo", callback_data="select_group")]
    ]
    
    update.message.reply_text(
        "🛠 *Painel de Controle do Bot* 🛠\n\n"
        "Escolha o que deseja configurar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def select_group_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    # Aqui você implementaria a lógica para listar os grupos
    # Por simplicidade, vamos supor que temos acesso à lista de grupos
    groups = ["Grupo 1 (12345)", "Grupo 2 (67890)"]  # Exemplo
    
    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(group, callback_data=f"config_group_{group.split('(')[1][:-1]}")])
    
    query.edit_message_text(
        "📋 *Selecione um grupo para configurar* 📋",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def config_group_menu(update: Update, context: CallbackContext, chat_id: str):
    query = update.callback_query
    if query:
        query.answer()
        chat_id = query.data.split('_')[2]
    
    settings = get_group_settings(int(chat_id))
    
    keyboard = [
        [
            InlineKeyboardButton(f"🔗 Links: {'✅' if settings['block_links'] else '❌'}", callback_data=f"toggle_links_{chat_id}"),
            InlineKeyboardButton(f"↩️ Encaminhamentos: {'✅' if settings['block_forwards'] else '❌'}", callback_data=f"toggle_forwards_{chat_id}")
        ],
        [
            InlineKeyboardButton(f"🤖 Bots: {'✅' if settings['block_bots'] else '❌'}", callback_data=f"toggle_bots_{chat_id}"),
            InlineKeyboardButton(f"👋 Boas-vindas: {'✅' if settings['welcome_enabled'] else '❌'}", callback_data=f"toggle_welcome_{chat_id}")
        ],
        [InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")]
    ]
    
    text = (
        f"⚙️ *Configurações do Grupo* ⚙️\n\n"
        f"ID do Grupo: `{chat_id}`\n\n"
        f"Escolha o que deseja modificar:"
    )
    
    if query:
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
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
    
    config_group_menu(update, context, chat_id)

# SISTEMA DE MODERAÇÃO --------------------------------------------

def warn_user(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    target = get_target_user(update, context)
    if not target:
        return
    
    chat_id = str(update.effective_chat.id)
    reason = ' '.join(context.args) if context.args else "Sem motivo especificado"
    
    # Registrar advertência
    if chat_id not in warnings_data:
        warnings_data[chat_id] = {}
    if str(target.id) not in warnings_data[chat_id]:
        warnings_data[chat_id][str(target.id)] = []
    
    warnings_data[chat_id][str(target.id)].append(reason)
    save_data(DATABASE['WARNINGS_FILE'], warnings_data)
    
    # Verificar limite
    settings = get_group_settings(update.effective_chat.id)
    if len(warnings_data[chat_id][str(target.id)]) >= settings['max_warnings']:
        context.bot.ban_chat_member(update.effective_chat.id, target.id)
        text = f"🚫 {target.mention_html()} foi banido por atingir o limite de advertências!"
    else:
        text = (
            f"⚠️ {target.mention_html()} foi advertido.\n"
            f"Motivo: {reason}\n"
            f"Advertências: {len(warnings_data[chat_id][str(target.id)])}/{settings['max_warnings']}"
        )
    
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=ParseMode.HTML
    )
    delete_message(update)

def mute_user(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    target = get_target_user(update, context)
    if not target:
        return
    
    try:
        context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🔇 {target.mention_html()} foi silenciado.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Erro ao silenciar: {e}")

def ban_user(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    target = get_target_user(update, context)
    if not target:
        return
    
    try:
        context.bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚫 {target.mention_html()} foi banido.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Erro ao banir: {e}")

def get_target_user(update: Update, context: CallbackContext):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    
    if context.args:
        arg = context.args[0]
        if arg.startswith('@'):
            # Buscar por username
            pass  # Implementar lógica
        elif arg.isdigit():
            # Buscar por ID
            pass  # Implementar lógica
    
    update.message.reply_text("⚠️ Responda a mensagem do usuário ou use @username/ID")
    return None

# MAIN FUNCTION ---------------------------------------------------

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers de grupo
    dp.add_handler(MessageHandler(
        Filters.status_update.new_chat_members,
        bot_added_to_group
    ))
    
    # Handlers de comandos
    dp.add_handler(CommandHandler("start", start_private))
    dp.add_handler(CommandHandler("warn", warn_user))
    dp.add_handler(CommandHandler("mute", mute_user))
    dp.add_handler(CommandHandler("ban", ban_user))
    
    # Handlers de callback
    dp.add_handler(CallbackQueryHandler(select_group_menu, pattern='^select_group$'))
    dp.add_handler(CallbackQueryHandler(config_group_menu, pattern='^config_group_'))
    dp.add_handler(CallbackQueryHandler(toggle_setting, pattern='^toggle_'))
    
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