from functools import wraps 
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db, mail
from app.decorators import admin_required
from datetime import datetime, timedelta, date
from app.models import Service, Appointment, User 
from sqlalchemy import or_, func, and_
from flask_mail import Message # Importa a classe Message
from . import bp
from app.tasks import send_appointment_reminder 
# ----------------------------------------------------------------------
# 📌 1. DEFINIÇÃO DO BLUEPRINT
# ----------------------------------------------------------------------
bp = Blueprint('services', __name__, url_prefix='/services', template_folder='templates')

# ----------------------------------------------------
# 📌 2. FUNÇÃO AUXILIAR DE ENVIO DE EMAIL
# ----------------------------------------------------
def send_appointment_email(appointment, subject, status):
    """
    Envia email de notificação para o usuário sobre o agendamento.
    :param appointment: Objeto Appointment do DB
    :param subject: Assunto do Email
    :param status: Status da ação (e.g., 'Confirmado', 'Cancelado', 'Reagendado')
    """
    
    # Cria o objeto Message
    msg = Message(
        subject,
        recipients=[appointment.user.email] 
    )
    
    # Conteúdo de texto simples
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
        print(f"ERRO CRÍTICO AO ENVIAR EMAIL: Verifique a configuração SMTP e a Senha de App. Erro: {e}")


# ----------------------------------------------------
# 📌 3. FUNÇÕES AUXILIARES (has_conflict e get_available_slots)
# ----------------------------------------------------
# app/services/routes.py (Ajuste na FUNÇÃO AUXILIAR has_conflict)

def has_conflict(service_id, desired_start_time, appointment_id_to_exclude=None):
    """Verifica se o horário desejado conflita com agendamentos existentes, 
       excluindo um agendamento específico."""
       
    service = Service.query.get(service_id)
    if not service:
        return False
        
    duration = service.duracao_minutos
    desired_end_time = desired_start_time + timedelta(minutes=duration)

    start_of_day = datetime.combine(desired_start_time.date(), datetime.min.time())
    end_of_day_exclusive = start_of_day + timedelta(days=1) 

    # 📌 NOVO: Adiciona filtro para excluir o agendamento que está sendo editado
    query = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_of_day,
        Appointment.data_horario < end_of_day_exclusive
    ).filter(Appointment.status == 'Agendado')
    
    if appointment_id_to_exclude:
        query = query.filter(Appointment.id != appointment_id_to_exclude)
        
    all_appointments_on_day = query.all()
    # ... (O restante da lógica de loop 'for existing_appointment in all_appointments_on_day:' permanece o mesmo) ...
    
    for existing_appointment in all_appointments_on_day:
        # ... (sua lógica de conflito existente) ...
         existing_service_duration = existing_appointment.servico.duracao_minutos 
         existing_start_time = existing_appointment.data_horario
         existing_end_time = existing_start_time + timedelta(minutes=existing_service_duration)

         if desired_start_time < existing_end_time and desired_end_time > existing_start_time:
             return True 

    return False

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
        
        # Acessar as propriedades antes de enviar o email para garantir que as relações foram carregadas
        new_appointment.user.email 
        new_appointment.servico.nome
        
        # 5. Envio do Email de Confirmação Imediata
        send_appointment_email(
            appointment=new_appointment, 
            subject="Confirmação de Agendamento Realizado", 
            status='Confirmado'
        )
        
        # ========================================================
        # 📌 6. AGENDAMENTO DO LEMBRETE CELERY (24 HORAS ANTES)
        # ========================================================
        
        # Calcula o tempo para o lembrete (24 horas antes)
        reminder_time = new_appointment.data_horario - timedelta(hours=24)
        
        # Verifica se o tempo de lembrete ainda está no futuro
        if reminder_time > datetime.now():
            send_appointment_reminder.apply_async(
                args=[new_appointment.id], # Passa o ID do novo agendamento
                eta=reminder_time           # Agendado para ser executado em 'reminder_time'
            )
            flash_message = 'Agendamento realizado com sucesso! Um email de confirmação foi enviado e um lembrete foi agendado.'
        else:
            flash_message = 'Agendamento realizado com sucesso! Um email de confirmação foi enviado.'
        
        flash(flash_message, 'success')
        return redirect(url_for('services.my_appointments'))

    return render_template('services/book.html', title='Novo Agendamento', services=services, now=datetime.now)
    
    
