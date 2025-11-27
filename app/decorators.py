from functools import wraps
from flask import abort, current_app, redirect, url_for, flash
from flask_login import current_user

def admin_required(f):
    """
    Decorator customizado para garantir que apenas usuários com is_admin=True acessem a rota.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Verifica se o usuário está logado
        if not current_user.is_authenticated:
            # Se não estiver logado, redireciona para o login (flask_login faria isso, mas é bom ser explícito)
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        
        # 2. Verifica se o usuário NÃO é administrador
        if not current_user.is_admin:
            # Se não for admin, retorna 403 (Proibido) e exibe uma mensagem
            flash('Acesso negado: Você não tem permissão de administrador.', 'danger')
            return redirect(url_for('index')) # Redireciona para a home
            
        # 3. Se for admin, executa a função original
        return f(*args, **kwargs)
    return decorated_function