import os
import logging
import asyncio
import signal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatType
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

# Configuração do logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cria aplicação FastAPI
app = FastAPI()
bot_application = None

class ForwardBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.stop_event = asyncio.Event()
        
        # Inicializa dados persistentes
        self.application.bot_data.setdefault('known_chats', set())
        
        # Configura handlers
        self.setup_handlers()
        self.application.add_error_handler(self.error_handler)
    
    def setup_handlers(self):
        """Configura todos os handlers do bot"""
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("stats", self.stats),
            CallbackQueryHandler(self.button),
            MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, self.handle_private_message)
        ]
        for handler in handlers:
            self.application.add_handler(handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler do comando /start"""
        user = update.effective_user
        keyboard = [
            [
                InlineKeyboardButton(
                    "➕ Adicionar ao Grupo",
                    url=f"https://t.me/{context.bot.username}?startgroup=true&admin=post_messages+delete_messages+invite_users+restrict_members",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_html(
            rf"""
            Olá {user.mention_html()}! Eu sou um bot de encaminhamento de mensagens.

            ✨ <b>Como funciona:</b>
            1. Adicione-me a um ou mais grupos (botão abaixo)
            2. Envie a mensagem que deseja encaminhar para mim no privado
            3. Eu encaminho para todos os grupos onde estou adicionado
            
            📊 Após o encaminhamento, mostro quantas pessoas foram alcançadas (soma de todos os membros dos grupos).
            
            Clique no botão abaixo para me adicionar ao seu grupo com todas as permissões necessárias:
            """,
            reply_markup=reply_markup,
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler do comando /help"""
        await update.message.reply_text(
            "📝 Envie qualquer mensagem (texto, foto, vídeo, etc.) para mim no privado "
            "e eu a encaminharei para todos os grupos onde estou adicionado.\n\n"
            "Use /stats para ver estatísticas de alcance."
        )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler do comando /stats"""
        try:
            if not context.bot_data.get('known_chats'):
                await update.message.reply_text("🤖 Eu ainda não estou em nenhum grupo. Adicione-me a um grupo para começar!")
                return
            
            total_groups = 0
            total_members = 0
            group_list = []
            
            for chat_id in context.bot_data.get('known_chats', set()):
                try:
                    chat = await context.bot.get_chat(chat_id)
                    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                        members_count = await context.bot.get_chat_members_count(chat_id)
                        total_members += members_count
                        total_groups += 1
                        group_list.append(f"{chat.title}: {members_count} membros")
                except Exception as e:
                    logger.error(f"Erro ao obter info do chat {chat_id}: {e}")
                    continue
            
            if total_groups == 0:
                await update.message.reply_text("🤖 Não consegui acessar nenhum grupo no momento. Talvez eu tenha sido removido?")
            else:
                stats_msg = (
                    f"📊 Estatísticas de Alcance:\n"
                    f"• Grupos: {total_groups}\n"
                    f"• Total de membros: {total_members}\n\n"
                    f"📋 Lista de Grupos:\n" + "\n".join(group_list)
                )
                await update.message.reply_text(stats_msg)
        except Exception as e:
            logger.error(f"Erro no comando /stats: {e}")
            await update.message.reply_text("⚠️ Ocorreu um erro ao obter estatísticas. Tente novamente mais tarde.")

    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler de callbacks de botões"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Ótimo! Agora você pode me adicionar ao grupo.")

    async def handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Processa mensagens privadas para encaminhar aos grupos"""
        try:
            message = update.effective_message
            
            if message.reply_to_message:
                await update.message.reply_text("⚠️ Por favor, envie mensagens diretamente, não como resposta.")
                return
            
            if not context.bot_data.get('known_chats'):
                await update.message.reply_text(
                    "⚠️ Eu não estou registrado em nenhum grupo ainda. Adicione-me a um grupo e envie uma mensagem qualquer nele para eu me registrar."
                )
                return
            
            total_groups = 0
            total_members = 0
            forwarded_to = []
            failed_chats = []
            
            for chat_id in context.bot_data['known_chats']:
                try:
                    chat = await context.bot.get_chat(chat_id)
                    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
                        continue
                    
                    await message.forward(chat_id)
                    members_count = await context.bot.get_chat_members_count(chat_id)
                    total_members += members_count
                    total_groups += 1
                    forwarded_to.append(chat.title)
                except Exception as e:
                    logger.error(f"Erro ao processar chat {chat_id}: {e}")
                    failed_chats.append(chat_id)
                    continue
            
            if failed_chats:
                for chat_id in failed_chats:
                    context.bot_data['known_chats'].discard(chat_id)
                logger.info(f"Chats removidos por falha: {failed_chats}")
            
            if total_groups == 0:
                await update.message.reply_text(
                    "⚠️ Não consegui encaminhar para nenhum grupo. Verifique se ainda estou adicionado nos grupos."
                )
            else:
                confirmation_msg = (
                    f"✅ Mensagem encaminhada com sucesso para {total_groups} grupos, "
                    f"alcançando um total de {total_members} pessoas.\n\n"
                    f"📋 Grupos:\n• " + "\n• ".join(forwarded_to)
                )
                await update.message.reply_text(confirmation_msg)
        except Exception as e:
            logger.error(f"Erro ao processar mensagem privada: {e}")
            await update.message.reply_text("⚠️ Ocorreu um erro ao processar sua mensagem. Tente novamente mais tarde.")

    async def track_new_chat(self, chat_id, context):
        """Registra um novo chat na lista de chats conhecidos"""
        if 'known_chats' not in context.bot_data:
            context.bot_data['known_chats'] = set()
        if chat_id not in context.bot_data['known_chats']:
            context.bot_data['known_chats'].add(chat_id)
            logger.info(f"Novo chat registrado: {chat_id}")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler global de erros"""
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        if update and isinstance(update, Update):
            try:
                await update.effective_message.reply_text(
                    "⚠️ Ocorreu um erro inesperado. Por favor, tente novamente mais tarde."
                )
            except Exception:
                pass

async def initialize_bot():
    """Inicializa a aplicação do bot"""
    global bot_application
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    
    bot = ForwardBot(token)
    
    # Configura webhook se necessário
    if os.getenv("WEBHOOK_MODE", "false").lower() == "true":
        webhook_url = os.getenv("WEBHOOK_URL")
        secret_token = os.getenv("WEBHOOK_SECRET", "DEFAULT_SECRET")
        
        if not webhook_url:
            raise ValueError("WEBHOOK_URL não configurado")
        
        await bot.application.bot.set_webhook(
            url=webhook_url,
            secret_token=secret_token,
            drop_pending_updates=True
        )
        logger.info(f"Webhook configurado para {webhook_url}")
    
    return bot

@app.on_event("startup")
async def startup_event():
    """Evento de inicialização da aplicação FastAPI"""
    global bot_application
    try:
        bot_application = await initialize_bot()
        await bot_application.application.initialize()
        await bot_application.application.start()
        logger.info("Bot inicializado com sucesso")
    except Exception as e:
        logger.error(f"Falha ao inicializar bot: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Evento de desligamento da aplicação FastAPI"""
    if bot_application:
        await bot_application.application.stop()
        await bot_application.application.shutdown()
        logger.info("Bot desligado corretamente")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Endpoint para receber atualizações do Telegram"""
    if not bot_application:
        return PlainTextResponse(
            "Bot não inicializado",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        data = await request.json()
        update = Update.de_json(data, bot_application.application.bot)
        await bot_application.application.update_queue.put(update)
        return PlainTextResponse("OK")
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return PlainTextResponse(
            f"Erro: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/health")
async def health_check():
    """Endpoint para health checks"""
    return JSONResponse(
        {"status": "ok", "bot_initialized": bot_application is not None},
        status_code=status.HTTP_200_OK
    )

if __name__ == "__main__":
    # Modo de desenvolvimento (polling)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Defina TELEGRAM_BOT_TOKEN")
    
    bot = ForwardBot(token)
    bot.application.run_polling()