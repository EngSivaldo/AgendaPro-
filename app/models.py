# app/models.py

from datetime import datetime, timezone
from app import db, login
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index

# Função auxiliar para o loader do Flask-Login
@login.user_loader
def load_user(id):
    """Carrega o usuário dado o ID para o Flask-Login."""
    return db.session.get(User, int(id))


# --------------------------
# 1. Tabela User (Usuário)
# --------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    # 📌 Índice para otimizar buscas por e-mail
    __table_args__ = (Index('idx_user_email', 'email'),)
    
    def set_password(self, password):
        """Criptografa a senha para armazenamento."""
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha fornecida corresponde ao hash armazenado."""
        return check_password_hash(self.senha_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

# --------------------------
# 2. Tabela Service (Serviço)
# --------------------------
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # 📌 MELHORIA: UNIQUE=TRUE para garantir nomes de serviços não duplicados
    nome = db.Column(db.String(100), nullable=False, unique=True) 
    descricao = db.Column(db.String(255))
    preco = db.Column(db.Float, nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    
    # 📌 MELHORIA: Soft Delete - O serviço é ATIVO por padrão
    is_active = db.Column(db.Boolean, default=True) 

    # Agendamentos reversos criados pelo backref em Appointment
    
    def __repr__(self):
        return f'<Service {self.nome}>'

# --------------------------
# 3. Tabela Appointment (Agendamento)
# --------------------------
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_horario = db.Column(db.DateTime, index=True, nullable=False)
    status = db.Column(db.String(50), default='Agendado') 
    
    # 📌 MELHORIA: Campo de Auditoria (registra quando o agendamento foi CRIADO)
    # Usa datetime.now(timezone.utc) para consistência no banco de dados.
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc)) 
    
    # Chaves Estrangeiras (Relações N:1)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)

    # Relacionamento 1: User (acesso: appointment.user)
    user = db.relationship('User', backref='agendamentos', foreign_keys=[user_id]) 
    
    # Relacionamento 2: Service (acesso: appointment.servico)
    servico = db.relationship('Service', backref='agendamentos_do_servico', foreign_keys=[service_id])

    def __repr__(self):
        return f'<Appointment {self.user.nome} - {self.servico.nome} em {self.data_horario}>'