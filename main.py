import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
from database import (
    init_db,
    add_verified_user,
    remove_verified_user,
    is_user_verified,
    get_all_groups,
    add_group,
    remove_group,
    get_source_channel,
    set_source_channel,
)

# Configuração básica
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializa o banco de dados
init_db()

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem de boas-vindas com botões"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Divulgar na KS Agência", callback_data="divulgar")],
        [InlineKeyboardButton("Sobre o bot", callback_data="sobre")],
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("Admin Painel", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 Olá {user.first_name}!\n\n"
        "Eu sou um bot de encaminhamento de conteúdo. Aqui está o que posso fazer:\n"
        "✅ Encaminhar publicações do canal vinculado para todos os grupos\n"
        "✅ Permitir que usuários verificados divulguem na rede KS Agência\n"
        "✅ Manter um banco de dados de usuários verificados\n\n"
        "Use os botões abaixo para interagir comigo!"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula os callbacks dos botões"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "divulgar":
        if is_user_verified(query.from_user.username):
            await query.edit_message_text(
                "✅ Você é um usuário verificado!\n"
                "Por favor, encaminhe a mensagem que deseja divulgar na rede KS Agência.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Voltar", callback_data="back")]
                ])
            )
            context.user_data["awaiting_forward"] = True
        else:
            await query.edit_message_text(
                "⚠️ Você não está na lista de usuários verificados.\n"
                "Entre em contato com um administrador para ser verificado.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Voltar", callback_data="back")]
                ])
            )
    
    elif query.data == "sobre":
        await query.edit_message_text(
            "🤖 Sobre este bot:\n\n"
            "Este bot foi desenvolvido para:\n"
            "1. Encaminhar automaticamente publicações de um canal específico para todos os grupos configurados\n"
            "2. Gerenciar uma rede de divulgação chamada 'KS Agência'\n"
            "3. Permitir que usuários verificados compartilhem conteúdo na rede\n\n"
            "Desenvolvido com Python e python-telegram-bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Voltar", callback_data="back")]
            ])
        )
    
    elif query.data == "admin":
        if query.from_user.id in ADMIN_IDS:
            await show_admin_panel(query)
        else:
            await query.edit_message_text(
                "⚠️ Acesso negado. Você não é um administrador.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Voltar", callback_data="back")]
                ])
            )
    
    elif query.data == "back":
        await start(update, context)
    
    elif query.data.startswith("admin_"):
        if query.from_user.id in ADMIN_IDS:
            await handle_admin_actions(query, context)
        else:
            await query.edit_message_text("⚠️ Acesso negado.")

async def show_admin_panel(query):
    """Mostra o painel de administração"""
    keyboard = [
        [InlineKeyboardButton("Gerenciar Usuários Verificados", callback_data="admin_manage_users")],
        [InlineKeyboardButton("Gerenciar Grupos", callback_data="admin_manage_groups")],
        [InlineKeyboardButton("Configurar Canal de Origem", callback_data="admin_set_channel")],
        [InlineKeyboardButton("Voltar", callback_data="back")]
    ]
    
    await query.edit_message_text(
        "🛠 Painel de Administração\n\n"
        "Escolha uma opção:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_admin_actions(query, context):
    """Manipula ações do painel de admin"""
    action = query.data.split("_")[1]
    
    if action == "manage_users":
        await manage_users(query, context)
    elif action == "manage_groups":
        await manage_groups(query)
    elif action == "set_channel":
        await query.edit_message_text(
            "Por favor, encaminhe uma mensagem do canal que será a fonte das publicações.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancelar", callback_data="admin")]
            ])
        )
        context.user_data["awaiting_channel"] = True

