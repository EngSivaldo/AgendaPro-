from flask import render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import bp # Importa o Blueprint (CORRETO)
from app.models import User
from app import db
# REMOVA AS LINHAS DO admin_required e functools AQUI

## --- ROTAS DE AUTENTICAÇÃO ---

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Rota para registrar novos usuários (Clientes)"""
    # ... (O resto do código da rota register está correto)
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()

        # 1. Validação de Email Existente
        if user:
            flash('Este email já está registrado.', 'warning')
            return redirect(url_for('auth.register'))

        # 2. Criação do Novo Usuário
        new_user = User(nome=nome, email=email, is_admin=False)
        # Assumindo que set_password e check_password funcionam
        new_user.set_password(password) 

        db.session.add(new_user)
        db.session.commit()
        
        flash('Registro realizado com sucesso! Por favor, faça o login.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html', title='Registrar')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Rota para login de usuários (Clientes e Administradores)"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

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
            return redirect(url_for('services.admin_dashboard'))
        
        flash(f'Bem-vindo(a), {user.nome}!', 'success')
        return redirect(url_for('index'))
        
    return render_template('auth/login.html', title='Login')

@bp.route('/logout')
@login_required 
def logout():
    """Rota para fazer logout"""
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))

# NOVO: Implementação da rota manage_users (necessária para corrigir o BuildError do template)
from app.decorators import admin_required 

@bp.route('/manage_users')
@login_required
@admin_required
def manage_users():
    """Visualiza e gerencia todos os usuários (Admin)."""
    
    # Busca todos os usuários no banco de dados
    all_users = User.query.all()
    
    # Renderiza o template que você precisa criar
    return render_template('auth/manage_users.html', 
                           title='Gerenciar Usuários', 
                           users=all_users)
    
    
# app/auth/routes.py

# ... imports ...
from app.decorators import admin_required 
from app.models import User
# ...

# Rota de Edição
@bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Permite ao administrador editar o nome, email e status admin de um usuário."""
    
    user = User.query.get_or_404(user_id) # Busca o usuário pelo ID, ou retorna 404 se não existir

    if request.method == 'POST':
        user.nome = request.form['nome']
        user.email = request.form['email']
        
        # O campo 'is_admin' só é enviado se a checkbox estiver marcada
        user.is_admin = bool(request.form.get('is_admin')) 
        
        # Opcional: Lógica para mudar senha, se for enviada
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
            
    # GET: Exibe o formulário pré-preenchido
    return render_template('auth/edit_user.html', 
                           title='Editar Usuário', 
                           user=user)
    
    
# app/auth/routes.py

# ... (após a rota edit_user) ...

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Permite ao administrador deletar um usuário pelo ID."""
    
    user = User.query.get_or_404(user_id)
    
    # 🚨 PRECAUÇÃO: Não permita que o admin se delete acidentalmente
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