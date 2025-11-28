# app/config.py

import os

# Define o diretório base como sendo o diretório onde o config.py está (a pasta 'app')
basedir = os.path.abspath(os.path.dirname(__file__))
# O diretório raiz do projeto (um nível acima de 'app')
project_root = os.path.join(basedir, os.pardir) 

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-muito-segura'
    
    # Define o caminho do banco de dados: pasta 'instance' DENTRO do diretório raiz
    # Ex: C:\Users\sival\scheduling_system\instance\agendamentos.db
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(project_root, 'instance', 'agendamentos.db')
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TIMEZONE = 'America/Sao_Paulo'