from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db 
from app.decorators import admin_required # <-- CORRIGIDO AQUI: Importa do arquivo decorators.py
from datetime import datetime, timedelta
from app.models import Service, Appointment, User 
from sqlalchemy import or_, func, and_

# ----------------------------------------------------------------------
# 📌 1. DEFINIÇÃO DO BLUEPRINT
# ----------------------------------------------------------------------
bp = Blueprint('services', __name__, url_prefix='/services', template_folder='templates')

# ----------------------------------------------------
# 📌 2. FUNÇÃO AUXILIAR has_conflict 
# ----------------------------------------------------
def has_conflict(service_id, desired_start_time):
    """Verifica se o horário desejado conflita com agendamentos existentes."""
    
    service = Service.query.get(service_id)
    if not service:
        return False
        
    duration = service.duracao_minutos
    desired_end_time = desired_start_time + timedelta(minutes=duration)

    start_of_day = datetime.combine(desired_start_time.date(), datetime.min.time())
    end_of_day_exclusive = start_of_day + timedelta(days=1) 

    all_appointments_on_day = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_of_day,
        Appointment.data_horario < end_of_day_exclusive
    ).filter(Appointment.status == 'Agendado').all()
    
    for existing_appointment in all_appointments_on_day:
        
        # O objeto do serviço é 'servico' (minúsculo) devido ao relacionamento
        existing_service_duration = existing_appointment.servico.duracao_minutos 
        existing_start_time = existing_appointment.data_horario
        existing_end_time = existing_start_time + timedelta(minutes=existing_service_duration)

        # Lógica de Conflito: O novo agendamento começa antes do existente terminar E
        # O novo agendamento termina depois do existente começar.
        if desired_start_time < existing_end_time and desired_end_time > existing_start_time:
            return True 
    
    return False

