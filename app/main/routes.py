from flask import render_template
from . import bp # Importa a Blueprint 'bp' definida em __init__.py

# ROTAS DE DOCUMENTAÇÃO LEGAL
# A rota index (/) foi movida aqui, seguindo o padrão de Blueprints

# Rota Vazia (Página Inicial)
@bp.route('/')
def index():
    return render_template('index.html', title='Início') 

# Rota de Termos de Uso
@bp.route('/termos-de-uso')
def terms():
    return render_template('terms.html') 

# Rota de Política de Privacidade
@bp.route('/politica-de-privacidade')
def privacy():
    return render_template('politica.html')