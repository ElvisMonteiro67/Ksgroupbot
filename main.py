import os
import logging
import time  # Adicionei esta linha
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Configuração básica
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('SOURCE_CHANNEL_ID')  # ID do canal de origem (com @ ou numérico)
ADMIN_ID = os.getenv('ADMIN_USER_ID')  # Seu ID de usuário para comandos admin

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dicionário para armazenar temporariamente os grupos (simulando DB)
groups_cache = {
    'group_ids': set(),
    'last_update': 0
}

def start(update: Update, context: CallbackContext) -> None:
    """Envia mensagem de boas-vindas quando o comando /start é recebido."""
    update.message.reply_text('🤖 Bot de encaminhamento ativo! Adicione-me a grupos como admin para funcionar.')

def update_groups_list(context: CallbackContext) -> None:
    """Atualiza a lista de grupos onde o bot está presente."""
    bot = context.bot
    try:
        # Obtém todas as conversas onde o bot está presente
        updates = bot.get_updates()
        
        group_ids = set()
        for update in updates:
            if update.message and update.message.chat.type in ['group', 'supergroup']:
                group_ids.add(update.message.chat.id)
            elif update.channel_post and update.channel_post.chat.type == 'channel':
                # Para canais, verificar se o bot é admin
                chat_member = bot.get_chat_member(update.channel_post.chat.id, bot.id)
                if chat_member.status in ['administrator', 'creator']:
                    group_ids.add(update.channel_post.chat.id)
        
        # Adiciona também os grupos obtidos via getUpdates
        for chat in bot.get_updates(limit=100):
            if chat.message and chat.message.chat.type in ['group', 'supergroup']:
                group_ids.add(chat.message.chat.id)
        
        groups_cache['group_ids'] = group_ids
        groups_cache['last_update'] = time.time()
        logger.info(f"Lista de grupos atualizada. Total: {len(group_ids)}")
    except Exception as e:
        logger.error(f"Erro ao atualizar lista de grupos: {e}")

def forward_from_channel(context: CallbackContext) -> None:
    """Verifica mensagens do canal e encaminha para os grupos."""
    bot = context.bot
    
    try:
        # Atualiza a lista de grupos periodicamente
        if time.time() - groups_cache['last_update'] > 3600:  # 1 hora
            update_groups_list(context)
        
        # Obtém as últimas mensagens do canal
        messages = bot.get_chat_history(CHANNEL_ID, limit=1)
        
        for message in messages:
            # Verifica se a mensagem já foi processada (simples mecanismo de cache)
            if hasattr(message, 'message_id') and not getattr(message, 'is_forwarded', False):
                # Cria botão com o nome do canal
                channel = bot.get_chat(CHANNEL_ID)
                keyboard = [[InlineKeyboardButton(f"📢 {channel.title}", url=f"https://t.me/{channel.username}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Encaminha para todos os grupos
                for group_id in groups_cache['group_ids']:
                    try:
                        if message.text:
                            bot.send_message(
                                chat_id=group_id,
                                text=message.text,
                                reply_markup=reply_markup
                            )
                        elif message.photo:
                            bot.send_photo(
                                chat_id=group_id,
                                photo=message.photo[-1].file_id,
                                caption=message.caption,
                                reply_markup=reply_markup
                            )
                        elif message.video:
                            bot.send_video(
                                chat_id=group_id,
                                video=message.video.file_id,
                                caption=message.caption,
                                reply_markup=reply_markup
                            )
                        elif message.document:
                            bot.send_document(
                                chat_id=group_id,
                                document=message.document.file_id,
                                caption=message.caption,
                                reply_markup=reply_markup
                            )
                        # Marca como encaminhada
                        message.is_forwarded = True
                        logger.info(f"Mensagem {message.message_id} encaminhada para o grupo {group_id}")
                    except Exception as e:
                        logger.error(f"Erro ao encaminhar para grupo {group_id}: {e}")
                        # Remove grupo da lista se houver erro (pode ter sido removido)
                        groups_cache['group_ids'].discard(group_id)
    except Exception as e:
        logger.error(f"Erro no forward_from_channel: {e}")

def main() -> None:
    """Inicia o bot."""
    # Cria o Updater e passa o token do bot
    updater = Updater(TOKEN)

    # Obtém o dispatcher para registrar handlers
    dispatcher = updater.dispatcher

    # Comandos
    dispatcher.add_handler(CommandHandler("start", start))

    # Inicia o job para encaminhar mensagens periodicamente
    job_queue = updater.job_queue
    job_queue.run_repeating(forward_from_channel, interval=300.0, first=10.0)  # Verifica a cada 5 minutos

    # Inicia o Bot
    updater.start_polling()

    # Roda o bot até que Ctrl-C seja pressionado
    updater.idle()

if __name__ == '__main__':
    main()