"""initial_schema

Revision ID: e7dddff974c5
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

revision = 'e7dddff974c5'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('tenants',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('datasets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('source_type', sa.String(), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_datasets_tenant_id'), 'datasets', ['tenant_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'email', name='uq_user_tenant_email')
    )
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('entity_type', sa.String(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_tenant_id'), 'audit_log', ['tenant_id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('prompt_version', sa.Text(), nullable=True),
    sa.Column('model', sa.String(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_tenant_id'), 'jobs', ['tenant_id'], unique=False)
    op.create_table('records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('external_id', sa.String(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dataset_id', 'external_id', name='uq_record_dataset_external_id')
    )
    op.create_index(op.f('ix_records_tenant_id'), 'records', ['tenant_id'], unique=False)
    op.create_table('chunks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('record_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['record_id'], ['records.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chunks_tenant_id'), 'chunks', ['tenant_id'], unique=False)
    op.create_table('insights',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insights_tenant_id'), 'insights', ['tenant_id'], unique=False)
    op.create_table('llm_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('prompt_version', sa.String(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('cache_hit', sa.Boolean(), nullable=False),
    sa.Column('fallback_used', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_calls_tenant_id'), 'llm_calls', ['tenant_id'], unique=False)
    op.create_table('insight_sources',
    sa.Column('insight_id', sa.UUID(), nullable=False),
    sa.Column('record_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['insight_id'], ['insights.id'], ),
    sa.ForeignKeyConstraint(['record_id'], ['records.id'], ),
    sa.PrimaryKeyConstraint('insight_id', 'record_id')
    )
def downgrade() -> None:
    op.drop_table('insight_sources')
    op.drop_index(op.f('ix_llm_calls_tenant_id'), table_name='llm_calls')
    op.drop_table('llm_calls')
    op.drop_index(op.f('ix_insights_tenant_id'), table_name='insights')
    op.drop_table('insights')
    op.drop_index(op.f('ix_chunks_tenant_id'), table_name='chunks')
    op.drop_table('chunks')
    op.drop_index(op.f('ix_records_tenant_id'), table_name='records')
    op.drop_table('records')
    op.drop_index(op.f('ix_jobs_tenant_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_audit_log_tenant_id'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_datasets_tenant_id'), table_name='datasets')
    op.drop_table('datasets')
    op.drop_table('tenants')
