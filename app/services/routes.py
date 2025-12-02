from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db, mail
from datetime import datetime, timedelta, date
from app.models import Service, Appointment 
from flask_mail import Message
from app.tasks import send_appointment_reminder 
from sqlalchemy import or_, func, and_


# ----------------------------------------------------------------------
# 📌 1. DEFINIÇÃO DO BLUEPRINT
# ----------------------------------------------------------------------
# Prefixo /services para rotas de cliente (ex: /services/book)
bp = Blueprint('services', __name__, url_prefix='/services')


# ----------------------------------------------------
# 📌 2. FUNÇÃO AUXILIAR DE ENVIO DE EMAIL (Reusada no Agendamento/Cancelamento)
# ----------------------------------------------------
def send_appointment_email(appointment, subject, status):
    """
    Envia email de notificação para o usuário sobre o agendamento.
    """
    msg = Message(
        subject,
        recipients=[appointment.user.email] 
    )
    
    msg.body = f"""
Olá, {appointment.user.nome}!

Seu agendamento foi {status.lower()} com sucesso.

Detalhes do Serviço:
- Serviço: {appointment.servico.nome}
- Data/Hora: {appointment.data_horario.strftime('%d/%m/%Y às %H:%M')}
- Duração: {appointment.servico.duracao_minutos} minutos
- Status: {appointment.status}

Para visualizar ou cancelar seu agendamento, acesse a seção 'Meus Agendamentos' no aplicativo.

Atenciosamente,
Sua Equipe de Agendamentos.
"""
    
    try:
        mail.send(msg)
        print(f"DEBUG: Email enviado com sucesso para {appointment.user.email} (Assunto: {subject})")
    except Exception as e:
        print(f"ERRO CRÍTICO AO ENVIAR EMAIL: Verifique a configuração SMTP. Erro: {e}")


# ----------------------------------------------------
# 📌 3. FUNÇÕES AUXILIARES (has_conflict e get_available_slots)
# ----------------------------------------------------

def has_conflict(service_id, desired_start_time, appointment_id_to_exclude=None):
    """
    Verifica se o horário desejado conflita com agendamentos existentes, 
    excluindo um agendamento específico.
    """
    service = Service.query.get(service_id)
    if not service:
        return False
        
    duration = service.duracao_minutos
    desired_end_time = desired_start_time + timedelta(minutes=duration)

    start_of_day = datetime.combine(desired_start_time.date(), datetime.min.time())
    end_of_day_exclusive = start_of_day + timedelta(days=1) 

    # Filtra apenas agendamentos com status 'Agendado'
    query = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_of_day,
        Appointment.data_horario < end_of_day_exclusive
    ).filter(Appointment.status == 'Agendado')
    
    # Exclui o próprio agendamento (mantido para compatibilidade, embora não seja usado na rota 'book')
    if appointment_id_to_exclude:
        query = query.filter(Appointment.id != appointment_id_to_exclude)
        
    all_appointments_on_day = query.all()
    
    for existing_appointment in all_appointments_on_day:
        existing_service_duration = existing_appointment.servico.duracao_minutos 
        existing_start_time = existing_appointment.data_horario
        existing_end_time = existing_start_time + timedelta(minutes=existing_service_duration)

        if desired_start_time < existing_end_time and desired_end_time > existing_start_time:
            return True 

    return False


def get_available_slots(service_id, date_obj):
    """Calcula e retorna todos os slots disponíveis de um serviço em um dia."""
    
    START_HOUR = 9
    END_HOUR = 17 

    service = Service.query.get(service_id)
    if not service:
        return []

    duration = service.duracao_minutos
    
    start_time_limit = datetime.combine(date_obj.date(), datetime.min.time().replace(hour=START_HOUR))
    end_time_limit = datetime.combine(date_obj.date(), datetime.min.time().replace(hour=END_HOUR))

    # 1. Busca agendamentos confirmados (status 'Agendado')
    existing_appointments = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_time_limit,
        Appointment.data_horario < end_time_limit,
        Appointment.status == 'Agendado'
    ).all()

    taken_intervals = []
    for appt in existing_appointments:
        appt_duration = appt.servico.duracao_minutos
        start = appt.data_horario
        end = start + timedelta(minutes=appt_duration)
        taken_intervals.append((start, end))

    available_slots = []
    current_slot_start = start_time_limit

    # Intervalo de iteração (30 minutos)
    SLOT_INTERVAL = 30 
    while current_slot_start < end_time_limit:
        
        # Ignora horários no passado para o dia atual
        if date_obj.date() == datetime.now().date() and current_slot_start < datetime.now():
            current_slot_start += timedelta(minutes=SLOT_INTERVAL)
            continue
            
        potential_end_time = current_slot_start + timedelta(minutes=duration)

        if potential_end_time > end_time_limit:
            break

        # Verifica conflito
        is_conflicting = False
        for taken_start, taken_end in taken_intervals:
            if current_slot_start < taken_end and potential_end_time > taken_start:
                is_conflicting = True
                break
        
        if not is_conflicting:
            available_slots.append(current_slot_start.strftime('%H:%M'))
        
        current_slot_start += timedelta(minutes=SLOT_INTERVAL)

    return available_slots


# ----------------------------------------------------
# 📌 4. ROTA DE API PARA CALCULAR SLOTS DISPONÍVEIS
# ----------------------------------------------------
@bp.route('/api/available_slots', methods=['GET'])
@login_required
def api_available_slots():
    """Endpoint chamado pelo JavaScript para obter os slots disponíveis."""
    service_id = request.args.get('service_id', type=int)
    date_str = request.args.get('date')

    if not service_id or not date_str:
        return jsonify({'error': 'Missing service_id or date'}), 400

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    slots = get_available_slots(service_id, date_obj)
    
    return jsonify({'available_slots': slots})


