from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from flask_mail import Mail
# Importa a classe Config do arquivo config.py (necessária para carregar SQLALCHEMY_DATABASE_URI)
from .config import Config 

# ===============================================
# 📌 INICIALIZAÇÃO DE EXTENSÕES (Fora da função)
# ===============================================

# Inicializa extensões fora da função para que possam ser importadas nos models e routes
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail() # Objeto Flask-Mail

def create_app(config_class=Config):
    # Cria a instância da aplicação Flask
    app = Flask(__name__, instance_relative_config=True)

    # --- Configuração ---
    # 🚨 CRÍTICO: Carrega TODAS as configurações (incluindo SQLALCHEMY_DATABASE_URI e MAIL_*) 
    # Isso deve ocorrer antes de init_app das extensões.
    app.config.from_object(config_class) 
    
    # Garante que a pasta 'instance' existe
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Inicialização das Extensões com a App ---
    # Agora as extensões encontram suas configurações em app.config
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app) # Conecta o Flask-Mail à instância do Flask
    
    # --- Configuração do User Loader para Flask-Login ---
    # Importa o modelo User aqui para evitar o problema de importação circular
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        # Forma moderna de buscar pelo ID primário
        return db.session.get(User, int(user_id))

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # ===============================================
    # 📌 REGISTRO DE BLUEPRINTS
    # ===============================================
    
    # Importa e registra o Blueprint de Autenticação
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    
    # Importa e registra o Blueprint de Serviços/Agendamento
    from app.services.routes import bp as services_bp 
    app.register_blueprint(services_bp, url_prefix='/services')
    
    # ===============================================
    # 📌 ROTAS PRINCIPAIS (RAIZ)
    # ===============================================
    
    @app.route('/')
    def index():
        return render_template('index.html', title='Início')

    # ===============================================
    # 📌 REGISTRO DE COMANDOS CLI CUSTOMIZADOS
    # ===============================================
    
    # Importa e registra o módulo cli.py para comandos como 'flask init-db'
    # Use try/except caso o arquivo cli.py ainda não exista
    try:
        from app import cli 
        for command in cli.cli_commands:
            app.cli.add_command(command)
    except ImportError:
        pass # Ignora se cli.py ainda não estiver pronto

    return app