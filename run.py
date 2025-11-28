# run.py

import os
from dotenv import load_dotenv # Importa a função para carregar o .env
from app import create_app, db
from app.models import User, Service, Appointment

# 💡 CORREÇÃO CRÍTICA: Carrega as variáveis do arquivo .env
# Isso deve ser feito ANTES de criar a aplicação para que os.environ.get() 
# possa ler as credenciais de email e a SECRET_KEY no config.py
load_dotenv()
print(f"DEBUG EMAIL USER: {os.environ.get('MAIL_USERNAME')}") # Adicione esta linha
print(f"DEBUG EMAIL PASS EXISTE: {bool(os.environ.get('MAIL_PASSWORD'))}") # Adicione esta linha

# Cria a instância da aplicação Flask
app = create_app()

# Permite criar e gerenciar o banco de dados no shell interativo
@app.shell_context_processor
def make_shell_context():
    """Adiciona as instâncias do DB e dos Models ao contexto do Flask shell."""
    return {'db': db, 'User': User, 'Service': Service, 'Appointment': Appointment}

if __name__ == '__main__':
    # Usamos app.run() apenas para rodar diretamente o arquivo Python
    # O modo preferido (e mais seguro) é usar 'flask run' no terminal.
    app.run(debug=True)