## --- ROTA DE ADMINISTRAÇÃO (DASHBOARD) ---
@bp.route('/dashboard') # Rota será /services/dashboard
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
    
    # 💡 NOVO: Envio de email de cancelamento
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
            # 💡 CORREÇÃO: Trata a vírgula para ponto ao converter para float
            preco_str = request.form.get('preco').replace(',', '.') 
            preco = float(preco_str) 
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
        # 📌 LÓGICA ROBUSTA DE CONVERSÃO NUMÉRICA (CÓDIGO LIMPO DE \ua0)
        # ----------------------------------------------------
        try:
            # Pega o Preço e converte vírgula para ponto.
            preco_str = request.form.get('preco', '0').replace(',', '.')
            
            # Pega a Duração
            duracao_str = request.form.get('duracao_minutos', '0')
            
            # Converte para float e int
            preco = float(preco_str) 
            duracao_minutos = int(duracao_str)
            
            # 🚨 VALIDAÇÃO DE NEGÓCIO: Se um dos campos for zero ou negativo, rejeita.
            if preco < 0 or duracao_minutos <= 0:
                flash('O preço deve ser positivo e a duração deve ser maior que zero.', 'danger')
                return redirect(url_for('services.edit_service', service_id=service.id))

        except (ValueError, TypeError): 
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
    return render_template('services/edit_service.html', # 💡 CORRIGIDO o caminho do template, se necessário
                           title=f'Editar Serviço: {service.nome}', 
                           service=service)
    
    
## --- ROTA: DELETAR SERVIÇO (Admin) ---
# app/services/routes.py (ou o arquivo onde esta rota está definida)

