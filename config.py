import os

# Configurações principais
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]

# Configurações do Render
RENDER_CONFIG = {
    'WEBHOOK_URL': os.getenv('RENDER_EXTERNAL_URL', ''),
    'PORT': int(os.getenv('PORT', 10000)),
    'HOST': '0.0.0.0'
}

# Configurações do Bot
BOT_CONFIG = {
    'DEFAULT_WELCOME_MSG': (
        "👋 Olá {name}! Bem-vindo ao grupo!\n\n"
        "📌 Por favor leia as regras\n"
        "🛡️ Respeite todos os membros"
    ),
    'DEFAULT_WELCOME_IMAGE': None,  # URL de imagem padrão
    'WELCOME_BUTTONS': [
        {"text": "📜 Regras", "url": ""},
        {"text": "📢 Canal", "url": "https://t.me/seucanal"}
    ]
}

# Configurações de segurança
SECURITY = {
    'MAX_WARNINGS': 3,
    'MUTE_DURATION': 3600  # 1 hora em segundos
}

# Armazenamento de dados
DATABASE = {
    'WELCOME_FILE': '/tmp/welcome_data.json',
    'GROUP_SETTINGS_FILE': '/tmp/group_settings.json',
    'WARNINGS_FILE': '/tmp/warnings.json'
}