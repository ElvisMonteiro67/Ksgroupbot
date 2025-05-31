import os
import logging
import json
from typing import Dict, Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    BotCommand,
    ParseMode,
    ChatMember
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

# Configuração de logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversação
CONFIGURANDO_MENSAGEM, CONFIGURANDO_REGRAS = range(2)

# Carregar dados
def carregar_dados(arquivo: str) -> Dict:
    try:
        with open(arquivo, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Salvar dados
def salvar_dados(arquivo: str, dados: Dict):
    try:
        with open(arquivo, 'w') as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}")

# Inicializar dados
mensagens_boas_vindas = carregar_dados(DATABASE['WELCOME_MSG_FILE'])
configuracoes_grupos = carregar_dados(DATABASE['GROUP_SETTINGS_FILE'])

# Funções auxiliares
def eh_admin(update: Update, context: CallbackContext) -> bool:
    usuario = update.effective_user
    if usuario.id in ADMIN_IDS:
        return True
    
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return False
    
    try:
        membro = context.bot.get_chat_member(chat.id, usuario.id)
        return membro.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]
    except Exception:
        return False

def deletar_mensagem(update: Update):
    try:
        update.message.delete()
    except Exception as e:
        logger.warning(f"Não foi possível deletar mensagem: {e}")

# Comandos administrativos
def advertir_usuario(update: Update, context: CallbackContext):
    if not eh_admin(update, context):
        return
    
    if not update.message.reply_to_message:
        update.message.reply_text("Responda a mensagem do usuário para advertir")
        return
    
    alvo = update.message.reply_to_message.from_user
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⚠️ {alvo.mention_html()} foi advertido(a)",
        parse_mode=ParseMode.HTML
    )
    deletar_mensagem(update)

def silenciar_usuario(update: Update, context: CallbackContext):
    if not eh_admin(update, context):
        return
    
    if not update.message.reply_to_message:
        update.message.reply_text("Responda a mensagem do usuário para silenciar")
        return
    
    alvo = update.message.reply_to_message.from_user
    try:
        context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=alvo.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🔇 {alvo.mention_html()} foi silenciado(a)",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Erro ao silenciar: {e}")
    deletar_mensagem(update)

def banir_usuario(update: Update, context: CallbackContext):
    if not eh_admin(update, context):
        return
    
    if not update.message.reply_to_message:
        update.message.reply_text("Responda a mensagem do usuário para banir")
        return
    
    alvo = update.message.reply_to_message.from_user
    try:
        context.bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=alvo.id
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚫 {alvo.mention_html()} foi banido(a)",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Erro ao banir: {e}")
    deletar_mensagem(update)

# Mensagem de boas-vindas
def enviar_boas_vindas(update: Update, context: CallbackContext):
    for novo_membro in update.message.new_chat_members:
        chat_id = str(update.effective_chat.id)
        mensagem = mensagens_boas_vindas.get(chat_id, BOT_CONFIG['DEFAULT_WELCOME']).format(
            nome=novo_membro.full_name,
            usuario=f"@{novo_membro.username}" if novo_membro.username else "",
            id=novo_membro.id
        )
        
        botoes = [
            InlineKeyboardButton("📜 Regras", callback_data="regras"),
            InlineKeyboardButton("📢 Canal", url="https://t.me/seucanal")
        ]
        
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=mensagem,
            reply_markup=InlineKeyboardMarkup([botoes]),
            parse_mode=ParseMode.HTML
        )

# Painel de configuração
def painel_controle(update: Update, context: CallbackContext):
    if update.effective_chat.type != 'private' or not eh_admin(update, context):
        return
    
    teclado = [
        [InlineKeyboardButton("👋 Configurar Boas-vindas", callback_data="config_boas_vindas")],
        [InlineKeyboardButton("⚙️ Configurações do Grupo", callback_data="config_grupo")],
        [InlineKeyboardButton("🛡️ Gerenciar Usuários", callback_data="gerenciar_usuarios")]
    ]
    
    update.message.reply_text(
        "🛠 *Painel de Controle do Bot* 🛠\n\n"
        "Escolha uma opção abaixo para configurar:",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode=ParseMode.MARKDOWN
    )

def configurar_boas_vindas(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "✍️ *Configurar Mensagem de Boas-vindas*\n\n"
        "Envie a nova mensagem. Você pode usar:\n"
        "- `{nome}`: Nome do usuário\n"
        "- `{usuario}`: @username\n"
        "- `{id}`: ID do usuário\n\n"
        "Exemplo:\n"
        "`Olá {nome}! Bem-vindo ao nosso grupo!`",
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIGURANDO_MENSAGEM

def salvar_boas_vindas(update: Update, context: CallbackContext):
    mensagens_boas_vindas[str(update.effective_chat.id)] = update.message.text
    salvar_dados(DATABASE['WELCOME_MSG_FILE'], mensagens_boas_vindas)
    update.message.reply_text("✅ Mensagem de boas-vindas salva com sucesso!")
    return ConversationHandler.END

# Função principal
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Configuração para Render
    if RENDER_CONFIG['WEBHOOK_URL']:
        updater.start_webhook(
            listen=RENDER_CONFIG['HOST'],
            port=RENDER_CONFIG['PORT'],
            url_path=TOKEN,
            webhook_url=f"{RENDER_CONFIG['WEBHOOK_URL']}/{TOKEN}"
        )
    else:
        updater.start_polling()

    # Handlers de comandos
    dp.add_handler(CommandHandler("start", painel_controle))
    dp.add_handler(CommandHandler("advertir", advertir_usuario))
    dp.add_handler(CommandHandler("silenciar", silenciar_usuario))
    dp.add_handler(CommandHandler("banir", banir_usuario))
    
    # Handlers de mensagens
    dp.add_handler(MessageHandler(
        Filters.status_update.new_chat_members,
        enviar_boas_vindas
    ))
    
    # Conversação para configuração
    dp.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(configurar_boas_vindas, pattern='^config_boas_vindas$')],
        states={
            CONFIGURANDO_MENSAGEM: [MessageHandler(Filters.text & ~Filters.command, salvar_boas_vindas)]
        },
        fallbacks=[]
    ))

    # Configurar comandos do bot
    updater.bot.set_my_commands([
        BotCommand("start", "Iniciar o painel de controle"),
        BotCommand("advertir", "Advertir um usuário (responda a mensagem)"),
        BotCommand("silenciar", "Silenciar um usuário (responda a mensagem)"),
        BotCommand("banir", "Banir um usuário (responda a mensagem)")
    ])

    logger.info("Bot iniciado e funcionando")
    updater.idle()

if __name__ == '__main__':
    main()