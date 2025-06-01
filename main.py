import os
import logging
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode

# Configuração básica
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID'))  # ID do canal de origem
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]  # IDs dos administradores

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /start"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Você não tem permissão para usar este bot.")
        return
    
    await update.message.reply_text(
        "🤖 Bot de Encaminhamento Ativo!\n\n"
        "Este bot encaminha mensagens de um canal específico para todos os grupos "
        "onde ele é administrador.\n\n"
        "Comandos disponíveis:\n"
        "/list_groups - Lista todos os grupos onde o bot é admin"
    )

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os grupos onde o bot é admin"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return
    
    bot = context.bot
    try:
        # Obter todas as conversas onde o bot está
        chats = await bot.get_updates()
        group_list = []
        
        # Verificar cada chat para ver se é um grupo e o bot é admin
        for chat in chats:
            if chat.message and chat.message.chat.type in ['group', 'supergroup']:
                chat_id = chat.message.chat.id
                try:
                    member = await bot.get_chat_member(chat_id, bot.id)
                    if member.status in ['administrator', 'creator']:
                        group_info = await bot.get_chat(chat_id)
                        group_list.append(f"• {group_info.title} (ID: {chat_id})")
                except Exception as e:
                    logger.warning(f"Erro ao verificar grupo {chat_id}: {e}")
        
        if group_list:
            await update.message.reply_text(
                "📌 Grupos onde sou administrador:\n\n" + "\n".join(group_list)
            )
        else:
            await update.message.reply_text("Não sou administrador em nenhum grupo.")
            
    except Exception as e:
        logger.error(f"Erro ao listar grupos: {e}")
        await update.message.reply_text("Ocorreu um erro ao listar os grupos.")

async def forward_from_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Encaminha mensagens do canal para todos os grupos"""
    # Verificar se a mensagem é do canal correto
    if update.effective_chat.id != CHANNEL_ID:
        return
    
    bot = context.bot
    message = update.effective_message
    
    try:
        # Obter todas as conversas onde o bot está
        chats = await bot.get_updates()
        forwarded_count = 0
        
        for chat in chats:
            if chat.message and chat.message.chat.type in ['group', 'supergroup']:
                chat_id = chat.message.chat.id
                try:
                    # Verificar se o bot é admin no grupo
                    member = await bot.get_chat_member(chat_id, bot.id)
                    if member.status in ['administrator', 'creator']:
                        # Encaminhar a mensagem
                        await message.forward(chat_id)
                        forwarded_count += 1
                        logger.info(f"Mensagem encaminhada para o grupo {chat_id}")
                except Exception as e:
                    logger.warning(f"Erro ao encaminhar para grupo {chat_id}: {e}")
        
        logger.info(f"Mensagem encaminhada para {forwarded_count} grupos")
        
    except Exception as e:
        logger.error(f"Erro no encaminhamento: {e}")

def main():
    """Inicia o bot"""
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list_groups", list_groups))
    
    # Handler para mensagens do canal
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=CHANNEL_ID) & ~filters.COMMAND,
        forward_from_channel
    ))
    
    # Iniciar o bot
    app.run_polling()

if __name__ == '__main__':
    main()