@bp.route('/delete/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def delete_service(service_id):
    """Permite ao administrador deletar um serviço existente, se não houver agendamentos ATIVOS."""
    
    # 1. Busca o serviço
    service = Service.query.get_or_404(service_id)
    service_name = service.nome # Captura o nome para uso nas mensagens
    
    # 📌 REGRAS DE NEGÓCIO: Verificação de Agendamentos ATIVOS/CONCLUÍDOS
    # Busca por qualquer agendamento com status que BLOQUEIA a exclusão
    has_active_appointments = Appointment.query.filter(
        Appointment.service_id == service.id,
        Appointment.status.in_(['Agendado', 'Concluído'])
    ).first()
    
    if has_active_appointments:
        # Bloqueia a exclusão e envia mensagem instrutiva
        # 💡 MELHORIA: A mensagem agora sugere a ação corretiva (cancelar/remover).
        flash(f'ERRO: O serviço "{service_name}" não pode ser excluído. Existem agendamentos ativos ou concluídos ligados a ele. Cancele ou remova esses agendamentos primeiro.', 'danger')
        # Presume que a listagem de serviços do Admin é a rota correta de retorno
        return redirect(url_for('services.list_services')) # Mantido conforme seu pedido
        
    # Se não houver agendamentos ativos/concluídos
    try:
        db.session.delete(service)
        db.session.commit()
        
        # 💡 MELHORIA: Mensagem clara de sucesso e permanentemente removido
        flash(f'Serviço "{service_name}" removido permanentemente.', 'success') 
        
    except Exception as e:
        # Tratamento de erro inesperado (ex: falha de conexão com DB)
        db.session.rollback()
        print(f"Erro detalhado no servidor ao deletar o serviço: {e}")
        flash(f'Ocorreu um erro interno inesperado ao deletar o serviço "{service_name}".', 'danger')
        
    return redirect(url_for('services.list_services')) # Mantido conforme seu pedido


## --- ROTA: ATUALIZAR STATUS (Admin) ---
@bp.route('/update_status/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def update_appointment_status(appointment_id):
    
    appointment = Appointment.query.get_or_404(appointment_id)
    new_status = request.form.get('status')
    valid_statuses = ['Agendado', 'Concluído', 'Cancelado', 'Reagendado']
    
    if new_status not in valid_statuses:
        flash('Status inválido.', 'danger')
        return redirect(url_for('services.manage_appointments'))

    # 📌 NOVO: Pega o status atual ANTES de alterá-lo
    old_status = appointment.status 

    if old_status == new_status:
        flash('Status inalterado.', 'info')
        return redirect(url_for('services.manage_appointments'))

    try:
        # 1. ATUALIZA O OBJETO
        appointment.status = new_status
        # 2. TENTA SALVAR
        db.session.commit() 

        # 3. 📢 ENVIO DE EMAIL: Notifica o cliente sobre a mudança
        # A notificação só é enviada se o status realmente mudou (já garantido pelo if acima)
        send_appointment_email(
            appointment=appointment, 
            subject=f"ATUALIZAÇÃO DE STATUS: Agendamento ID {appointment_id}", 
            status=new_status # Passa o novo status para o corpo do email
        )
        
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
    
    # 1. Tenta converter a string do formato HTML para datetime
    try:
        new_datetime = datetime.strptime(new_datetime_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Formato de data e hora inválido.', 'danger')
        return redirect(url_for('services.manage_appointments'))

    # 2. 🚨 VALIDAÇÃO DE DATA FUTURA 🚨
    if new_datetime < datetime.now():
        flash('A data e hora do reagendamento não podem ser no passado.', 'danger')
        return redirect(url_for('services.manage_appointments'))
        
    # 3. 🚨 VALIDAÇÃO DE CONFLITO 🚨
    # Passa o ID do agendamento atual para que ele seja ignorado na verificação
    if has_conflict(appointment.service_id, new_datetime, appointment_id_to_exclude=appointment.id):
        flash('ERRO: O novo horário conflita com outro agendamento existente. Selecione outro slot.', 'danger')
        return redirect(url_for('services.manage_appointments'))


    # 4. Atualiza e salva no banco de dados
    try:
        # Atualiza a data e define o status como Reagendado
        appointment.data_horario = new_datetime
        appointment.status = 'Reagendado' 
        
        db.session.commit()
        
        # 5. 📢 ENVIO DE EMAIL de reagendamento (já estava OK)
        send_appointment_email(
            appointment=appointment, 
            subject="REAGENDAMENTO de Serviço", 
            status='Reagendado'
        )
        
        # 6. 🚨 (OPCIONAL) CANCELAMENTO DO LEMBRETE ANTIGO E AGENDAMENTO DO NOVO
        # Aqui você deveria cancelar o Celery task antigo e agendar um novo, 
        # mas como você não tem o ID do task, essa é uma melhoria futura.
        
        flash(f'Agendamento #{appointment.id} reagendado com sucesso para {new_datetime.strftime("%d/%m/%Y às %H:%M")} e cliente notificado.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO DE REAGENDAMENTO: {e}") 
        flash('Erro ao salvar o reagendamento no banco de dados. Tente novamente.', 'danger')
        
    return redirect(url_for('services.manage_appointments'))



# Função auxiliar para garantir que apenas administradores acessem
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Acesso restrito a administradores.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Rota para o Relatório de Faturamento
# Rota para o Relatório de Faturamento
@bp.route('/admin/reports/billing', methods=['GET'])
@login_required
@admin_required
def billing_report():
    """Calcula e exibe o faturamento total com base nos agendamentos concluídos."""
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = Appointment.query.filter_by(status='Concluído')
    
    # --- NOVO BLOCO: Definir padrão (Mês Atual) ---
    today = date.today()
    start_of_month = datetime(today.year, today.month, 1)
    
    # Calcula o último dia do mês atual (ou próximo mês)
    try:
        # Tenta ir para o dia 1 do próximo mês e subtrai 1 dia
        end_of_month = datetime(today.year, today.month + 1, 1) - timedelta(seconds=1) 
    except ValueError:
        # Se for Dezembro (month + 1 = 13), vai para Janeiro do próximo ano
        end_of_month = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)

    # 💡 DEFINIÇÕES INICIAIS (serão usadas se não houver filtro)
    start_date_filter = start_of_month
    end_date_filter = end_of_month
    # -----------------------------------------------

    # 1. Lógica do Período (Filtro do Usuário)
    if start_date_str and end_date_str:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # Ajusta para incluir o dia inteiro
            end_datetime = datetime.combine(end_date_obj.date(), datetime.max.time())
            
            # 💡 SOBRESCREVE OS FILTROS PARA A QUERY E PARA O DISPLAY
            start_date_filter = start_date_obj
            end_date_filter = end_datetime
            
        except ValueError:
            flash('Formato de data inválido.', 'danger')
            return redirect(url_for('services.billing_report'))
            
    # Filtra a Query com base nos filtros definidos (padrão ou pelo usuário)
    query = query.filter(Appointment.data_horario >= start_date_filter,
                         Appointment.data_horario <= end_date_filter)

    # 2. Execução da Consulta
    completed_appointments = query.all()

    # 3. Cálculo do Faturamento
    total_revenue = sum(appt.servico.preco for appt in completed_appointments)
    
    # 4. Retorno: Usa os filtros ATUAIS (start_date_filter/end_date_filter) para formatar
    return render_template('services/billing_report.html', 
                           title='Relatório de Faturamento',
                           total_revenue=total_revenue,
                           appointments=completed_appointments,
                           
                           # Passa a data formatada para ser usada nos INPUTS HTML (valor='2025-11-01')
                           start_date=start_date_filter.strftime('%Y-%m-%d'),
                           end_date=end_date_filter.strftime('%Y-%m-%d'),
                           
                           datetime=datetime 
                           )