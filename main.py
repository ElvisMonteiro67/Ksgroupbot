import logging
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
import asyncio

# Configuração do logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class ForwardBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        
        # Handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("stats", self.stats))
        self.application.add_handler(CallbackQueryHandler(self.button))
        self.application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, self.handle_private_message))
        
        # Adiciona handler de erros
        self.application.add_error_handler(self.error_handler)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a message if possible."""
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        if update and isinstance(update, Update):
            try:
                await update.effective_message.reply_text(
                    "⚠️ Ocorreu um erro inesperado. Por favor, tente novamente mais tarde."
                )
            except Exception:
                pass

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Envia mensagem de boas-vindas quando o comando /start é acionado."""
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
        """Envia mensagem de ajuda."""
        await update.message.reply_text(
            "📝 Envie qualquer mensagem (texto, foto, vídeo, etc.) para mim no privado "
            "e eu a encaminharei para todos os grupos onde estou adicionado.\n\n"
            "Use /stats para ver estatísticas de alcance."
        )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra estatísticas de grupos e membros."""
        try:
            total_groups = 0
            total_members = 0
            group_list = []
            
            # Obtém todos os chats onde o bot está (usando uma abordagem alternativa)
            updates = await context.bot.get_updates()
            
            for update_data in updates:
                if hasattr(update_data, 'message') and update_data.message:
                    chat = update_data.message.chat
                    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                        try:
                            members_count = await context.bot.get_chat_members_count(chat.id)
                            total_members += members_count
                            total_groups += 1
                            group_list.append(f"{chat.title}: {members_count} membros")
                        except Exception as e:
                            logger.error(f"Erro ao obter contagem de membros para {chat.id}: {e}")
                            continue
            
            if total_groups == 0:
                await update.message.reply_text("🤖 Eu ainda não estou em nenhum grupo. Adicione-me a um grupo para começar!")
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
        """Processa callbacks de botões."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text=f"Ótimo! Agora você pode me adicionar ao grupo.")

    async def get_all_groups(self, context: ContextTypes.DEFAULT_TYPE):
        """Obtém todos os grupos onde o bot está adicionado."""
        groups = []
        updates = await context.bot.get_updates()
        
        for update_data in updates:
            if hasattr(update_data, 'message') and update_data.message:
                chat = update_data.message.chat
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    groups.append(chat)
        
        return groups

    async def handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Processa mensagens recebidas no privado e encaminha para os grupos."""
        try:
            user = update.effective_user
            message = update.effective_message
            
            # Verifica se a mensagem é uma resposta a outra mensagem
            if message.reply_to_message:
                await update.message.reply_text("⚠️ Por favor, envie mensagens diretamente, não como resposta.")
                return
            
            total_groups = 0
            total_members = 0
            forwarded_to = []
            
            # Obtém todos os grupos onde o bot está
            groups = await self.get_all_groups(context)
            
            if not groups:
                await update.message.reply_text(
                    "⚠️ Eu não estou em nenhum grupo ainda. Por favor, adicione-me a um grupo primeiro.\n\n"
                    "Use /start para ver como me adicionar ao seu grupo."
                )
                return
            
            # Encaminha a mensagem para cada grupo
            for group in groups:
                try:
                    # Encaminha a mensagem para o grupo
                    await message.forward(group.id)
                    
                    # Obtém estatísticas do grupo
                    members_count = await context.bot.get_chat_members_count(group.id)
                    total_members += members_count
                    total_groups += 1
                    forwarded_to.append(group.title)
                except Exception as e:
                    logger.error(f"Erro ao encaminhar mensagem para {group.id}: {e}")
                    continue
            
            # Cria mensagem de confirmação
            confirmation_msg = (
                f"✅ Mensagem encaminhada com sucesso para {total_groups} grupos, "
                f"alcançando um total de {total_membros} pessoas.\n\n"
                f"📋 Grupos:\n• " + "\n• ".join(forwarded_to)
            )
            
            # Envia confirmação para o usuário
            await update.message.reply_text(confirmation_msg)
        except Exception as e:
            logger.error(f"Erro ao processar mensagem privada: {e}")
            await update.message.reply_text("⚠️ Ocorreu um erro ao processar sua mensagem. Tente novamente mais tarde.")

    def run(self):
        """Inicia o bot."""
        self.application.run_polling()

if __name__ == "__main__":
    # Substitua pelo token do seu bot
    TOKEN = "7589679491:AAFwPkgGzhy0XC-b1fOvFfyWQqq9K0m86vs"
    
    bot = ForwardBot(TOKEN)
    bot.run()