"""Add compliance & auditing tables.

Adds tables for:
  - consent_records: User consent management (GDPR)
  - pii_inventory: PII field registry for DSAR
  - data_retention_purges: Audit trail of data purges
  - audit_log_chain: SHA-256 chain-linking for immutable audit
  - regulatory_reports: Generated regulatory report history
  - risk_disclosures: Risk disclaimer history
  - archive_manifest: Cold-storage archive references
  - data_classification_rules: Classification rules for data types

Adds write-once trigger for audit_logs table (PostgreSQL only).

Revision ID: 004_compliance
Revises: 003_performance
Create Date: 2024-07-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_compliance"
down_revision: Union[str, None] = "003_performance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add compliance tables."""

    # Enum types for compliance
    consent_type = postgresql.ENUM(
        'terms_of_service', 'privacy_policy', 'risk_disclosure',
        'data_processing', 'marketing', 'third_party_sharing',
        'cookies', 'trading_authorization',
        name='consenttype', create_type=False,
    )
    consent_status = postgresql.ENUM(
        'granted', 'withdrawn', 'expired',
        name='consentstatus', create_type=False,
    )
    pii_category = postgresql.ENUM(
        'public', 'internal', 'sensitive', 'restricted',
        name='piicategory', create_type=False,
    )
    data_retention_category = postgresql.ENUM(
        'trades', 'decisions', 'audit_logs', 'notifications',
        'sessions', 'pi_data', 'consent', 'risk_disclosures',
        'regulatory_reports',
        name='dataretentioncategory', create_type=False,
    )
    classification_level = postgresql.ENUM(
        'public', 'internal', 'confidential', 'restricted',
        name='classificationlevel', create_type=False,
    )
    purge_status = postgresql.ENUM(
        'pending', 'archived', 'deleted', 'failed',
        name='purgestatus', create_type=False,
    )

    # Create enums
    for enum in [consent_type, consent_status, pii_category,
                 data_retention_category, classification_level, purge_status]:
        enum.create(op.get_bind(), checkfirst=True)

    # Consent Records table
    op.create_table(
        'consent_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('consent_type', consent_type, nullable=False),
        sa.Column('status', consent_status, nullable=False,
                  server_default='granted'),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('consent_version', sa.String(50), nullable=False,
                  server_default='1.0'),
        sa.Column('granted_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_consent_user_type', 'consent_records',
                    ['user_id', 'consent_type'])
    op.create_index('idx_consent_status', 'consent_records',
                    ['status', 'created_at'])

    # PII Inventory table
    op.create_table(
        'pii_inventory',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('category', pii_category, nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('is_required', sa.Boolean, nullable=False,
                  server_default='false'),
        sa.Column('retention_days', sa.Integer, nullable=True),
        sa.Column('masking_rule', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_pii_category', 'pii_inventory', ['category'])
    op.create_index('idx_pii_table_field', 'pii_inventory',
                    ['table_name', 'field_name'], unique=True)

    # Data Retention Purges table
    op.create_table(
        'data_retention_purges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category', data_retention_category, nullable=False),
        sa.Column('status', purge_status, nullable=False),
        sa.Column('records_purged', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('older_than_days', sa.Integer, nullable=False),
        sa.Column('archive_path', sa.String(500), nullable=True),
        sa.Column('archive_size_bytes', sa.Integer, nullable=True),
        sa.Column('archive_hash', sa.String(128), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('purged_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('purged_by', sa.String(100), nullable=True),
        sa.Column('was_dry_run', sa.Boolean, nullable=False,
                  server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_purge_category_status', 'data_retention_purges',
                    ['category', 'status'])
    op.create_index('idx_purge_timestamp', 'data_retention_purges',
                    ['purged_at'])

    # Audit Log Chain table (SHA-256 linking)
    op.create_table(
        'audit_log_chain',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_log_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('audit_logs.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('previous_hash', sa.String(128), nullable=True),
        sa.Column('current_hash', sa.String(128), nullable=False, unique=True),
        sa.Column('chain_index', sa.Integer, nullable=False),
        sa.Column('witness_tx_id', sa.String(500), nullable=True),
        sa.Column('witness_location', sa.String(500), nullable=True),
        sa.Column('witness_timestamp', sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_chain_audit_id', 'audit_log_chain',
                    ['audit_log_id'], unique=True)
    op.create_index('idx_chain_prev_hash', 'audit_log_chain',
                    ['previous_hash'])

    # Regulatory Reports table
    op.create_table(
        'regulatory_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('report_type', sa.String(100), nullable=False),
        sa.Column('report_format', sa.String(10), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_size_bytes', sa.Integer, nullable=True),
        sa.Column('content_hash', sa.String(128), nullable=True),
        sa.Column('parameters', postgresql.JSONB, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_reg_report_type_period', 'regulatory_reports',
                    ['report_type', 'period_start'])
    op.create_index('idx_reg_report_user', 'regulatory_reports', ['user_id'])

    # Risk Disclosures table
    op.create_table(
        'risk_disclosures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('disclosure_type', sa.String(100), nullable=False),
        sa.Column('jurisdiction', sa.String(10), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(128), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('language', sa.String(10), nullable=False,
                  server_default='en'),
        sa.Column('acknowledged', sa.Boolean, nullable=False,
                  server_default='false'),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_disclosure_user', 'risk_disclosures', ['user_id'])
    op.create_index('idx_disclosure_type', 'risk_disclosures',
                    ['disclosure_type'])

    # Archive Manifest table
    op.create_table(
        'archive_manifest',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category', data_retention_category, nullable=False),
        sa.Column('storage_location', sa.String(500), nullable=False),
        sa.Column('storage_format', sa.String(50), nullable=False,
                  server_default='json.gz'),
        sa.Column('record_count', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('data_start_date', sa.DateTime(timezone=True),
                  nullable=False),
        sa.Column('data_end_date', sa.DateTime(timezone=True),
                  nullable=False),
        sa.Column('archive_hash', sa.String(128), nullable=False),
        sa.Column('file_size_bytes', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('retention_purge_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('data_retention_purges.id',
                                ondelete='SET NULL'),
                  nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_archive_category', 'archive_manifest', ['category'])
    op.create_index('idx_archive_created', 'archive_manifest', ['archived_at'])

    # Data Classification Rules table
    op.create_table(
        'data_classification_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('classification_level', classification_level, nullable=False),
        sa.Column('rationale', sa.String(500), nullable=True),
        sa.Column('handling_procedure', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_class_rule_table_field', 'data_classification_rules',
                    ['table_name', 'field_name'])

    # ------------------------------------------------------------------
    # Write-once trigger for audit_logs (PostgreSQL only)
    # Prevents UPDATE/DELETE on audit_logs after they are created.
    # For SQLite, this is enforced at the application level.
    # ------------------------------------------------------------------
    try:
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs table is write-once: UPDATE and DELETE are not permitted';
            END;
            $$ LANGUAGE plpgsql;
        """)

        op.execute("""
            CREATE TRIGGER trg_audit_logs_write_once
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """)

        # Also for audit_log_chain
        op.execute("""
            CREATE TRIGGER trg_audit_log_chain_write_once
            BEFORE UPDATE OR DELETE ON audit_log_chain
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """)
    except Exception:
        # Not on PostgreSQL — that's fine
        pass


def downgrade() -> None:
    """Drop compliance tables."""

    # Drop write-once triggers
    try:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_write_once ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_chain_write_once ON audit_log_chain")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
    except Exception:
        pass

    # Drop tables in reverse order
    tables = [
        'data_classification_rules',
        'archive_manifest',
        'risk_disclosures',
        'regulatory_reports',
        'audit_log_chain',
        'data_retention_purges',
        'pii_inventory',
        'consent_records',
    ]

    for table in tables:
        op.drop_table(table)

    # Drop enums
    enums = [
        'purgestatus',
        'classificationlevel',
        'dataretentioncategory',
        'piicategory',
        'consentstatus',
        'consenttype',
    ]

    for enum in enums:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