# ----------------------------------------------------
# 📌 5. ROTAS DE CLIENTE
# ----------------------------------------------------

## --- ROTA DE AGENDAMENTO (Cliente) ---
@bp.route('/book', methods=['GET', 'POST'])
@login_required 
def book_appointment():
    """Permite ao cliente selecionar um serviço e agendar um horário."""
    
    # 📌 FILTRA apenas serviços ATIVOS para clientes
    services = Service.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        service_id = request.form.get('service_id', type=int)
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        
        # 1. Validação de Dados e Conversão
        try:
            # Verifica se o service_id corresponde a um serviço ativo (segurança)
            selected_service = Service.query.filter_by(id=service_id, is_active=True).first()
            if not selected_service:
                flash('Serviço inválido ou indisponível.', 'danger')
                return redirect(url_for('services.book_appointment'))
                
            desired_start_time = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
        except (ValueError, TypeError): 
            flash('Formato de dados inválido.', 'danger')
            return redirect(url_for('services.book_appointment'))
            
        # 2. Verificar se o horário já passou
        if desired_start_time < datetime.now() - timedelta(minutes=5): 
            flash('Não é possível agendar um horário no passado.', 'danger')
            return redirect(url_for('services.book_appointment'))
            
        # 3. VALIDAÇÃO DE CONFLITO OBRIGATÓRIA (Reaplicada para garantir, caso o cliente tente burlar o JS/API)
        # Manter has_conflict aqui é a prova de falhas definitiva.
        if has_conflict(service_id, desired_start_time):
            flash('O horário selecionado não está disponível. Conflito detectado!', 'danger')
            return redirect(url_for('services.book_appointment'))
            
        # 4. Criação do Agendamento
        try:
            new_appointment = Appointment(
                user_id=current_user.id,
                service_id=service_id,
                data_horario=desired_start_time,
                status='Agendado'
            )
            
            db.session.add(new_appointment)
            db.session.commit()
            
            # 5. Envio do Email de Confirmação Imediata (Síncrono)
            send_appointment_email(
                appointment=new_appointment, 
                subject="Confirmação de Agendamento Realizado", 
                status='Confirmado'
            )
            
            # 6. AGENDAMENTO DO LEMBRETE CELERY (24 HORAS ANTES)
            reminder_time = desired_start_time - timedelta(hours=24)
            
            if reminder_time > datetime.now():
                # NOTE: Calcular o 'countdown' antes do Agendamento
                countdown_seconds = (reminder_time - datetime.now()).total_seconds()
                
                send_appointment_reminder.apply_async(
                    args=[new_appointment.id], 
                    countdown=countdown_seconds # Agendado para 24 horas antes
                )
                flash_message = f'Agendamento realizado com sucesso para {desired_start_time.strftime("%d/%m/%Y às %H:%M")}! O lembrete foi agendado.'
            else:
                flash_message = f'Agendamento realizado com sucesso para {desired_start_time.strftime("%d/%m/%Y às %H:%M")}! (Lembrete não agendado, pois está muito próximo ou no passado).'
            
            flash(flash_message, 'success')
            return redirect(url_for('services.my_appointments'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar agendamento: {e}")
            flash('Ocorreu um erro ao processar o agendamento. Tente novamente.', 'danger')

    return render_template('services/book.html', 
                            title='Novo Agendamento', 
                            services=services, 
                            now=datetime.now)
    
# ... (o restante do código é mantido, pois está correto) ...
    
    
## --- ROTA: MEUS AGENDAMENTOS (Cliente) ---
@bp.route('/my_appointments')
@login_required
def my_appointments():
    """Visualiza todos os agendamentos do usuário logado."""
    appointments = Appointment.query.filter_by(user_id=current_user.id)\
                                   .order_by(Appointment.data_horario.asc())\
                                   .all()
    
    return render_template('services/my_appointments.html', 
                           title='Meus Agendamentos', 
                           appointments=appointments,
                           now=datetime.now, 
                           datetime=datetime) 
    
    
## --- ROTA: CANCELAR AGENDAMENTO (Cliente) ---
@bp.route('/cancel/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    """Permite ao cliente (ou Admin) cancelar um agendamento."""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 📌 Apenas o próprio usuário pode cancelar nesta rota (ou o Admin, se ele estiver usando)
    if appointment.user_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para cancelar este agendamento.', 'danger')
        return redirect(url_for('services.my_appointments'))

    # Verifica se o agendamento já passou
    if appointment.data_horario < datetime.now():
        flash('Não é possível cancelar um agendamento que já ocorreu.', 'danger')
        # Redireciona para onde o usuário estava
        return redirect(url_for('services.my_appointments'))
    
    appointment.status = 'Cancelado'
    db.session.commit()
    
    # Envio de email de cancelamento
    try:
        send_appointment_email(
            appointment=appointment, 
            subject="CANCELAMENTO de Agendamento", 
            status='Cancelado'
        )
    except Exception as e:
        print(f"AVISO: Falha ao enviar email de cancelamento: {e}") 

    flash('Agendamento cancelado com sucesso. Notificação enviada.', 'info')
    
    # Se o cancelamento foi feito pelo Admin, ele provavelmente veio do admin.manage_appointments
    # Mas nesta rota, o padrão é retornar ao 'my_appointments' do cliente.
    # Se o Admin usou o link do cliente, ele vai para a página de cliente.
    return redirect(url_for('services.my_appointments'))