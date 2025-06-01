from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# COLOQUE AQUI OS NOVOS VALORES QUE VOCÊ OBTEVE
API_ID = 20261016  # Substitua pelo seu API_ID real
API_HASH = '23240f2a7b2e08a801e8a5b3d787fc9e'  # Substitua pelo seu API_HASH real

print("""
1. Vá para https://my.telegram.org/auth
2. Faça login com seu número (+5547992592171)
3. Crie um novo aplicativo em 'API development tools'
4. Obtenha o API_ID e API_HASH
5. Cole esses valores no script acima
""")

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n\nCONECTANDO AO TELEGRAM...")
    client.start(phone=lambda: input("Digite seu número com código do país (+5547992592171): "))
    
    session_string = client.session.save()
    print("\n\nSUA STRING DE SESSÃO (GUARDE ESTA INFORMAÇÃO):")
    print("----------------------------------")
    print(session_string)
    print("----------------------------------")
    print("\nGuarde esta string em SESSION_STRING no arquivo .env")
    
    # Envia a string para o seu chat "Saved Messages"
    client.send_message('me', f'Sua string de sessão:\n\n{session_string}')