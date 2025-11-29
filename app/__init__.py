# app/__init__.py

from flask import Flask, render_template
from celery import Celery 
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from flask_mail import Mail
# Importa a classe Config do arquivo config.py
from .config import Config 


# ===============================================
# 1. INSTÂNCIAS GLOBAIS
# ===============================================

# 💡 Instância do Celery: Definida no nível superior
celery = Celery(__name__) 

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail() # Objeto Flask-Mail

def create_app(config_class=Config):
    # Cria a instância da aplicação Flask
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object(config_class) 
    
    # Garante que a pasta 'instance' existe
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Inicialização das Extensões com a App ---
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app) 
    
    
    # ===============================================
    # 2. CONFIGURAÇÃO DO CELERY COM CONTEXTO
    # ===============================================
    
    # Configura o Celery com as configurações do Flask (incluindo broker_url)
    celery.conf.update(app.config) # ESTA LINHA ESTÁ CORRETA
    
    # Cria uma classe base para tarefas que injeta o contexto da aplicação Flask
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            # Assegura que o db, mail, etc., funcionem dentro da tarefa Celery
            with app.app_context(): 
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    
    # ===============================================
    
    
    # =ACTERÍSTICAS
    # ===============================================
    # 💡 Importa o modelo User AQUI, após db.init_app(app)
    from app.models import User 
    
    @login_manager.user_loader
    def load_user(user_id):
        # Forma moderna de buscar pelo ID primário
        return db.session.get(User, int(user_id))

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # ===============================================
    # 4. REGISTRO DE BLUEPRINTS E ROTAS
    # ===============================================
    
    # Importa e registra o Blueprint de Autenticação
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    
    # Importa e registra o Blueprint de Serviços/Agendamento
    from app.services.routes import bp as services_bp 
    app.register_blueprint(services_bp, url_prefix='/services')
    
    # Rotas principais (RAIZ)
    @app.route('/')
    def index():
        return render_template('index.html', title='Início')

    # ===============================================
    # 5. REGISTRO DE COMANDOS CLI CUSTOMIZADOS
    # ===============================================
    
    # Importa e registra o módulo cli.py para comandos como 'flask init-db'
    try:
        from app import cli 
        
        # Registra a função de contexto de shell do módulo cli
        if hasattr(cli, 'make_shell_context'):
            app.shell_context_processor(cli.make_shell_context)
            
        # Registra comandos CLI (ex: flask create-admin)
        if hasattr(cli, 'cli_commands'):
            for command in cli.cli_commands:
                app.cli.add_command(command)
                
    except ImportError:
        pass # Ignora se cli.py ainda não estiver pronto

    return app