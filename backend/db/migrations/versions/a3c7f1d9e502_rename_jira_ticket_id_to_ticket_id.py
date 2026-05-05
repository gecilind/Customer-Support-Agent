"""rename jira_ticket_id to ticket_id

Revision ID: a3c7f1d9e502
Revises: fbaa44d8bc62
Create Date: 2026-05-04 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a3c7f1d9e502'
down_revision: Union[str, Sequence[str], None] = 'fbaa44d8bc62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_tickets_jira_ticket_id', table_name='tickets')
    op.alter_column('tickets', 'jira_ticket_id', new_column_name='ticket_id')
    op.create_index(op.f('ix_tickets_ticket_id'), 'tickets', ['ticket_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_tickets_ticket_id'), table_name='tickets')
    op.alter_column('tickets', 'ticket_id', new_column_name='jira_ticket_id')
    op.create_index('ix_tickets_jira_ticket_id', 'tickets', ['jira_ticket_id'], unique=True)
