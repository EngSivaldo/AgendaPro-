from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from flask_login import login_required # Import necessário

# Inicializa extensões fora da função para que possam ser importadas nos models
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(test_config=None):
    # Cria a instância da aplicação Flask
    app = Flask(__name__, instance_relative_config=True)

    # --- Configuração ---
    app.config.from_mapping(
        SECRET_KEY='dev', # Mude isto em produção!
        # Configura o caminho do banco de dados SQLite
        SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(app.instance_path, 'agendamentos.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False
    )
    
    if test_config is None:
        # Carrega a configuração da instância se existir
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Carrega a configuração de teste
        app.config.from_mapping(test_config)

    # Garante que a pasta 'instance' existe
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Inicialização das Extensões ---
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # --- Configuração do User Loader para Flask-Login ---
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ----------------------------------------------------
    # 📌 REGISTRO DE BLUEPRINTS
    # ----------------------------------------------------
    
    # Importa os Blueprints explicitamente de seus arquivos de rotas.
    from app.auth.routes import bp as auth_bp
    from app.services.routes import bp as services_bp 
    
    app.register_blueprint(auth_bp) 
    app.register_blueprint(services_bp) 
    
    # ----------------------------------------------------
    
    # A rota /admin_dashboard DEVE ser removida daqui, pois já foi definida
    # dentro do Blueprint 'services' (services/dashboard), que é o lugar correto.
    # Se você quiser uma rota para o admin sem prefixo, defina-a aqui.
    
    # Exemplo: Se /admin_dashboard for necessário, a importação do decorator deve vir de 'app.decorators':
    # from app.decorators import admin_required 
    # @app.route('/admin_dashboard')
    # @login_required
    # @admin_required
    # def admin_dashboard():
    #     return render_template('admin_dashboard.html', title='Admin Dashboard')

    # --- Rotas Principais ---
    # app/__init__.py (Dentro da função create_app, antes do return app final)

    # ... (Resto das rotas e Blueprints)

    # --- Rotas Principais ---
    @app.route('/')
    def index():
        return render_template('index.html', title='Início')


    # ===============================================
    # 📌 REGISTRO DE COMANDOS CLI CUSTOMIZADOS (LOCAL CORRIGIDO)
    # ===============================================
    
    # 🚨 NOTA: Para simplificar, registre o CLI sempre que o app for criado.
    # Se quiser manter a verificação de ambiente, ela deve estar DENTRO da função.
    
    from app import cli # Importa o módulo cli.py
    
    for command in cli.cli_commands:
        app.cli.add_command(command)
            
    # ===============================================

    return app # <--- Este deve ser o retorno final.