import os
import json
from typing import Dict, Any

class Database:
    def __init__(self, data_dir: str = 'data'):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Estrutura padrão dos arquivos
        self.default_data = {
            'welcome_data': {
                'messages': {},
                'media': {},
                'buttons': {}
            },
            'group_settings': {},
            'warnings': {},
            'users': {}
        }

    def _get_file_path(self, data_type: str) -> str:
        """Retorna o caminho completo do arquivo de dados"""
        return os.path.join(self.data_dir, f'{data_type}.json')

    def _load_data(self, data_type: str) -> Dict:
        """Carrega dados de um arquivo específico"""
        file_path = self._get_file_path(data_type)
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self.default_data.get(data_type, {})

    def _save_data(self, data_type: str, data: Dict):
        """Salva dados em um arquivo específico"""
        file_path = self._get_file_path(data_type)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    # Métodos para welcome_data
    def get_welcome_message(self, chat_id: int) -> Dict:
        data = self._load_data('welcome_data')
        return data['messages'].get(str(chat_id), None)

    def save_welcome_message(self, chat_id: int, message: str):
        data = self._load_data('welcome_data')
        data['messages'][str(chat_id)] = message
        self._save_data('welcome_data', data)

    # Métodos para group_settings
    def get_group_settings(self, chat_id: int) -> Dict:
        return self._load_data('group_settings').get(str(chat_id), {})

    def save_group_settings(self, chat_id: int, settings: Dict):
        data = self._load_data('group_settings')
        data[str(chat_id)] = settings
        self._save_data('group_settings', data)

    # Métodos para warnings
    def get_warnings(self, chat_id: int, user_id: int) -> List[Dict]:
        data = self._load_data('warnings')
        return data.get(str(chat_id), {}).get(str(user_id), [])

    def add_warning(self, chat_id: int, user_id: int, reason: str):
        data = self._load_data('warnings')
        if str(chat_id) not in data:
            data[str(chat_id)] = {}
        if str(user_id) not in data[str(chat_id)]:
            data[str(chat_id)][str(user_id)] = []
        
        data[str(chat_id)][str(user_id)].append({
            'reason': reason,
            'timestamp': int(time.time())
        })
        self._save_data('warnings', data)

    # Métodos para users
    def get_user(self, user_id: int) -> Dict:
        return self._load_data('users').get(str(user_id), {})

    def save_user(self, user_id: int, user_data: Dict):
        data = self._load_data('users')
        data[str(user_id)] = user_data
        self._save_data('users', data)