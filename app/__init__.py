# app/__init__.py

from flask import Flask, render_template # Removendo render_template daqui, não é usado na função
from celery import Celery 
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import os
from flask_mail import Mail
from .config import Config 
from flask_moment import Moment 

# ===============================================
# 1. INSTÂNCIAS GLOBAIS
# ===============================================

celery = Celery(
    __name__, 
    broker=Config.broker_url,
    result_backend=Config.result_backend 
)

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
mail = Mail() 
moment = Moment() # Inicialização da instância Moment

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
    migrate.init_app(app, db)
    login.init_app(app) 
    mail.init_app(app) 
    moment.init_app(app) # Inicializa Flask-Moment
    
    
    # ===============================================
    # 2. CONFIGURAÇÃO DO CELERY COM CONTEXTO
    # ===============================================
    
    # Configura o Celery com as configurações do Flask
    celery.conf.update(app.config)
    
    # Importar o módulo tasks AQUI garante que as tarefas sejam registradas,
    # quebrando o ciclo de importação e resolvendo o erro 'KeyError'.
    
    # Cria uma classe base para tarefas que injeta o contexto da aplicação Flask
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context(): 
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    
    # ===============================================
    # 3. CONFIGURAÇÃO DO FLASK-LOGIN (user_loader)
    # ===============================================
    
    # Importa o modelo User AQUI, após db.init_app(app)
    from app.models import User 
    
    @login.user_loader 
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    login.login_view = 'auth.login'
    login.login_message_category = 'info'

    # ===============================================
    # 4. REGISTRO DE BLUEPRINTS E ROTAS
    # ===============================================
    
    # Importa e registra o Blueprint de Autenticação
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    
    # Importa e registra o Blueprint de Serviços/Agendamento
    from app.services.routes import bp as services_bp 
    app.register_blueprint(services_bp, url_prefix='/services')
    
    # NOVO: Importa e registra o Blueprint Principal (main)
    # ESTE PASSO É CRUCIAL PARA ENCONTRAR main.terms
    from app.main.routes import bp as main_bp # Assumindo que você usa 'bp' em app/main/routes.py
    app.register_blueprint(main_bp)

    # REMOVIDO: @app.route('/') - A rota index deve estar em app/main/routes.py agora.


    # ===============================================
    # 5. REGISTRO DE COMANDOS CLI CUSTOMIZADOS
    # ===============================================
    
    try:
        from app import cli 
        
        if hasattr(cli, 'make_shell_context'):
            app.shell_context_processor(cli.make_shell_context)
            
        if hasattr(cli, 'cli_commands'):
            for command in cli.cli_commands:
                app.cli.add_command(command)
                
    except ImportError:
        pass 

    return app