# ----------------------------------------------------
# 📌 3. FUNÇÃO AUXILIAR DE CÁLCULO DE DISPONIBILIDADE
# ----------------------------------------------------
def get_available_slots(service_id, date_obj):
    """Calcula e retorna todos os slots disponíveis de um serviço em um dia."""
    
    # Horário de funcionamento: 9:00h às 17:00h
    START_HOUR = 9
    END_HOUR = 17 

    service = Service.query.get(service_id)
    if not service:
        return []

    duration = service.duracao_minutos
    
    # Define início e fim do limite de busca
    start_time_limit = datetime.combine(date_obj.date(), datetime.min.time().replace(hour=START_HOUR))
    end_time_limit = datetime.combine(date_obj.date(), datetime.min.time().replace(hour=END_HOUR))

    # 1. Busca todos os agendamentos confirmados no dia
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

    # 2. Itera de 30 em 30 minutos (Intervalo de iteração)
    SLOT_INTERVAL = 30 
    while current_slot_start < end_time_limit:
        
        # Ignora horários no passado para o dia atual
        if date_obj.date() == datetime.now().date() and current_slot_start < datetime.now():
            current_slot_start += timedelta(minutes=SLOT_INTERVAL)
            continue
            
        potential_end_time = current_slot_start + timedelta(minutes=duration)

        # Se o fim do agendamento ultrapassar o horário de trabalho, para
        if potential_end_time > end_time_limit:
            break

        # 3. Verifica se o slot potencial conflita com algum slot ocupado
        is_conflicting = False
        for taken_start, taken_end in taken_intervals:
            # Lógica de conflito (Slot Potencial vs Slot Ocupado)
            if current_slot_start < taken_end and potential_end_time > taken_start:
                is_conflicting = True
                break
        
        if not is_conflicting:
            available_slots.append(current_slot_start.strftime('%H:%M'))
        
        # Move para o próximo intervalo
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
        # Cria um objeto datetime com a data e hora mínima para a função de cálculo
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
    
    services = Service.query.all()
    
    if request.method == 'POST':
        service_id = request.form.get('service_id', type=int)
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        
        # 1. Validação de Dados e Conversão
        try:
            desired_start_time = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
        except ValueError:
            flash('Formato de data ou hora inválido.', 'danger')
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
        new_appointment = Appointment(
            user_id=current_user.id,
            service_id=service_id,
            data_horario=desired_start_time,
            status='Agendado'
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        flash('Agendamento realizado com sucesso!', 'success')
        return redirect(url_for('services.my_appointments')) # Melhor redirecionar para a lista de agendamentos do usuário

    return render_template('services/book.html', title='Novo Agendamento', services=services, now=datetime.now)
    
    
## --- ROTA DE ADMINISTRAÇÃO (DASHBOARD) ---
@bp.route('/dashboard') # Rota será /services/dashboard
@login_required
@admin_required
def admin_dashboard():
    """Renderiza o template do Painel de Administração."""
    # Aqui você pode adicionar lógica para calcular estatísticas se quiser
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
        # Redireciona corretamente, dependendo do usuário
        if current_user.is_admin:
            return redirect(url_for('services.manage_appointments')) 
        else:
            return redirect(url_for('services.my_appointments'))
    
    appointment.status = 'Cancelado'
    db.session.commit()
    
    flash('Agendamento cancelado com sucesso.', 'info')
    
    if current_user.is_admin:
        return redirect(url_for('services.manage_appointments')) 
    else:
        return redirect(url_for('services.my_appointments'))
    
    
## --- ROTA: LISTAR SERVIÇOS (Admin) ---
@bp.route('/list')
@login_required
@admin_required
def list_services():
    """Visualiza todos os serviços cadastrados (Apenas Admin)"""
    services = Service.query.all()
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
            preco = float(request.form.get('preco')) 
            duracao_minutos = int(request.form.get('duracao_minutos'))
        except (ValueError, TypeError): 
            flash('Preço e Duração devem ser números válidos.', 'danger')
            return redirect(url_for('services.create_service'))

        new_service = Service(
            nome=nome,
            descricao=descricao,
            preco=preco,
            duracao_minutos=duracao_minutos
        )
        
        db.session.add(new_service)
        db.session.commit()
        
        flash(f'Serviço "{nome}" criado com sucesso!', 'success')
        return redirect(url_for('services.list_services'))

    return render_template('services/new.html', title='Adicionar Serviço')


## --- ROTA: GERENCIAR AGENDAMENTOS (Admin) ---
@bp.route('/manage_appointments')
@login_required
@admin_required
def manage_appointments():
    """Visualiza todos os agendamentos feitos no sistema, incluindo o cliente."""
    
    # Busca todos os agendamentos, ordenados por data futura
    all_appointments = Appointment.query.order_by(Appointment.data_horario.asc()).all()
    
    return render_template('services/manage_appointments.html', 
                           title='Gerenciar Agendamentos', 
                           appointments=all_appointments,
                           now=datetime.now)
    


## --- ROTA: EDITAR SERVIÇO (Admin) ---
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
        
        # ----------------------------------------------------
        # 📌 LÓGICA ROBUSTA DE CONVERSÃO NUMÉRICA
        # ----------------------------------------------------
        try:
            # Pega o Preço:
            # 1. Usa um valor padrão '0' se estiver vazio.
            # 2. Converte vírgula para ponto.
            preco_str = request.form.get('preco', '0').replace(',', '.')
            
            # Pega a Duração:
            # 1. Usa um valor padrão '0' se estiver vazio.
            duracao_str = request.form.get('duracao_minutos', '0')
            
            # Converte para float e int
            preco = float(preco_str) 
            duracao_minutos = int(duracao_str)
            
            # 🚨 ADICIONE ESTA LINHA DE DEBUG
            print(f"DEBUG FINAL: Preço lido: {preco}, Duração lida: {duracao_minutos}") 
            # -------------------------------

            # 🚨 VALIDAÇÃO DE NEGÓCIO: Se um dos campos for zero ou negativo, rejeita.
            if preco < 0 or duracao_minutos <= 0:
                flash('O preço deve ser positivo e a duração deve ser maior que zero.', 'danger')
                return redirect(url_for('services.edit_service', service_id=service.id))

        except (ValueError, TypeError): 
            # Captura se o usuário digitou texto inválido (ex: "abc")
            flash('Preço e Duração devem ser números válidos. Por favor, verifique os campos.', 'danger')
            return redirect(url_for('services.edit_service', service_id=service.id))
        
        # ----------------------------------------------------
        
        # 1. Atualizar o objeto do serviço com os novos dados
        service.nome = nome
        service.descricao = descricao
        service.preco = preco
        service.duracao_minutos = duracao_minutos
        
        db.session.commit()
        
        flash(f'Serviço "{service.nome}" atualizado com sucesso!', 'success')
        return redirect(url_for('services.list_services'))

    # Para requisição GET, renderiza o formulário preenchido com os dados atuais
    return render_template('edit_service.html', 
                           title=f'Editar Serviço: {service.nome}', 
                           service=service)
    
    
## --- ROTA: DELETAR SERVIÇO (Admin) ---
@bp.route('/delete/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def delete_service(service_id):
    """Permite ao administrador deletar um serviço existente."""
    
    service = Service.query.get_or_404(service_id)
    
    # 📌 REGRAS DE NEGÓCIO: Verificação de Agendamentos Pendentes
    # Verifica se há algum agendamento 'Agendado' (ou não cancelado) para este serviço
    has_appointments = Appointment.query.filter(
        Appointment.service_id == service.id,
        Appointment.status.in_(['Agendado', 'Concluído']) # Exclui Cancelados
    ).first()
    
    if has_appointments:
        flash(f'Não é possível deletar o serviço "{service.nome}". Existem agendamentos associados.', 'danger')
        return redirect(url_for('services.list_services'))

    try:
        db.session.delete(service)
        db.session.commit()
        flash(f'Serviço "{service.nome}" removido permanentemente.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao deletar o serviço: {e}', 'danger')
        
    return redirect(url_for('services.list_services'))



# app/services/routes.py

@bp.route('/update_status/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def update_appointment_status(appointment_id):
    
    appointment = Appointment.query.get_or_404(appointment_id)
    new_status = request.form.get('status')
    valid_statuses = ['Agendado', 'Concluído', 'Cancelado', 'Reagendado']
    
    if new_status not in valid_statuses:
        # ... (flash de status inválido)
        return redirect(url_for('services.manage_appointments'))

    if appointment.status == new_status:
        # ... (flash de status inalterado)
        return redirect(url_for('services.manage_appointments'))

    try:
        # 1. ATUALIZA O OBJETO
        appointment.status = new_status
        # 2. TENTA SALVAR
        db.session.commit() # <-- PONTO DA FALHA
        flash(f'Status do agendamento atualizado para "{new_status}".', 'success')
    except Exception as e:
        # 3. FALHA E FAZ ROLLBACK
        db.session.rollback()
        # 🚨 Use o print(e) para ver o erro real no terminal
        print(f"ERRO DE DB: {e}") 
        flash(f'Erro ao atualizar o status. Tente novamente.', 'danger')
        
    return redirect(url_for('services.manage_appointments'))




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
    
    # 1. Tenta converter a string do formato HTML para datetime
    try:
        # O formato de entrada de datetime-local é YYYY-MM-DDTHH:MM
        new_datetime = datetime.strptime(new_datetime_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Formato de data e hora inválido. Use AAAA-MM-DD HH:MM.', 'danger')
        return redirect(url_for('services.manage_appointments'))

    # 🚨 VALIDAÇÃO DE DATA FUTURA (A CORREÇÃO) 🚨
    if new_datetime < datetime.now():
        flash('A data e hora do reagendamento não podem ser no passado. Por favor, selecione uma data futura.', 'danger')
        return redirect(url_for('services.manage_appointments'))
    # -----------------------------------------------

    # 2. Atualiza e salva no banco de dados
    try:
        # Atualiza a data e define o status como Reagendado
        appointment.data_horario = new_datetime
        appointment.status = 'Reagendado' 
        
        db.session.commit()
        flash(f'Agendamento #{appointment.id} reagendado com sucesso para {new_datetime.strftime("%d/%m/%Y às %H:%M")}.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO DE REAGENDAMENTO: {e}") 
        flash('Erro ao salvar o reagendamento no banco de dados. Tente novamente.', 'danger')
        
    return redirect(url_for('services.manage_appointments'))