async def manage_users(query, context):
    """Mostra interface para gerenciar usuários verificados"""
    keyboard = [
        [InlineKeyboardButton("Adicionar Usuário", callback_data="admin_add_user")],
        [InlineKeyboardButton("Remover Usuário", callback_data="admin_remove_user")],
        [InlineKeyboardButton("Voltar", callback_data="admin")]
    ]
    
    await query.edit_message_text(
        "👥 Gerenciar Usuários Verificados\n\n"
        "Escolha uma opção:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def manage_groups(query):
    """Mostra interface para gerenciar grupos"""
    groups = get_all_groups()
    groups_text = "\n".join([f"🟢 {group}" for group in groups]) if groups else "Nenhum grupo cadastrado."
    
    keyboard = [
        [InlineKeyboardButton("Adicionar Grupo", callback_data="admin_add_group")],
        [InlineKeyboardButton("Remover Grupo", callback_data="admin_remove_group")],
        [InlineKeyboardButton("Voltar", callback_data="admin")]
    ]
    
    await query.edit_message_text(
        f"👥 Gerenciar Grupos\n\nGrupos ativos:\n{groups_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula mensagens recebidas"""
    user_data = context.user_data
    
    if user_data.get("awaiting_channel"):
        if update.message.forward_from_chat:
            channel_id = update.message.forward_from_chat.id
            set_source_channel(channel_id)
            await update.message.reply_text(
                f"Canal de origem definido como: {update.message.forward_from_chat.title}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Voltar ao Painel", callback_data="admin")]
                ])
            )
            user_data["awaiting_channel"] = False
        else:
            await update.message.reply_text(
                "Por favor, encaminhe uma mensagem de um canal válido.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancelar", callback_data="admin")]
                ])
            )
    
    elif user_data.get("awaiting_forward") and is_user_verified(update.effective_user.username):
        # Encaminha a mensagem para o canal e grupos
        source_channel = get_source_channel()
        groups = get_all_groups()
        
        if source_channel and groups:
            try:
                # Encaminha para o canal
                await context.bot.forward_message(
                    chat_id=source_channel,
                    from_chat_id=update.message.chat_id,
                    message_id=update.message.message_id
                )
                
                # Encaminha para todos os grupos com botão de origem
                for group in groups:
                    try:
                        forwarded_msg = await context.bot.forward_message(
                            chat_id=group,
                            from_chat_id=update.message.chat_id,
                            message_id=update.message.message_id
                        )
                        
                        # Adiciona botão com o canal de origem
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("Fonte", url=f"https://t.me/{context.bot.get_chat(source_channel).username}")]
                        ])
                        
                        await context.bot.send_message(
                            chat_id=group,
                            text="🔍 Fonte da publicação:",
                            reply_to_message_id=forwarded_msg.message_id,
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        logger.error(f"Erro ao enviar para grupo {group}: {e}")
                
                await update.message.reply_text(
                    "✅ Sua publicação foi compartilhada com sucesso!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Voltar", callback_data="back")]
                    ])
                )
            except Exception as e:
                logger.error(f"Erro ao encaminhar mensagem: {e}")
                await update.message.reply_text(
                    "❌ Ocorreu um erro ao compartilhar sua publicação.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Voltar", callback_data="back")]
                    ])
                )
        else:
            await update.message.reply_text(
                "❌ Canal de origem ou grupos não configurados.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Voltar", callback_data="back")]
                ])
            )
        
        user_data["awaiting_forward"] = False
    
    elif update.message.chat.type == "private" and not user_data.get("awaiting_forward"):
        await start(update, context)

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula novas postagens no canal de origem"""
    source_channel = get_source_channel()
    if update.channel_post.chat.id == source_channel:
        groups = get_all_groups()
        
        for group in groups:
            try:
                forwarded_msg = await context.bot.forward_message(
                    chat_id=group,
                    from_chat_id=source_channel,
                    message_id=update.channel_post.message_id
                )
                
                # Adiciona botão com o canal de origem
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Fonte", url=f"https://t.me/{context.bot.get_chat(source_channel).username}")]
                ])
                
                await context.bot.send_message(
                    chat_id=group,
                    text="🔍 Fonte da publicação:",
                    reply_to_message_id=forwarded_msg.message_id,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Erro ao encaminhar para grupo {group}: {e}")

def main():
    """Inicia o bot"""
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))
    
    # Inicia o bot
    application.run_polling()

if __name__ == "__main__":
    main()