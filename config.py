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
        "👋 Olá {nome}! Bem-vindo(a) ao grupo!\n\n"
        "📌 Por favor leia as regras abaixo\n"
        "🛡️ Respeite todos os membros\n"
        "✅ Participe e divirta-se!"
    ),
    'MENSAGEM_REGRAS': (
        "📜 *REGRAS DO GRUPO* 📜\n\n"
        "1️⃣ Respeite todos os membros\n"
        "2️⃣ Proibido spam/flood\n"
        "3️⃣ Não compartilhe conteúdo ilegal\n"
        "4️⃣ Mantenha discussões civilizadas\n\n"
        "⚠️ Infrações resultam em mute/ban"
    ),
    'CANAL_PRINCIPAL': "https://t.me/seucanal"
}

# Configurações de segurança
SECURITY = {
    'MAX_ADVERTENCIAS': 3,
    'TEMPO_MUTE_PADRAO': '1h'
}

# Armazenamento (usando /tmp no Render)
DATABASE = {
    'WELCOME_MSG_FILE': '/tmp/boas_vindas.json',
    'RULES_FILE': '/tmp/regras.json',
    'GROUP_SETTINGS_FILE': '/tmp/config_grupos.json',
    'WARNINGS_FILE': '/tmp/advertencias.json'
}