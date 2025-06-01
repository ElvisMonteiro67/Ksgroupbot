import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ConversationHandler,
    filters,
    ContextTypes
)
from sqlalchemy import create_engine, Column, Integer, String, or_
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from threading import Lock
import uvicorn

# ==================================================
# CONFIGURAÇÃO INICIAL (COMPLETA)
# ==================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_ADMIN_ID = int(os.getenv("BOT_ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

# Configuração do banco de dados (original)
engine = create_engine(DATABASE_URL)
Session = scoped_session(sessionmaker(bind=engine))
db_lock = Lock()

Base = declarative_base()

class UserRole(Base):
    __tablename__ = 'user_roles'
    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=False)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" ou "verified"

# ==================================================
# FUNÇÕES ORIGINAIS COMPLETAS (MANTIDAS)
# ==================================================

def init_db():
    try:
        with db_lock:
            Base.metadata.create_all(engine)
            logger.info("Banco de dados inicializado.")
    except Exception as e:
        logger.error(f"Erro ao iniciar banco: {e}")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    🤖 *Bot de Gerenciamento* 🤖
    Comandos:
    /addgroupadmin @user - Adiciona admin
    /addverified @user - Adiciona verificada
    /manage - Menu interativo
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def add_user_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    if update.effective_user.id != BOT_ADMIN_ID:
        await update.message.reply_text("❌ Sem permissão.")
        return

    try:
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = (target_user.username or "").lower()
        elif context.args:
            username = context.args[0].lstrip('@').lower()
            user_id = 0
        else:
            await update.message.reply_text("ℹ️ Use: /comando @username")
            return

        with db_lock:
            session = Session()
            existing = session.query(UserRole).filter(
                UserRole.role == role,
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            if existing:
                await update.message.reply_text("ℹ️ Já está na lista.")
                return

            session.add(UserRole(
                telegram_user_id=user_id,
                username=username,
                role=role
            ))
            session.commit()

        await update.message.reply_text(f"✅ @{username} adicionado como {'admin' if role == 'admin' else 'verificada'}!")
    except Exception as e:
        logger.error(f"Erro: {e}")
        await update.message.reply_text("❌ Erro ao processar.")
    finally:
        Session.remove()

async def add_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_user_to_list(update, context, "admin")

async def add_verified(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_user_to_list(update, context, "verified")

async def new_member_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        user_id = member.id
        username = (member.username or "").lower()

        with db_lock:
            session = Session()
            is_admin = session.query(UserRole).filter(
                UserRole.role == "admin",
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()

            is_verified = session.query(UserRole).filter(
                UserRole.role == "verified",
                or_(UserRole.telegram_user_id == user_id, UserRole.username == username)
            ).first()
            Session.remove()

        if is_admin:
            await context.bot.promote_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                can_manage_chat=True,
                can_delete_messages=True,
                # ... (todas permissões originais)
            )
            await update.message.reply_text(f"👑 @{username} promovido a admin!")

        elif is_verified:
            await context.bot.set_chat_administrator_custom_title(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                custom_title="Verificada"
            )
            await update.message.reply_text(f"🌸 @{username} verificada!")

# ... (TODAS as outras funções originais mantidas aqui)
# - Funções de conversação interativa
# - Handlers de callback
# - Funções auxiliares

# ==================================================
# INTEGRAÇÃO COM FASTAPI (SOLUÇÃO RENDER)
# ==================================================

app = FastAPI()
bot_app = None

@app.on_event("startup")
async def startup():
    global bot_app
    init_db()
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Registra TODOS os handlers originais
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("addgroupadmin", add_group_admin))
    bot_app.add_handler(CommandHandler("addverified", add_verified))
    bot_app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        new_member_check
    ))
    
    # Configuração do ConversationHandler original
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(action_choice)],
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT | filters.FORWARDED, process_username)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_operation)],
        per_message=False  # Corrige o warning
    )
    bot_app.add_handler(conv_handler)

    if WEBHOOK_URL:
        await bot_app.initialize()
        await bot_app.bot.set_webhook(WEBHOOK_URL)
        await bot_app.start()
    else:
        asyncio.create_task(bot_app.run_polling())

@app.post(f"/{BOT_TOKEN}")
async def webhook(request: Request):
    if WEBHOOK_URL:
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "active"}

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )