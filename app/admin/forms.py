# app/admin/forms.py

from flask_wtf import FlaskForm
# 🟢 CORREÇÃO: Usando DecimalField para precisão monetária
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError
# A importação do modelo Service não é estritamente necessária aqui, mas é mantida
# from app.models import Service 

# ----------------------------------------------------
# 📌 FORMULÁRIO DE GERENCIAMENTO DE SERVIÇOS
# ----------------------------------------------------
class ServiceForm(FlaskForm):
    """
    Formulário para criar e editar serviços.
    """
    
    nome = StringField(
        'Nome do Serviço', 
        validators=[DataRequired(message="O nome do serviço é obrigatório."), 
                    Length(min=3, max=100, message="O nome deve ter entre 3 e 100 caracteres.")]
    )
    
    descricao = TextAreaField(
        'Descrição', 
        validators=[Length(max=500, message="A descrição não pode exceder 500 caracteres.")], 
        render_kw={"rows": 4}
    )
    
    # 🟢 CORREÇÃO: Usando DecimalField e definindo 'places=2'
    preco = DecimalField(
        'Preço (R$)', 
        validators=[DataRequired(message="O preço é obrigatório."), 
                    NumberRange(min=0.01, message="O preço deve ser maior que R$ 0,00.")],
        places=2 # Garante 2 casas decimais no formulário
    )
    
    duracao_minutos = IntegerField(
        'Duração (minutos)', 
        validators=[DataRequired(message="A duração é obrigatória."),
                    NumberRange(min=1, message="A duração deve ser de pelo menos 1 minuto.")],
        render_kw={"type": "number", "step": "5", "min": "1"}
    )

    is_active = BooleanField('Ativo para Agendamentos?', default=True)
    
    submit = SubmitField('Salvar Serviço')

    # Validador Customizado removido por simplicidade, pois a checagem é feita nas rotas