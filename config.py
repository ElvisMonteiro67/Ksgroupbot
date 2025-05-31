import os

# Configurações essenciais
TOKEN = os.getenv('TELEGRAM_TOKEN', '')  # Obtenha via variável de ambiente
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]  # Formato: "123,456"

# Configurações do Render
RENDER_CONFIG = {
    'WEBHOOK_URL': os.getenv('RENDER_EXTERNAL_URL', ''),
    'PORT': int(os.getenv('PORT', 8443)),
    'HOST': '0.0.0.0'
}

# Configurações do Bot
BOT_CONFIG = {
    'POLL_INTERVAL': 0.5,
    'TIMEOUT': 10,
    'DEFAULT_WELCOME': (
        "🌟 Bem-vindo(a), {name}! 🌟\n\n"
        "🔹 Respeite as regras\n"
        "🔹 Sem spam/flood\n"
        "🔹 Divirta-se!"
    ),
    'MAX_MESSAGE_LENGTH': 4000
}

# Configurações de Segurança
SECURITY = {
    'BLOCK_LINKS': True,
    'BLOCK_FORWARDS': True,
    'MAX_WARNINGS': 3
}

# Database (Render não persiste arquivos, então usamos JSON temporário)
DATABASE = {
    'WELCOME_MSG_FILE': '/tmp/welcome_messages.json',
    'GROUP_SETTINGS_FILE': '/tmp/group_settings.json'
}