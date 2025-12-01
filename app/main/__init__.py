from flask import Blueprint

# Define e inicializa a Blueprint. Usaremos 'main' como nome interno da Blueprint, 
# mas a variável Python será 'bp' para manter o padrão das suas outras Blueprints.
bp = Blueprint('main', __name__)

# Importa as rotas NO FINAL. Isso registra as funções de rota 
# (index, terms, privacy) na Blueprint 'bp' após sua definição.
from . import routes