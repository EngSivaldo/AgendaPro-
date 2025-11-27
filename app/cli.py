import click
from flask.cli import with_appcontext
from app import db
from app.models import User # Supondo que seu modelo User está em app.models

@click.command('create-admin')
@click.argument('nome')
@click.argument('email')
@click.argument('senha')
@with_appcontext
def create_admin_command(nome, email, senha):
    """Cria um novo usuário e o define como administrador (is_admin=True)."""
    
    # Verifica se o usuário já existe
    if User.query.filter_by(email=email).first():
        click.echo(f"❌ Erro: O email '{email}' já está cadastrado.")
        return

    try:
        # Cria o novo usuário
        new_admin = User(nome=nome, 
                         email=email, 
                         is_admin=True)
        
        # Define a senha (Requer que User tenha o método set_password)
        new_admin.set_password(senha) 

        db.session.add(new_admin)
        db.session.commit()
        
        click.echo(f"✅ Administrador '{nome}' ({email}) criado com sucesso!")

    except Exception as e:
        db.session.rollback()
        click.echo(f"🛑 Erro ao criar administrador: {e}")

# Adicione o comando a uma lista para ser registrado (ver próximo passo)
cli_commands = [create_admin_command]