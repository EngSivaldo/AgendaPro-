# app/tasks.py

# Importa a instância Celery, Mail e DB que definimos em app/__init__.py
from app.__init__ import celery, mail, db
from flask_mail import Message
# Importa o modelo de Agendamento (Appointment) e outros que você usa para obter o cliente
from app.models import Appointment, User 
from datetime import datetime

@celery.task
def send_appointment_reminder(appointment_id):
    """
    Tarefa Celery agendada para enviar um e-mail de lembrete 24h antes do agendamento.
    A tarefa roda dentro do contexto da aplicação (graças à configuração no __init__.py).
    """
    
    # 1. Busca o agendamento no banco de dados
    # db.session.get é preferível para buscar pelo ID primário
    appointment = db.session.get(Appointment, appointment_id)
    
    # 2. Verifica se o agendamento existe e não foi cancelado
    if appointment and appointment.status != 'Cancelado':
        
        # O try/except é importante em tarefas de fundo para registrar falhas
        try:
            # Assumindo que:
            # - appointment.user é o objeto do cliente
            # - appointment.servico é o objeto do serviço
            
            # Monta a Mensagem de E-mail
            msg = Message(
                f'Lembrete: Seu Agendamento no Smart Agenda ({appointment.servico.nome})',
                recipients=[appointment.user.email], 
                # Se você configurou SENDER_EMAIL no config.py, use-o aqui
                sender="seu_email@dominio.com" 
            )
            msg.body = (
                f"Olá, {appointment.user.nome},\n\n"
                f"Este é um lembrete do seu agendamento:\n"
                f"Serviço: {appointment.servico.nome}\n"
                f"Data e Hora: {appointment.data_horario.strftime('%d/%m/%Y às %H:%M')}\n\n"
                f"Aguardamos você. Se precisar cancelar, por favor, faça-o através do sistema.\n"
            )
            
            # Envia o E-mail usando a instância do Flask-Mail
            mail.send(msg)
            print(f"Lembrete (ID {appointment_id}) enviado com sucesso para: {appointment.user.email}")
            
        except Exception as e:
            # Em caso de erro (ex: falha de conexão SMTP, e-mail inválido, etc.)
            print(f"ERRO Celery: Falha ao enviar email de lembrete para agendamento {appointment_id}. Erro: {e}")