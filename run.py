# run.py (Versão Limpa)

import os
from dotenv import load_dotenv 
# Certifique-se de importar o celery aqui
from app import create_app, celery 
from app.models import User, Service, Appointment # Não precisa, mas pode manter

# Carrega as variáveis de ambiente
load_dotenv()
print(f"DEBUG EMAIL USER: {os.environ.get('MAIL_USERNAME')}") 
print(f"DEBUG EMAIL PASS EXISTE: {bool(os.environ.get('MAIL_PASSWORD'))}") 

# Cria a instância da aplicação Flask (o Celery é configurado dentro dela)
app = create_app()

# Importação para o Celery Worker
import app.tasks 

# REMOVA O BLOCO shell_context_processor DAQUI!

if __name__ == '__main__':
    app.run(debug=True)