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

async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem de boas-vindas quando alguém inicia o bot"""
    welcome_text = (
        "🤖 *Bem-vindo ao Forward Bot!*\n\n"
        "Eu sou um bot que encaminha automaticamente mensagens de um canal específico "
        "para todos os grupos onde sou administrador.\n\n"
        "*Como usar:*\n"
        "1. Me adicione como administrador em seus grupos\n"
        "2. Envie mensagens no canal configurado\n"
        "3. Eu automaticamente encaminharei para todos os grupos\n\n"
        "📌 *Comandos disponíveis para administradores:*\n"
        "/start - Mostra esta mensagem\n"
        "/list_groups - Lista todos os grupos onde sou admin\n\n"
        "⚠️ Apenas administradores podem usar comandos."
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os grupos onde o bot é admin"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ Você não tem permissão para usar este comando.")
        return
    
    bot = context.bot
    try:
        # Obter todas as conversas onde o bot está
        updates = await bot.get_updates()
        group_list = []
        
        # Verificar cada chat para ver se é um grupo e o bot é admin
        seen_groups = set()
        for update in updates:
            if update.message and update.message.chat.type in ['group', 'supergroup']:
                chat_id = update.message.chat.id
                if chat_id not in seen_groups:
                    seen_groups.add(chat_id)
                    try:
                        member = await bot.get_chat_member(chat_id, bot.id)
                        if member.status in ['administrator', 'creator']:
                            group_info = await bot.get_chat(chat_id)
                            group_list.append(f"• {group_info.title} (ID: {chat_id})")
                    except Exception as e:
                        logger.warning(f"Erro ao verificar grupo {chat_id}: {e}")
        
        if group_list:
            response = (
                "📌 *Grupos onde sou administrador:*\n\n" + 
                "\n".join(group_list) + 
                "\n\nTotal: " + str(len(group_list)) + " grupos"
            await update.message.reply_text(
                response,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("ℹ️ Não sou administrador em nenhum grupo.")
            
    except Exception as e:
        logger.error(f"Erro ao listar grupos: {e}")
        await update.message.reply_text("❌ Ocorreu um erro ao listar os grupos.")

async def forward_from_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Encaminha mensagens do canal para todos os grupos"""
    # Verificar se a mensagem é do canal correto
    if update.effective_chat.id != CHANNEL_ID:
        return
    
    bot = context.bot
    message = update.effective_message
    
    try:
        # Obter todas as conversas onde o bot está
        updates = await bot.get_updates()
        forwarded_count = 0
        seen_groups = set()
        
        for update in updates:
            if update.message and update.message.chat.type in ['group', 'supergroup']:
                chat_id = update.message.chat.id
                if chat_id not in seen_groups:
                    seen_groups.add(chat_id)
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

async def post_init(application: ApplicationBuilder):
    """Função executada após o bot iniciar"""
    await application.bot.set_my_commands([
        ("start", "Mostra informações sobre o bot"),
        ("list_groups", "Lista grupos onde sou admin (apenas para administradores)"),
    ])
    logger.info("Bot iniciado e comandos configurados")

def main():
    """Inicia o bot"""
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()
    
    # Handlers
    app.add_handler(CommandHandler("start", send_welcome_message))
    app.add_handler(CommandHandler("list_groups", list_groups))
    
    # Handler para mensagens do canal
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=CHANNEL_ID) & ~filters.COMMAND,
        forward_from_channel
    ))
    
    # Iniciar o bot
    logger.info("Iniciando o bot...")
    app.run_polling()

if __name__ == '__main__':
    main()