from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------
# 1. Tabela User (Usuário)
# --------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    # 📌 Relacionamento: REMOVIDO para evitar conflito. O backref em Appointment o criará.
    # agendamentos = db.relationship('Appointment', backref='cliente', lazy='dynamic') 
    
    def set_password(self, password):
        """Criptografa a senha para armazenamento (RNF03)"""
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha fornecida corresponde ao hash armazenado"""
        return check_password_hash(self.senha_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

# --------------------------
# 2. Tabela Service (Serviço)
# --------------------------
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(255))
    preco = db.Column(db.Float, nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    
    # 📌 Relacionamento: REMOVIDO para evitar conflito. O backref em Appointment o criará.
    # agendamentos = db.relationship('Appointment', backref='servico', lazy='dynamic')

    def __repr__(self):
        return f'<Service {self.nome}>'

# --------------------------
# 3. Tabela Appointment (Agendamento)
# --------------------------
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_horario = db.Column(db.DateTime, index=True, nullable=False)
    status = db.Column(db.String(50), default='Agendado') 
    
    # Chaves Estrangeiras (Relações N:1)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)

    # 📌 CORREÇÃO FINAL: Definir os relacionamentos AQUI usando o backref
    #
    # Relacionamento 1: User (O nome 'user' é o que o template espera: appointment.user.nome)
    # O backref='agendamentos' cria a lista User.agendamentos automaticamente.
    user = db.relationship('User', backref='agendamentos', foreign_keys=[user_id]) 
    
    # Relacionamento 2: Service (O nome 'servico' é o que o template espera: appointment.servico.nome)
    # O backref='agendamentos_do_servico' cria a lista Service.agendamentos_do_servico.
    servico = db.relationship('Service', backref='agendamentos_do_servico', foreign_keys=[service_id])


    def __repr__(self):
        # Agora o acesso a 'user' e 'servico' é garantido.
        return f'<Appointment {self.user.nome} - {self.servico.nome} em {self.data_horario}>'