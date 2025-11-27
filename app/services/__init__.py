from flask import Blueprint

# Define o Blueprint chamado 'services'
# O prefixo será '/services' (ex: /services/book)
bp = Blueprint('services', __name__, url_prefix='/services')

# IMPORTANTE: Importa as rotas para que sejam registradas pelo Blueprint
from . import routes