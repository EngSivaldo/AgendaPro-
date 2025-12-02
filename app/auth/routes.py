from flask import render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import bp 
from app.models import User
from app import db
from app.decorators import admin_required 

# Se 'bp' não estiver definido no topo (depende da sua estrutura de __init__), 
# você pode precisar desta linha:
# bp = Blueprint('auth', __name__, url_prefix='/auth') 

## --- ROTAS DE AUTENTICAÇÃO ---

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Rota para registrar novos usuários (Clientes)"""

    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        
        # --- 1. VALIDAÇÃO: Senhas Iguais ---
        if password != confirm_password:
            flash('As senhas digitadas não são iguais. Tente novamente.', 'danger')
            return redirect(url_for('auth.register'))
            
        # --- 2. VALIDAÇÃO: Email Existente ---
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Este email já está registrado. Por favor, faça login.', 'warning')
            return redirect(url_for('auth.register'))

        # --- 3. Criação do Novo Usuário ---
        new_user = User(nome=nome, email=email, is_admin=False)
        new_user.set_password(password) 

        db.session.add(new_user)
        
        try:
            db.session.commit()
            flash('Registro realizado com sucesso! Por favor, faça o login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar novo usuário: {e}")
            flash('Ocorreu um erro interno ao registrar. Tente novamente.', 'danger')
            return redirect(url_for('auth.register'))
            
    return render_template('auth/register.html', title='Registrar')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Rota para login de usuários (Clientes e Administradores)"""
    if current_user.is_authenticated:
        # Assumindo que a rota principal da aplicação é 'main.index'
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()

        # 1. Validação de Usuário e Senha
        if user is None or not user.check_password(password):
            flash('Email ou senha inválidos. Tente novamente.', 'danger')
            return redirect(url_for('auth.login'))
        
        # 2. Login
        login_user(user)
        
        # Redireciona o usuário
        if user.is_admin:
            flash(f'Bem-vindo, Administrador(a) {user.nome}!', 'info')
            # 🟢 CORREÇÃO APLICADA
            return redirect(url_for('admin.admin_dashboard')) 
        
        flash(f'Bem-vindo(a), {user.nome}!', 'success')
        return redirect(url_for('main.index'))
        
    return render_template('auth/login.html', title='Login')

@bp.route('/logout')
@login_required 
def logout():
    """Rota para fazer logout"""
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('main.index'))

# --- ROTAS DE ADMINISTRAÇÃO DE USUÁRIOS (CORRETO: Permanecem em 'auth') ---

@bp.route('/manage_users')
@login_required
@admin_required
def manage_users():
    """Visualiza e gerencia todos os usuários (Admin)."""
    all_users = User.query.all()
    return render_template('auth/manage_users.html', 
                            title='Gerenciar Usuários', 
                            users=all_users)
    
@bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Permite ao administrador editar o nome, email e status admin de um usuário."""
    
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.nome = request.form['nome']
        user.email = request.form['email']
        user.is_admin = bool(request.form.get('is_admin')) 
        
        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)
            
        try:
            db.session.commit()
            flash(f'Usuário "{user.nome}" atualizado com sucesso!', 'success')
            return redirect(url_for('auth.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar usuário: {e}', 'danger')
            
    return render_template('auth/edit_user.html', 
                            title='Editar Usuário', 
                            user=user)
    
@bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Permite ao administrador deletar um usuário pelo ID."""
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Você não pode deletar sua própria conta de administrador.', 'warning')
        return redirect(url_for('auth.manage_users'))

    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'Usuário "{user.nome}" deletado permanentemente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao deletar usuário: {e}', 'danger')

    return redirect(url_for('auth.manage_users'))