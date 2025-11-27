from flask import Blueprint

# Define o Blueprint chamado 'auth' com o prefixo /auth
bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates') # Adicione template_folder se necessário

# IMPORTANTE: Importa as rotas para que sejam registradas no Blueprint
# Se esta linha estiver faltando, o Flask não sabe que as funções de rota existem!
from . import routes