from app import create_app, db
from app.models import User, Service, Appointment

app = create_app()

# Permite criar e gerenciar o banco de dados no shell interativo
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Service': Service, 'Appointment': Appointment}

if __name__ == '__main__':
    app.run(debug=True)