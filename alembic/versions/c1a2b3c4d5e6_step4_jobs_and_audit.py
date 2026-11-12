"""step4_jobs_and_audit

Revision ID: c1a2b3c4d5e6
Revises: e7dddff974c5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c1a2b3c4d5e6'
down_revision = 'e7dddff974c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'prompts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('output_schema', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'version', name='uq_prompt_name_version')
    )

    op.add_column('jobs', sa.Column('type', sa.String(), server_default='analyze', nullable=False))
    op.add_column('jobs', sa.Column('prompt_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('created_by', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('idempotency_key', sa.String(), nullable=True))
    op.create_foreign_key('fk_jobs_prompt_id', 'jobs', 'prompts', ['prompt_id'], ['id'])
    op.create_foreign_key('fk_jobs_created_by', 'jobs', 'users', ['created_by'], ['id'])
    op.create_unique_constraint('uq_job_tenant_idempotency_key', 'jobs', ['tenant_id', 'idempotency_key'])

    op.add_column('datasets', sa.Column('uploaded_by', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_datasets_uploaded_by', 'datasets', 'users', ['uploaded_by'], ['id'])

    op.alter_column('audit_log', 'user_id', existing_type=sa.UUID(), nullable=True)
    op.add_column('audit_log', sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        'eval_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('prompt_id', sa.UUID(), nullable=True),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('dataset_size', sa.Integer(), nullable=False),
        sa.Column('theme_score', sa.Float(), nullable=False),
        sa.Column('sentiment_f1', sa.Float(), nullable=False),
        sa.Column('groundedness', sa.Float(), nullable=False),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('eval_runs')
    op.drop_column('audit_log', 'detail')
    op.alter_column('audit_log', 'user_id', existing_type=sa.UUID(), nullable=False)
    op.drop_constraint('fk_datasets_uploaded_by', 'datasets', type_='foreignkey')
    op.drop_column('datasets', 'uploaded_by')
    op.drop_constraint('uq_job_tenant_idempotency_key', 'jobs', type_='unique')
    op.drop_constraint('fk_jobs_created_by', 'jobs', type_='foreignkey')
    op.drop_constraint('fk_jobs_prompt_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'idempotency_key')
    op.drop_column('jobs', 'created_by')
    op.drop_column('jobs', 'prompt_id')
    op.drop_column('jobs', 'type')
    op.drop_table('prompts')
