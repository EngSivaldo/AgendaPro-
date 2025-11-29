# app/config.py

import os

# Define o caminho absoluto para o diretório RAIZ do projeto (scheduling_system)
# O os.pardir sobe um nível do diretório atual ('app')
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)) 

class Config:
    # --- Configurações Gerais ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'voce-nao-vai-adivinhar'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Configurações do Banco de Dados (DB) ---
    
    # 1. Pega o valor RAW do .env
    db_url_from_env = os.environ.get('DATABASE_URL')
    
    # 💡 CORREÇÃO APLICADA: DB AGORA ESTÁ DIRETAMENTE NA RAIZ (basedir)
    if db_url_from_env and db_url_from_env.startswith('sqlite:///'):
        # Se DATABASE_URL no .env for o caminho simplificado (ex: sqlite:///agendamentos.db), usamos.
        SQLALCHEMY_DATABASE_URI = db_url_from_env
    else:
        # Fallback: Força o caminho absoluto para o arquivo na RAIZ do projeto.
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'agendamentos.db')
    
    
    # --- Configurações do Flask-Mail ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.googlemail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    
    # 1. Lê as credenciais do ambiente
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # 2. Define o remetente padrão
    DEFAULT_SENDER_EMAIL = MAIL_USERNAME if MAIL_USERNAME else 'contato@sistema.com'
    MAIL_DEFAULT_SENDER = ('Sistema de Agendamento', DEFAULT_SENDER_EMAIL)
    
    
    # --- Configurações do Celery (CORREÇÃO AQUI) ---
    
    # URL do Broker (Fila de Mensagens). Lê do ambiente, ou usa o Redis local como fallback.
# --- Configurações do Celery (CORREÇÃO AQUI) ---
    
# Chave ANTIGA (Causa do erro): CELERY_BROKER_URL
# Chave NOVA (CORRETA): broker_url
broker_url = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0' # Mantenha a variável de ambiente antiga por segurança

# Chave ANTIGA (Causa do erro): CELERY_RESULT_BACKEND
# Chave NOVA (CORRETA): result_backend
result_backend = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0' # Mantenha a variável de ambiente antiga por segurança