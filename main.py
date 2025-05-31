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

# Configuração de logging
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
mensagens_regras = carregar_dados(DATABASE['RULES_FILE'])
configuracoes_grupos = carregar_dados(DATABASE['GROUP_SETTINGS_FILE'])
advertencias = carregar_dados(DATABASE['WARNINGS_FILE'])

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

def obter_config_grupo(chat_id: int) -> Dict:
    return configuracoes_grupos.get(str(chat_id), {
        'bloquear_links': True,
        'bloquear_encaminhamentos': True,
        'limite_advertencias': 3,
        'boas_vindas_ativas': True
    })

# Handler de erros
def tratar_erro(update: Update, context: CallbackContext):
    logger.error(f"Erro: {context.error}", exc_info=True)
    if update and update.effective_message:
        update.effective_message.reply_text("⚠️ Ocorreu um erro. Tente novamente ou contate um admin.")

# COMANDOS DE GRUPO --------------------------------------------

def comando_ajuda(update: Update, context: CallbackContext):
    ajuda_texto = """
🤖 *COMANDOS DO BOT* 🤖

*Para todos:*
/help - Mostra esta mensagem
/rules - Mostra as regras do grupo
/report - Reportar um problema (responda a mensagem)

*Para admins:*
/warn [motivo] - Advertir usuário (responda a mensagem)
/mute [tempo] - Silenciar usuário (ex: /mute 1h)
/ban [motivo] - Banir usuário
/config - Configurações do grupo
/stats - Estatísticas do grupo
/clean - Limpar mensagens (ex: /clean 10)
"""
    update.message.reply_text(ajuda_texto, parse_mode=ParseMode.MARKDOWN)
    deletar_mensagem(update)

def mostrar_regras(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    regras = mensagens_regras.get(chat_id, BOT_CONFIG['MENSAGEM_REGRAS'])
    update.message.reply_text(regras, parse_mode=ParseMode.MARKDOWN)
    deletar_mensagem(update)

def reportar_usuario(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("⚠️ Responda a mensagem para reportar")
        return
    
    reporter = update.effective_user
    reported = update.message.reply_to_message.from_user
    motivo = ' '.join(context.args) if context.args else "Nenhum motivo fornecido"
    
    # Envia para os admins
    for admin_id in ADMIN_IDS:
        try:
            context.bot.send_message(
                chat_id=admin_id,
                text=f"⚠️ *REPORTE*\n\nUsuário: {reported.mention_html()}\nMotivo: {motivo}\nReporter: {reporter.mention_html()}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Erro ao enviar report: {e}")
    
    update.message.reply_text("✅ Reporte enviado aos administradores!")
    deletar_mensagem(update)

# ADMIN COMMANDS ------------------------------------------------

def advertir_usuario(update: Update, context: CallbackContext):
    if not eh_admin(update, context):
        return
    
    if not update.message.reply_to_message:
        update.message.reply_text("⚠️ Responda a mensagem do usuário para advertir")
        return
    
    alvo = update.message.reply_to_message.from_user
    chat_id = str(update.effective_chat.id)
    motivo = ' '.join(context.args) if context.args else "Sem motivo especificado"
    
    # Registrar advertência
    if chat_id not in advertencias:
        advertencias[chat_id] = {}
    if str(alvo.id) not in advertencias[chat_id]:
        advertencias[chat_id][str(alvo.id)] = []
    
    advertencias[chat_id][str(alvo.id)].append(motivo)
    salvar_dados(DATABASE['WARNINGS_FILE'], advertencias)
    
    # Verificar limite
    config = obter_config_grupo(update.effective_chat.id)
    if len(advertencias[chat_id][str(alvo.id)]) >= config['limite_advertencias']:
        context.bot.ban_chat_member(update.effective_chat.id, alvo.id)
        texto = f"🚫 {alvo.mention_html()} foi banido por atingir o limite de advertências!"
    else:
        texto = f"⚠️ {alvo.mention_html()} foi advertido. Motivo: {motivo}\nAdvertências: {len(advertencias[chat_id][str(alvo.id)])}/{config['limite_advertencias']}"
    
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=texto,
        parse_mode=ParseMode.HTML
    )
    deletar_mensagem(update)

def limpar_mensagens(update: Update, context: CallbackContext):
    if not eh_admin(update, context):
        return
    
    try:
        quantidade = int(context.args[0]) if context.args else 10
        quantidade = min(100, max(1, quantidade))  # Limite entre 1-100
        
        messages = []
        for msg in range(quantidade + 1):  # +1 para incluir o comando
            messages.append(update.message.message_id - msg)
        
        update.effective_chat.delete_messages(messages)
    except Exception as e:
        logger.error(f"Erro ao limpar mensagens: {e}")
        update.message.reply_text("⚠️ Erro ao limpar mensagens")

# MENSAGENS AUTOMÁTICAS -----------------------------------------

def enviar_boas_vindas(update: Update, context: CallbackContext):
    config = obter_config_grupo(update.effective_chat.id)
    if not config['boas_vindas_ativas']:
        return
    
    for novo_membro in update.message.new_chat_members:
        chat_id = str(update.effective_chat.id)
        mensagem = mensagens_boas_vindas.get(chat_id, BOT_CONFIG['MENSAGEM_BOAS_VINDAS']).format(
            nome=novo_membro.full_name,
            usuario=f"@{novo_membro.username}" if novo_membro.username else "",
            id=novo_membro.id
        )
        
        botoes = [
            InlineKeyboardButton("📜 Regras", callback_data="regras"),
            InlineKeyboardButton("📢 Canal", url=BOT_CONFIG['CANAL_PRINCIPAL'])
        ]
        
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=mensagem,
            reply_markup=InlineKeyboardMarkup([botoes]),
            parse_mode=ParseMode.HTML
        )

