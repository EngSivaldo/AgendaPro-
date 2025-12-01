from functools import wraps 
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db, mail
from app.decorators import admin_required 
from datetime import datetime, timedelta, date
from app.models import Service, Appointment, User # Assumindo que models estão aqui
from sqlalchemy import or_, func, and_
from sqlalchemy.exc import IntegrityError 
from flask_mail import Message
from app.tasks import send_appointment_reminder 
# Importação garantida para a rota de faturamento
from sqlalchemy import func


# ----------------------------------------------------------------------
# 📌 1. DEFINIÇÃO DO BLUEPRINT
# ----------------------------------------------------------------------
bp = Blueprint('services', __name__, url_prefix='/services')


# ----------------------------------------------------
# 📌 2. FUNÇÃO AUXILIAR DE ENVIO DE EMAIL
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
        # Em produção, você pode usar um logger ou Celery para re-tentar
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

    # 📌 FILTRA apenas agendamentos com status 'Agendado'
    query = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_of_day,
        Appointment.data_horario < end_of_day_exclusive
    ).filter(Appointment.status == 'Agendado')
    
    # Exclui o próprio agendamento (usado no reagendamento)
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
# 📌 5. ROTAS DE CLIENTE E ADMIN
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
            
        # 3. Lógica Anti-Conflito (RNF04)
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
            
            # Acessar as propriedades antes de enviar o email
            new_appointment.user.email 
            new_appointment.servico.nome
            
            # 5. Envio do Email de Confirmação Imediata (Síncrono)
            send_appointment_email(
                appointment=new_appointment, 
                subject="Confirmação de Agendamento Realizado", 
                status='Confirmado'
            )
            
            # 6. AGENDAMENTO DO LEMBRETE CELERY (24 HORAS ANTES)
            reminder_time = desired_start_time - timedelta(hours=24)
            
            if reminder_time > datetime.now():
                countdown_seconds = (reminder_time - datetime.now()).total_seconds()
                
                send_appointment_reminder.apply_async(
                    args=[new_appointment.id], 
                    countdown=countdown_seconds # Agendado para 24 horas antes
                )
                flash_message = 'Agendamento realizado com sucesso! O lembrete será agendado (24h antes).'
            else:
                 flash_message = 'Agendamento realizado com sucesso! (Lembrete não agendado, pois está muito próximo ou no passado).'
            
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
    
    
## --- ROTA DE ADMINISTRAÇÃO (DASHBOARD) ---
@bp.route('/dashboard') 
@login_required
@admin_required
def admin_dashboard():
    """Renderiza o template do Painel de Administração."""
    return render_template('admin_dashboard.html', title='Dashboard Admin')


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
    
    
## --- ROTA: CANCELAR AGENDAMENTO (Cliente/Admin) ---
@bp.route('/cancel/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    """Permite ao cliente (ou Admin) cancelar um agendamento."""
    appointment = Appointment.query.get_or_404(appointment_id)
    is_authorized = appointment.user_id == current_user.id or current_user.is_admin

    if not is_authorized:
        flash('Você não tem permissão para cancelar este agendamento.', 'danger')
        return redirect(url_for('services.my_appointments'))

    # Verifica se o agendamento já passou
    if appointment.data_horario < datetime.now():
        flash('Não é possível cancelar um agendamento que já ocorreu.', 'danger')
        if current_user.is_admin:
            return redirect(url_for('services.manage_appointments')) 
        else:
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
    
    if current_user.is_admin:
        return redirect(url_for('services.manage_appointments')) 
    else:
        return redirect(url_for('services.my_appointments'))
    
    
## --- ROTA: LISTAR SERVIÇOS (Admin) ---
@bp.route('/list')
@login_required
@admin_required
def list_services():
    """Visualiza todos os serviços cadastrados (ativos e inativos) (Apenas Admin)"""
    # 📌 O Admin vê TODOS os serviços para gerenciar o status 'is_active'
    services = Service.query.order_by(Service.is_active.desc(), Service.nome.asc()).all()
    
    return render_template('services/list.html', title='Gerenciar Serviços', services=services)


## --- ROTA: CRIAR NOVO SERVIÇO (Admin) ---
@bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_service():
    """Permite ao administrador criar um novo serviço."""
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        
        try:
            # Lógica robusta de conversão numérica
            preco_str = request.form.get('preco').replace(',', '.') 
            preco = float(preco_str) 
            duracao_minutos = int(request.form.get('duracao_minutos'))
            
            if preco < 0 or duracao_minutos <= 0:
                flash('Preço deve ser positivo e Duração maior que zero.', 'danger')
                return redirect(url_for('services.create_service'))

        except (ValueError, TypeError): 
            flash('Preço e Duração devem ser números válidos.', 'danger')
            return redirect(url_for('services.create_service'))

        new_service = Service(
            nome=nome,
            descricao=descricao,
            preco=preco,
            duracao_minutos=duracao_minutos,
            is_active=True # Novos serviços são ativos por padrão
        )
        
        try:
            db.session.add(new_service)
            db.session.commit()
            
            flash(f'Serviço "{nome}" criado com sucesso!', 'success')
            return redirect(url_for('services.list_services'))
            
        # 📌 TRATAMENTO DE ERRO: Captura erro de unicidade (nome duplicado)
        except IntegrityError:
            db.session.rollback()
            flash(f'O nome do serviço "{nome}" já existe. Por favor, escolha um nome diferente.', 'danger')
            return redirect(url_for('services.create_service'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar serviço: {e}")
            flash('Ocorreu um erro interno ao criar o serviço.', 'danger')
            return redirect(url_for('services.create_service'))

    return render_template('services/new.html', title='Adicionar Serviço')


## --- ROTA: GERENCIAR AGENDAMENTOS (Admin) ---
@bp.route('/manage_appointments')
@login_required
@admin_required
def manage_appointments():
    """Visualiza todos os agendamentos feitos no sistema, incluindo o cliente."""
    
    all_appointments = Appointment.query.order_by(Appointment.data_horario.asc()).all()
    
    return render_template('services/manage_appointments.html', 
                           title='Gerenciar Agendamentos', 
                           appointments=all_appointments,
                           now=datetime.now)
    
## --- ROTA: EDITAR SERVIÇO (Admin) ---
@bp.route('/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_service(service_id):
    """Permite ao administrador editar um serviço existente."""
    
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        
        try:
            # Lógica robusta de conversão numérica
            preco_str = request.form.get('preco', '0').replace(',', '.')
            duracao_str = request.form.get('duracao_minutos', '0')
            
            preco = float(preco_str) 
            duracao_minutos = int(duracao_str)
            
            if preco < 0 or duracao_minutos <= 0:
                flash('O preço deve ser positivo e a duração deve ser maior que zero.', 'danger')
                return redirect(url_for('services.edit_service', service_id=service.id))
            
            # 📌 Captura o valor do checkbox 'is_active'
            service.is_active = 'is_active' in request.form 
            
        except (ValueError, TypeError): 
            flash('Preço e Duração devem ser números válidos. Por favor, verifique os campos.', 'danger')
            return redirect(url_for('services.edit_service', service_id=service.id))
        
        service.nome = nome
        service.descricao = descricao
        service.preco = preco
        service.duracao_minutos = duracao_minutos
        
        try:
            db.session.commit()
            flash(f'Serviço "{service.nome}" atualizado com sucesso!', 'success')
            return redirect(url_for('services.list_services'))
            
        # 📌 TRATAMENTO DE ERRO: Captura erro de unicidade
        except IntegrityError:
            db.session.rollback()
            flash(f'O nome do serviço "{nome}" já existe. Escolha outro nome.', 'danger')
            return redirect(url_for('services.edit_service', service_id=service.id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao editar serviço: {e}")
            flash('Erro ao salvar as alterações.', 'danger')
            return redirect(url_for('services.edit_service', service_id=service.id))


    # Para requisição GET
    return render_template('services/edit_service.html', 
                           title=f'Editar Serviço: {service.nome}', 
                           service=service)
    
    
## --- ROTA: DESATIVAR/SOFT DELETE SERVIÇO (Admin) ---
@bp.route('/delete/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def delete_service(service_id):
    """Permite ao administrador DESATIVAR (Soft Delete) um serviço. (Chamado via rota delete)"""
    return redirect(url_for('services.deactivate_service', service_id=service_id)) # Redireciona para a rota específica de desativação

@bp.route('/service/deactivate/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def deactivate_service(service_id):
    """Desativa um serviço (Soft Delete) definindo is_active=False."""
    
    # 1. Busca o serviço pelo ID
    service = db.session.get(Service, service_id)

    if service is None:
        flash('Serviço não encontrado.', 'danger')
        return redirect(url_for('services.list_services'))

    if not service.is_active:
        flash('O serviço já está inativo.', 'info')
        return redirect(url_for('services.list_services'))

    # 2. Desativa o serviço
    service.is_active = False
    
    # 3. Commit
    db.session.commit()
    flash(f'Serviço "{service.nome}" desativado (Soft Delete) com sucesso. Ele não será mais exibido para novos agendamentos.', 'success')
    
    return redirect(url_for('services.list_services'))


## --- ROTA: ATIVAR SERVIÇO (Admin) ---
@bp.route('/service/activate/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def activate_service(service_id):
    """Reativa um serviço definindo is_active=True."""
    
    # 1. Busca o serviço pelo ID
    service = db.session.get(Service, service_id)

    if service is None:
        flash('Serviço não encontrado.', 'danger')
        return redirect(url_for('services.list_services'))

    if service.is_active:
        flash('O serviço já está ativo.', 'info')
        return redirect(url_for('services.list_services'))

    # 2. Reativa o serviço
    service.is_active = True
    
    # 3. Commit
    db.session.commit()
    flash(f'Serviço "{service.nome}" reativado com sucesso.', 'success')
    
    return redirect(url_for('services.list_services'))


## --- ROTA: ATUALIZAR STATUS (Admin) ---
@bp.route('/update_status/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def update_appointment_status(appointment_id):
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # 🚨 CORRIGIDO: Use 'status' para pegar o valor do formulário
    new_status = request.form.get('status') 
    valid_statuses = ['Agendado', 'Concluído', 'Cancelado', 'Reagendado']
    
    if new_status not in valid_statuses:
        flash('Status inválido fornecido.', 'danger')
        return redirect(url_for('services.manage_appointments'))

    old_status = appointment.status 

    if old_status == new_status:
        flash('Status inalterado.', 'info')
        return redirect(url_for('services.manage_appointments'))

    # ----------------------------------------------------
    # 📌 NOVA REGRA DE NEGÓCIO: Conclusão de Serviço Futuro
    # Garante que a data_horario seja o momento atual se for concluído.
    # ----------------------------------------------------
    flash_message_override = None

    if new_status == 'Concluído':
        now = datetime.now()
        
        if appointment.data_horario > now:
            # Altera a data agendada para o momento da conclusão (hoje)
            appointment.data_horario = now
            
            flash_message_override = (
                f"Status do Agendamento ID {appointment_id} alterado para **Concluído**. "
                f"A data original ({old_status}) foi atualizada para a data e hora atuais para fins de faturamento."
            )
        
    try:
        appointment.status = new_status
        db.session.commit() 

        # Envio de email de notificação
        send_appointment_email(
            appointment=appointment, 
            subject=f"ATUALIZAÇÃO DE STATUS: Agendamento ID {appointment_id}", 
            status=new_status
        )
        
        # Usa a mensagem de aviso se a data foi alterada
        if flash_message_override:
            flash(flash_message_override, 'warning')
        else:
            flash(f'Status do agendamento atualizado para "{new_status}" e cliente notificado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRO DE DB ao atualizar status: {e}") 
        flash(f'Erro ao atualizar o status. Tente novamente.', 'danger')
        
    return redirect(url_for('services.manage_appointments'))


## --- ROTA: REAGENDAR (Admin) ---
@bp.route('/reschedule/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def reschedule_appointment(appointment_id):
    """Permite ao administrador alterar a data e o status de um agendamento."""
    
    appointment = Appointment.query.get_or_404(appointment_id)
    new_datetime_str = request.form.get('new_datetime')
    
    if not new_datetime_str:
        flash('A nova data e hora para o reagendamento são obrigatórias.', 'danger')
        return redirect(url_for('services.manage_appointments'))
    
    try:
        new_datetime = datetime.strptime(new_datetime_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Formato de data e hora inválido.', 'danger')
        return redirect(url_for('services.manage_appointments'))

    # 1. Validação de Data Futura
    if new_datetime < datetime.now():
        flash('A data e hora do reagendamento não podem ser no passado.', 'danger')
        return redirect(url_for('services.manage_appointments'))
        
    # 2. VALIDAÇÃO DE CONFLITO (usando a função revisada)
    if has_conflict(appointment.service_id, new_datetime, appointment_id_to_exclude=appointment.id):
        flash('ERRO: O novo horário conflita com outro agendamento existente. Selecione outro slot.', 'danger')
        return redirect(url_for('services.manage_appointments'))


    # 3. Atualiza e salva no banco de dados
    try:
        appointment.data_horario = new_datetime
        appointment.status = 'Reagendado' 
        
        db.session.commit()
        
        # Envio de Email de reagendamento
        send_appointment_email(
            appointment=appointment, 
            subject="REAGENDAMENTO de Serviço", 
            status='Reagendado'
        )
        
        # 📌 Reagendar o lembrete Celery, se necessário
        reminder_time = new_datetime - timedelta(hours=24)
        if reminder_time > datetime.now():
            countdown_seconds = (reminder_time - datetime.now()).total_seconds()
            send_appointment_reminder.apply_async(
                args=[appointment.id], 
                countdown=countdown_seconds
            )
        
        flash(f'Agendamento #{appointment.id} reagendado com sucesso para {new_datetime.strftime("%d/%m/%Y às %H:%M")} e cliente notificado.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO DE REAGENDAMENTO: {e}") 
        flash('Erro ao salvar o reagendamento no banco de dados. Tente novamente.', 'danger')
        
    return redirect(url_for('services.manage_appointments'))


## --- Rota para o Relatório de Faturamento (Admin) ---
@bp.route('/admin/reports/billing', methods=['GET'])
@login_required
@admin_required
def billing_report():
    """Calcula e exibe o faturamento total com base nos agendamentos concluídos."""
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # --- 1. Determinação do Período (Padrão: Mês Atual) ---
    today = date.today()
    
    # 📌 Se datas NÃO FORAM fornecidas pelo usuário, usa o Mês Atual como padrão
    if not start_date_str or not end_date_str:
        start_date_filter = datetime(today.year, today.month, 1)
        
        try:
            # Fim do mês (garante que inclui o dia 30, 31, etc.)
            end_date_filter = datetime(today.year, today.month + 1, 1) - timedelta(seconds=1) 
        except ValueError:
            end_date_filter = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
            
    # 📌 Se datas FORAM fornecidas pelo usuário
    else:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # Ajusta para incluir o dia inteiro (até 23:59:59)
            start_date_filter = start_date_obj
            end_date_filter = datetime.combine(end_date_obj.date(), datetime.max.time())
            
        except ValueError:
            flash('Formato de data inválido.', 'danger')
            return redirect(url_for('services.billing_report'))
            
    # 2. Construção da Query Base
    # Query que filtra apenas por 'Concluído'
    base_filter = [Appointment.status == 'Concluído']
    
    # Adiciona o filtro de data/hora (que agora contém a data de conclusão, se alterada)
    base_filter.append(Appointment.data_horario >= start_date_filter)
    base_filter.append(Appointment.data_horario <= end_date_filter)

    # 3. Execução do Cálculo SQL
    # Usa select_from(Appointment).join(Service) para resolver a ambiguidade do JOIN.
    total_revenue_query = db.session.query(func.sum(Service.preco)).select_from(Appointment).join(Service).filter(*base_filter)
    total_revenue = total_revenue_query.scalar() or 0.00
    
    # 4. Busca dos Agendamentos Detalhados
    appointments_query = Appointment.query.join(Service).filter(*base_filter).order_by(Appointment.data_horario.desc()) 
    completed_appointments = appointments_query.all()
    
    # 5. Retorno
    return render_template('services/billing_report.html', 
                           title='Relatório de Faturamento',
                           total_revenue=total_revenue,
                           appointments=completed_appointments,
                           start_date=start_date_filter.strftime('%Y-%m-%d'),
                           end_date=end_date_filter.strftime('%Y-%m-%d'),
                           datetime=datetime 
                           )