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
CONFIG_GROUP_SETTINGS = 1

class GroupManager:
    def __init__(self, bot, db, config):
        self.bot = bot
        self.db = db
        self.config = config
        self.chats = {}
        self.users = {}
        
    def is_chat_allowed(self, chat_id):
        """Verifica se o chat está na whitelist/blacklist"""
        return True  # Implementar lógica conforme necessário
    
    def load_chat_data(self, chat_id):
        """Carrega dados do chat"""
        if chat_id not in self.chats:
            self.chats[chat_id] = self.db.load_chat(chat_id)
        return self.chats[chat_id]
    
    def load_user_data(self, user_id):
        """Carrega dados do usuário"""
        if user_id not in self.users:
            self.users[user_id] = self.db.load_user(user_id)
        return self.users[user_id]

# Funções principais adaptadas
async def handle_message(update: Update, context: CallbackContext):
    """Processa mensagens recebidas"""
    try:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        
        # Verifica se o chat é permitido
        if not context.bot_data['group_manager'].is_chat_allowed(chat.id):
            return
        
        # Carrega dados do chat e usuário
        chat_data = context.bot_data['group_manager'].load_chat_data(chat.id)
        user_data = context.bot_data['group_manager'].load_user_data(user.id)
        
        # Verifica se é um novo grupo
        if chat.type in ['group', 'supergroup']:
            if (update.message.new_chat_members and 
                any(member.id == context.bot.id for member in update.message.new_chat_members)):
                await handle_bot_added(update, context, chat, user)
                return
        
        # Processa comandos de moderação
        if message.text and message.text.startswith('/'):
            await handle_commands(update, context, chat_data, user_data)
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

async def handle_bot_added(update: Update, context: CallbackContext, chat, user):
    """Lida com a adição do bot a um grupo"""
    keyboard = [
        [InlineKeyboardButton("⚙️ Configurar Grupo", 
            callback_data=f"config_group_{chat.id}")],
        [InlineKeyboardButton("📜 Ver Comandos", callback_data="show_help")]
    ]
    
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"🤖 *Obrigado por me adicionar ao grupo {chat.title}!*\n\n"
             "Eu sou um bot de moderação completo. Use os botões abaixo para me configurar.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Salva informações do grupo
    context.bot_data['group_manager'].chats[chat.id] = {
        'id': chat.id,
        'title': chat.title,
        'type': chat.type,
        'settings': {
            'block_links': True,
            'block_forwards': True,
            'block_bots': True,
            'welcome_enabled': True
        }
    }

async def handle_commands(update: Update, context: CallbackContext, chat_data, user_data):
    """Processa comandos recebidos"""
    message = update.effective_message
    command = message.text.split()[0][1:].lower()
    
    if command == 'start':
        await start_command(update, context)
    elif command == 'warn':
        await warn_user(update, context)
    elif command == 'mute':
        await mute_user(update, context)
    elif command == 'ban':
        await ban_user(update, context)
    elif command == 'config':
        await config_group_menu(update, context)

# Funções de moderação (adaptadas do código anterior)
async def warn_user(update: Update, context: CallbackContext):
    """Adverte um usuário"""
    # Implementação similar à versão anterior
    pass

async def mute_user(update: Update, context: CallbackContext):
    """Silencia um usuário"""
    # Implementação similar à versão anterior
    pass

async def ban_user(update: Update, context: CallbackContext):
    """Bane um usuário"""
    # Implementação similar à versão anterior
    pass

# Funções de configuração
async def config_group_menu(update: Update, context: CallbackContext):
    """Mostra menu de configuração do grupo"""
    query = update.callback_query
    if query:
        chat_id = int(query.data.split('_')[2])
    else:
        chat_id = update.effective_chat.id
    
    try:
        chat = await context.bot.get_chat(chat_id)
        settings = context.bot_data['group_manager'].load_chat_data(chat_id)['settings']
        
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
            ]
        ]
        
        text = f"⚙️ *Configurações do {chat.title}* ⚙️\n\nSelecione uma opção:"
        
        if query:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Erro no menu de configuração: {e}")

def main():
    """Função principal"""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Inicializa o gerenciador de grupos
    db = Database()  # Classe fictícia - implemente conforme necessário
    updater.bot_data['group_manager'] = GroupManager(updater.bot, db, BOT_CONFIG)
    
    # Handlers
    dp.add_handler(MessageHandler(Filters.all, handle_message))
    dp.add_handler(CallbackQueryHandler(config_group_menu, pattern='^config_group_'))
    
    # Comandos
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("warn", warn_user))
    dp.add_handler(CommandHandler("mute", mute_user))
    dp.add_handler(CommandHandler("ban", ban_user))
    dp.add_handler(CommandHandler("config", config_group_menu))
    
    # Inicia o bot
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