def filtrar_mensagens(update: Update, context: CallbackContext):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    config = obter_config_grupo(update.effective_chat.id)
    mensagem = update.effective_message
    
    # Verificar links
    if config['bloquear_links'] and not eh_admin(update, context):
        if mensagem.entities:
            for entity in mensagem.entities:
                if entity.type in ['url', 'text_link']:
                    deletar_mensagem(update)
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"⚠️ Links não são permitidos aqui, {update.effective_user.mention_html()}!",
                        parse_mode=ParseMode.HTML
                    )
                    return
    
    # Verificar encaminhamentos
    if config['bloquear_encaminhamentos'] and mensagem.forward_from_chat:
        if not eh_admin(update, context):
            deletar_mensagem(update)
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ Encaminhamentos não são permitidos, {update.effective_user.mention_html()}!",
                parse_mode=ParseMode.HTML
            )

# FUNÇÃO PRINCIPAL ----------------------------------------------

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Registrar handler de erros
    dp.add_error_handler(tratar_erro)

    # Configurar webhook no Render
    if RENDER_CONFIG['URL_WEBHOOK']:
        updater.start_webhook(
            listen=RENDER_CONFIG['HOST'],
            port=RENDER_CONFIG['PORTA'],
            url_path=TOKEN,
            webhook_url=f"{RENDER_CONFIG['URL_WEBHOOK']}/{TOKEN}",
            drop_pending_updates=True
        )
    else:
        updater.start_polling(drop_pending_updates=True)

    # Handlers de comandos
    dp.add_handler(CommandHandler("help", comando_ajuda))
    dp.add_handler(CommandHandler("rules", mostrar_regras))
    dp.add_handler(CommandHandler("report", reportar_usuario))
    dp.add_handler(CommandHandler("warn", advertir_usuario))
    dp.add_handler(CommandHandler("clean", limpar_mensagens))
    
    # Handlers de mensagens
    dp.add_handler(MessageHandler(
        Filters.status_update.new_chat_members,
        enviar_boas_vindas
    ))
    dp.add_handler(MessageHandler(
        Filters.text & Filters.chat_type.groups,
        filtrar_mensagens
    ))

    # Configurar comandos do bot
    comandos = [
        BotCommand("help", "Mostra todos os comandos"),
        BotCommand("rules", "Mostra as regras do grupo"),
        BotCommand("report", "Reportar um usuário"),
        BotCommand("warn", "Advertir um usuário (admin)"),
        BotCommand("clean", "Limpar mensagens (admin)")
    ]
    updater.bot.set_my_commands(comandos)

    logger.info("Bot iniciado com sucesso")
    updater.idle()

if __name__ == '__main__':
    main()