from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db, mail
from app.decorators import admin_required 
from datetime import datetime, timedelta, date
from app.models import Service, Appointment, User 
from sqlalchemy import or_, func, and_
from sqlalchemy.exc import IntegrityError 
from flask_mail import Message
from app.tasks import send_appointment_reminder 
# 📌 Importação do Formulário de Serviço
from app.admin.forms import ServiceForm 
# Importação necessária para usar o update direto no banco de dados
from sqlalchemy import text 

# ----------------------------------------------------------------------
# 📌 1. DEFINIÇÃO DO BLUEPRINT
# ----------------------------------------------------------------------
# Prefixo /admin para isolar todas as rotas de administração
bp = Blueprint('admin', __name__, url_prefix='/admin')

# Supondo que 'db' é o seu objeto SQLAlchemy global
# e 'bp' é o seu Blueprint de administração.

@bp.teardown_request
def shutdown_session(exception=None):
    """Garante que a sessão do SQLAlchemy seja removida após cada requisição."""
    db.session.remove()
    
# Importante: Se você estiver usando um 'scoped_session'
# manualmente, o código pode ser:
# from your_app.database import Session
# Session.remove()

# ----------------------------------------------------
# 📌 2. FUNÇÃO AUXILIAR DE ENVIO DE EMAIL (Reusada)
# ----------------------------------------------------
# Nota: Idealmente, mover para um módulo utils.
def send_appointment_email(appointment, subject, status):
    """
    Envia email de notificação para o usuário sobre o agendamento.
    (Necessário para notificar sobre alteração de status/reagendamento)
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
        print(f"ERRO CRÍTICO AO ENVIAR EMAIL: Erro: {e}")


# ----------------------------------------------------
# 📌 3. FUNÇÃO AUXILIAR has_conflict (Reusada no Reagendamento)
# ----------------------------------------------------
def has_conflict(service_id, desired_start_time, appointment_id_to_exclude=None):
    """
    Verifica se o horário desejado conflita com agendamentos existentes.
    """
    service = Service.query.get(service_id)
    if not service:
        return False
        
    duration = service.duracao_minutos
    desired_end_time = desired_start_time + timedelta(minutes=duration)

    start_of_day = datetime.combine(desired_start_time.date(), datetime.min.time())
    end_of_day_exclusive = start_of_day + timedelta(days=1) 

    query = Appointment.query.join(Service).filter(
        Appointment.data_horario >= start_of_day,
        Appointment.data_horario < end_of_day_exclusive
    ).filter(Appointment.status == 'Agendado')
    
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
    

# ----------------------------------------------------
# 📌 4. ROTAS MIGRADA DE ADMINISTRAÇÃO
# ----------------------------------------------------

## --- DASHBOARD ADMIN --- 
@bp.route('/dashboard') 
@login_required
@admin_required
def admin_dashboard():
    """Renderiza o template do Painel de Administração."""
    return render_template('admin_dashboard.html', title='Dashboard Admin')


## --- GERENCIAR AGENDAMENTOS ---
@bp.route('/appointments')
@login_required
@admin_required
def manage_appointments():
    """Visualiza todos os agendamentos feitos no sistema, incluindo o cliente."""
    all_appointments = Appointment.query.order_by(Appointment.data_horario.asc()).all()
    
    return render_template('services/manage_appointments.html', 
                           title='Gerenciar Agendamentos', 
                           appointments=all_appointments,
                           now=datetime.now)


## --- LISTAR SERVIÇOS ---
@bp.route('/services')
@login_required
@admin_required
def list_services():
    """Visualiza todos os serviços cadastrados (ativos e inativos) (Apenas Admin)"""
    # O Admin vê TODOS os serviços para gerenciar o status 'is_active'
    db.session.expire_all()
    
    services = Service.query.order_by(Service.is_active.desc(), Service.nome.asc()).all()
    
    return render_template('services/list.html', title='Gerenciar Serviços', services=services)


@bp.route('/service/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_service():
    """Permite ao administrador criar um novo serviço usando WTForms."""
    form = ServiceForm() 
    
    if form.validate_on_submit(): 
        # Validação de Unicidade
        if Service.query.filter_by(nome=form.nome.data).first():
            flash(f'O nome do serviço "{form.nome.data}" já existe. Escolha outro nome.', 'danger')
            return render_template('services/new.html', title='Adicionar Serviço', form=form)

        new_service = Service(
            nome=form.nome.data,
            descricao=form.descricao.data,
            preco=form.preco.data,
            duracao_minutos=form.duracao_minutos.data,
            is_active=True 
        )
        
        try:
            db.session.add(new_service)
            db.session.commit()
            flash(f'Serviço "{new_service.nome}" criado e **ATIVADO** com sucesso!', 'success')
            return redirect(url_for('admin.list_services')) 
            
        except IntegrityError:
            db.session.rollback()
            flash(f'Erro de integridade: Nome duplicado (cheque o banco de dados).', 'danger')
            return redirect(url_for('admin.create_service'))
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar serviço: {e}")
            flash('Ocorreu um erro interno ao criar o serviço.', 'danger')
            return redirect(url_for('admin.create_service'))

    # Para requisição GET ou falha na validação
    return render_template('services/new.html', title='Adicionar Serviço', form=form)


## --- EDITAR SERVIÇO (REFATORADO com WTForms) ---
@bp.route('/service/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_service(service_id):
    """Permite ao administrador editar um serviço existente usando WTForms."""
    
    service = Service.query.get_or_404(service_id)
    # Preenche o formulário com os dados atuais do serviço para GET
    form = ServiceForm(obj=service) 
    
    if form.validate_on_submit():
        # Lógica de validação de unicidade (excluindo o próprio serviço)
        existing_service = Service.query.filter(
            Service.nome == form.nome.data,
            Service.id != service_id
        ).first()

        if existing_service:
            flash(f'O nome do serviço "{form.nome.data}" já existe em outro serviço. Escolha outro nome.', 'danger')
            # Retorna para o template com os dados modificados do formulário
            return render_template('services/edit_service.html', title=f'Editar Serviço: {service.nome}', form=form, service=service)
        
        try:
            # Atualiza o objeto service com os dados validados do formulário
            service.nome = form.nome.data
            service.descricao = form.descricao.data
            service.preco = form.preco.data
            service.duracao_minutos = form.duracao_minutos.data
            service.is_active = form.is_active.data 
            
            db.session.commit()
            
            flash(f'Serviço "{service.nome}" atualizado com sucesso!', 'success')
            return redirect(url_for('admin.list_services'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao editar serviço: {e}")
            flash('Erro ao salvar as alterações.', 'danger')
            return redirect(url_for('admin.edit_service', service_id=service.id))


    # Para requisição GET ou falha na validação
    # O form.data já está populado com obj=service para o GET, ou com POST data para falhas
    return render_template('services/edit_service.html', 
                           title=f'Editar Serviço: {service.nome}', 
                           form=form,
                           service=service) 


## --- TOGGLE ATIVAR/DESATIVAR (AJAX-READY) ---
@bp.route('/service/toggle_active/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def toggle_service_active(service_id):
    """
    Alterna o status is_active de um serviço. Retorna JSON para uso com AJAX.
    """
    
    # 1. ROLLBACK DEFENSIVO: Limpa quaisquer alterações pendentes.
    db.session.rollback()

    service = Service.query.get(service_id)

    if service is None:
        # Retorna JSON de falha (código 404)
        return jsonify({'success': False, 'message': 'Serviço não encontrado.'}), 404

    nome_servico = service.nome
    novo_status = not service.is_active
    action = 'ativado' if novo_status else 'desativado'
    
    try:
        # 2. LIMPEZA ADICIONAL: Remove o objeto *atual* da sessão (se houver).
        db.session.expunge(service) 
        
        # 3. EXECUTA O UPDATE DIRETO NO BANCO DE DADOS (isolamento total)
        Service.query.filter_by(id=service_id).update(
            {'is_active': novo_status}
        )
        
        db.session.commit()
        
        # 4. FORÇA EXPIRAÇÃO: Garante que a próxima requisição (se houver) leia os dados novos.
        db.session.expire_all() 
        
        # ✅ Retorne JSON de Sucesso para o JavaScript
        return jsonify({
            'success': True, 
            'message': f'Serviço "{nome_servico}" {action} com sucesso.', 
            'new_status': novo_status
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"[ERRO CRÍTICO] Falha ao executar UPDATE para Service ID {service_id}: {e}") 
        
        # ❌ Retorne JSON de Falha para o JavaScript (código 500)
        return jsonify({'success': False, 'message': 'Erro ao atualizar o status. Falha no banco de dados.'}), 500


# --- ROTA: DELETE (Redirecionamento) ---
@bp.route('/service/delete/<int:service_id>', methods=['POST'])
@login_required
@admin_required
def delete_service_redirect(service_id):
    """Redireciona a rota /delete para a rota unificada de toggle (Soft Delete)."""
    # A rota de delete/deactivate no template deve chamar admin.toggle_service_active
    # Nota: Com AJAX, esta rota se torna obsoleta, mas mantemos para evitar 404.
    return redirect(url_for('admin.toggle_service_active', service_id=service_id))


## --- ROTA: ATUALIZAR STATUS ---
@bp.route('/appointment/update_status/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def update_appointment_status(appointment_id):
    """Permite ao administrador alterar o status de um agendamento."""
    
    appointment = Appointment.query.get_or_404(appointment_id)
    new_status = request.form.get('status') 
    valid_statuses = ['Agendado', 'Concluído', 'Cancelado', 'Reagendado']
    
    if new_status not in valid_statuses:
        flash('Status inválido fornecido.', 'danger')
        return redirect(url_for('admin.manage_appointments'))

    old_status = appointment.status 

    if old_status == new_status:
        flash('Status inalterado.', 'info')
        return redirect(url_for('admin.manage_appointments'))

    flash_message_override = None

    if new_status == 'Concluído':
        now = datetime.now()
        
        if appointment.data_horario > now:
            # Altera a data agendada para o momento da conclusão para fins de faturamento
            appointment.data_horario = now
            
            flash_message_override = (
                f"Status do Agendamento ID {appointment_id} alterado para **Concluído**. "
                f"A data original foi atualizada para a data e hora atuais para fins de faturamento."
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
        
        if flash_message_override:
            flash(flash_message_override, 'warning')
        else:
            flash(f'Status do agendamento atualizado para "{new_status}" e cliente notificado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRO DE DB ao atualizar status: {e}")
        flash(f'Erro ao atualizar o status. Tente novamente.', 'danger')
        
    return redirect(url_for('admin.manage_appointments'))


## --- ROTA: REAGENDAR ---
@bp.route('/appointment/reschedule/<int:appointment_id>', methods=['POST'])
@login_required
@admin_required
def reschedule_appointment(appointment_id):
    """Permite ao administrador alterar a data e o status de um agendamento."""
    
    appointment = Appointment.query.get_or_404(appointment_id)
    new_datetime_str = request.form.get('new_datetime')
    
    if not new_datetime_str:
        flash('A nova data e hora para o reagendamento são obrigatórias.', 'danger')
        return redirect(url_for('admin.manage_appointments'))
    
    try:
        new_datetime = datetime.strptime(new_datetime_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Formato de data e hora inválido.', 'danger')
        return redirect(url_for('admin.manage_appointments'))

    # 1. Validação de Data Futura
    if new_datetime < datetime.now():
        flash('A data e hora do reagendamento não podem ser no passado.', 'danger')
        return redirect(url_for('admin.manage_appointments'))
        
    # 2. VALIDAÇÃO DE CONFLITO
    if has_conflict(appointment.service_id, new_datetime, appointment_id_to_exclude=appointment.id):
        flash('ERRO: O novo horário conflita com outro agendamento existente. Selecione outro slot.', 'danger')
        return redirect(url_for('admin.manage_appointments'))


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
        
        # Reagendar o lembrete Celery, se necessário
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
        
    return redirect(url_for('admin.manage_appointments'))


## --- Rota para o Relatório de Faturamento ---
@bp.route('/reports/billing', methods=['GET'])
@login_required
@admin_required
def billing_report():
    """Calcula e exibe o faturamento total com base nos agendamentos concluídos."""
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # --- 1. Determinação do Período (Padrão: Mês Atual) ---
    today = date.today()
    
    if not start_date_str or not end_date_str:
        start_date_filter = datetime(today.year, today.month, 1)
        
        try:
            # Fim do mês 
            end_date_filter = datetime(today.year, today.month + 1, 1) - timedelta(seconds=1) 
        except ValueError:
            # Passa para janeiro do próximo ano
            end_date_filter = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
            
    # --- Se datas FORAM fornecidas ---
    else:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # Ajusta para incluir o dia inteiro (até 23:59:59)
            start_date_filter = start_date_obj
            end_date_filter = datetime.combine(end_date_obj.date(), datetime.max.time())
            
        except ValueError:
            flash('Formato de data inválido.', 'danger')
            return redirect(url_for('admin.billing_report'))
            
    # 2. Construção da Query Base
    base_filter = [Appointment.status == 'Concluído']
    base_filter.append(Appointment.data_horario >= start_date_filter)
    base_filter.append(Appointment.data_horario <= end_date_filter)

    # 3. Execução do Cálculo SQL
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