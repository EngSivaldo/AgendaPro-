"""Adiciona Soft Delete em Service, Auditoria em Appointment e Unicidade em Service

Revision ID: a64ffa28ec58
Revises: 
Create Date: 2025-11-29 17:31:51.977923

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone # 📌 Importação necessária para preencher datas


# revision identifiers, used by Alembic.
revision = 'a64ffa28ec58'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### comandos auto gerados pelo Alembic - por favor, ajuste! ###
    
    # ---------------------------------------------------------------------
    # 📌 CORREÇÃO: 'appointment.created_at' (Adição NOT NULL em 3 passos)
    # ---------------------------------------------------------------------
    
    # 1. Adicionar a coluna 'created_at' permitindo NULL temporariamente (Já gerado)
    with op.batch_alter_table('appointment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    # 2. Preencher a coluna com um valor padrão (data atual em UTC)
    data_atual = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    op.execute(
        f"UPDATE appointment SET created_at = '{data_atual}' WHERE created_at IS NULL"
    )

    # 3. Alterar a coluna para NOT NULL
    with op.batch_alter_table('appointment', schema=None) as batch_op:
        # Nota: O Alembic/SQLAlchemy geralmente não precisa do tipo aqui, mas a alteração para nullable=False é a chave
        batch_op.alter_column('created_at', nullable=False)


    # ---------------------------------------------------------------------
    # 📌 CORREÇÃO: 'service.is_active' (Adição NOT NULL em 3 passos)
    # ---------------------------------------------------------------------

    # 1. Adicionar a coluna 'is_active' permitindo NULL temporariamente (Já gerado)
    with op.batch_alter_table('service', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True))
    
    # 2. Preencher a coluna com TRUE para todos os serviços existentes
    op.execute("UPDATE service SET is_active = TRUE WHERE is_active IS NULL")
    
    # 3. Alterar a coluna para NOT NULL
    with op.batch_alter_table('service', schema=None) as batch_op:
        batch_op.alter_column('is_active', nullable=False)


    # ---------------------------------------------------------------------
    # 📌 REUSO DOS COMANDOS ORIGINAIS (Finalizando constraints/indices)
    # ---------------------------------------------------------------------
    
    # Unicidade em 'service.nome' (Renomeado o None para um nome explícito)
    with op.batch_alter_table('service', schema=None) as batch_op:
        # Nota: Você pode precisar ajustar o nome 'uq_service_nome' se já houver um.
        # Use o nome gerado pelo Alembic se preferir, mas 'uq_service_nome' é mais legível.
        batch_op.create_unique_constraint('uq_service_nome', ['nome'])

    # Índice em 'user.email'
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Se 'email' no seu modelo é unique=True, a linha abaixo deveria ser: 
        # batch_op.create_index('idx_user_email', ['email'], unique=True)
        # Mantive unique=False conforme o Alembic gerou, mas confira seu modelo.
        batch_op.create_index('idx_user_email', ['email'], unique=False) # Se for apenas um índice, ou unique=True se for constraint de unicidade


    # ### fim dos comandos auto gerados pelo Alembic ###


def downgrade():
    # ### commands auto gerados pelo Alembic - por favor, ajuste! ###
    
    # Reverte o índice de usuário
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index('idx_user_email')

    # Reverte a unicidade e o is_active
    with op.batch_alter_table('service', schema=None) as batch_op:
        batch_op.drop_constraint('uq_service_nome', type_='unique') # Usa o nome definido em upgrade
        batch_op.drop_column('is_active')

    # Reverte o created_at
    with op.batch_alter_table('appointment', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    # ### fim dos comandos auto gerados pelo Alembic ###