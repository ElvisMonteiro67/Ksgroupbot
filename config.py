import os

# Configurações essenciais
TOKEN = os.getenv('TOKEN_BOT')
ADMIN_IDS = [int(id) for id in os.getenv('ADMINS', '').split(',') if id]

# Configurações do Render
RENDER_CONFIG = {
    'URL_WEBHOOK': os.getenv('URL_EXTERNA_RENDER', ''),
    'PORTA': int(os.getenv('PORTA', 10000)),
    'HOST': '0.0.0.0'
}

# Mensagens padrão
BOT_CONFIG = {
    'MENSAGEM_BOAS_VINDAS': (
        "👋 Olá {nome}! Bem-vindo(a)!\n\n"
        "📌 Leia as regras do grupo\n"
        "🛡️ Respeite todos os membros\n"
        "✅ Divirta-se!"
    )
}

# Configurações de segurança
SECURITY = {
    'BLOQUEAR_LINKS': True,
    'MAX_ADVERTENCIAS': 3
}

# Armazenamento (usando /tmp no Render)
DATABASE = {
    'WELCOME_MSG_FILE': '/tmp/boas_vindas.json',
    'GROUP_SETTINGS_FILE': '/tmp/config_grupos.json'
}