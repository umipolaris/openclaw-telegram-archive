"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-02-24 00:00:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")

    op.execute("create type source_type as enum ('telegram', 'wiki', 'manual', 'api')")
    op.execute(
        "create type ingest_state as enum ('RECEIVED','STORED','EXTRACTED','CLASSIFIED','INDEXED','PUBLISHED','FAILED','NEEDS_REVIEW')"
    )
    op.execute("create type review_status as enum ('NONE','NEEDS_REVIEW','RESOLVED')")
    op.execute("create type user_role as enum ('ADMIN','EDITOR','REVIEWER','VIEWER')")

    op.execute(
        """
        create table users (
          id uuid primary key default gen_random_uuid(),
          username varchar(64) not null unique,
          password_hash text not null,
          role user_role not null default 'VIEWER',
          is_active boolean not null default true,
          last_login_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table categories (
          id uuid primary key default gen_random_uuid(),
          name varchar(100) not null,
          slug varchar(120) not null unique,
          parent_id uuid references categories(id),
          sort_order int not null default 0,
          is_active boolean not null default true,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table tags (
          id uuid primary key default gen_random_uuid(),
          name varchar(80) not null unique,
          slug varchar(100) not null unique,
          is_sensitive boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table rulesets (
          id uuid primary key default gen_random_uuid(),
          name varchar(120) not null unique,
          description text,
          is_active boolean not null default true,
          current_version_id uuid,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table rule_versions (
          id uuid primary key default gen_random_uuid(),
          ruleset_id uuid not null references rulesets(id) on delete cascade,
          version_no int not null,
          rules_json jsonb not null,
          checksum_sha256 char(64) not null,
          published_at timestamptz,
          is_active boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          unique (ruleset_id, version_no)
        )
        """
    )

    op.execute(
        "alter table rulesets add constraint fk_rulesets_current_version foreign key (current_version_id) references rule_versions(id)"
    )

    op.execute(
        """
        create table files (
          id uuid primary key default gen_random_uuid(),
          source source_type not null,
          source_ref varchar(128),
          storage_backend varchar(16) not null,
          bucket varchar(100) not null,
          storage_key text not null,
          original_filename text not null,
          uploaded_filename text not null,
          extension varchar(16),
          checksum_sha256 char(64) not null,
          mime_type varchar(150) not null,
          size_bytes bigint not null check (size_bytes >= 0),
          metadata_json jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          unique (checksum_sha256)
        )
        """
    )

    op.execute(
        """
        create table documents (
          id uuid primary key default gen_random_uuid(),
          source source_type not null,
          source_ref varchar(128),
          title varchar(300) not null,
          description text not null default '',
          caption_raw text not null default '',
          summary text not null default '',
          category_id uuid references categories(id),
          event_date date,
          ingested_at timestamptz not null default now(),
          review_status review_status not null default 'NONE',
          review_reasons text[] not null default '{}'::text[],
          current_version_no int not null default 1,
          search_vector tsvector,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table document_versions (
          id uuid primary key default gen_random_uuid(),
          document_id uuid not null references documents(id) on delete cascade,
          version_no int not null,
          title varchar(300) not null,
          description text not null,
          summary text not null,
          category_id uuid references categories(id),
          event_date date,
          tags_snapshot jsonb not null default '[]'::jsonb,
          change_reason varchar(200) not null,
          changed_at timestamptz not null default now(),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          unique (document_id, version_no)
        )
        """
    )

    op.execute(
        """
        create table document_files (
          id uuid primary key default gen_random_uuid(),
          document_id uuid not null references documents(id) on delete cascade,
          file_id uuid not null references files(id) on delete restrict,
          is_primary boolean not null default true,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          unique (document_id, file_id)
        )
        """
    )

    op.execute(
        """
        create table document_tags (
          document_id uuid not null references documents(id) on delete cascade,
          tag_id uuid not null references tags(id) on delete cascade,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          primary key (document_id, tag_id)
        )
        """
    )

    op.execute(
        """
        create table ingest_jobs (
          id uuid primary key default gen_random_uuid(),
          source source_type not null,
          source_ref varchar(128),
          state ingest_state not null default 'RECEIVED',
          file_path_temp text,
          caption text,
          payload_json jsonb not null default '{}'::jsonb,
          document_id uuid references documents(id),
          attempt_count int not null default 0,
          max_attempts int not null default 5,
          retry_after timestamptz,
          last_error_code varchar(80),
          last_error_message text,
          received_at timestamptz not null default now(),
          started_at timestamptz,
          finished_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table ingest_events (
          id bigserial primary key,
          ingest_job_id uuid not null references ingest_jobs(id) on delete cascade,
          from_state ingest_state,
          to_state ingest_state not null,
          event_type varchar(80) not null,
          event_message text not null default '',
          event_payload jsonb not null default '{}'::jsonb,
          occurred_at timestamptz not null default now(),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table audit_logs (
          id bigserial primary key,
          actor_user_id uuid references users(id),
          action varchar(100) not null,
          target_type varchar(50) not null,
          target_id uuid,
          source source_type,
          source_ref varchar(128),
          before_json jsonb,
          after_json jsonb,
          masked_fields text[] not null default '{}'::text[],
          ip_addr inet,
          user_agent text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )

    op.execute(
        """
        create table saved_filters (
          id uuid primary key default gen_random_uuid(),
          user_id uuid not null references users(id) on delete cascade,
          name varchar(120) not null,
          filter_json jsonb not null,
          is_shared boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id),
          unique (user_id, name)
        )
        """
    )

    op.execute("create index idx_documents_event_date_desc on documents (event_date desc nulls last)")
    op.execute("create index idx_documents_category_event_date on documents (category_id, event_date desc nulls last)")
    op.execute("create index idx_documents_search_vector_gin on documents using gin (search_vector)")
    op.execute(
        "create unique index uq_documents_source_ref_telegram on documents (source_ref) where source='telegram' and source_ref is not null"
    )
    op.execute(
        "create unique index uq_ingest_jobs_source_ref_telegram on ingest_jobs (source_ref) where source='telegram' and source_ref is not null"
    )
    op.execute("create index idx_ingest_jobs_state_received_at on ingest_jobs (state, received_at desc)")
    op.execute("create index idx_ingest_events_job_occurred on ingest_events (ingest_job_id, occurred_at desc)")
    op.execute("create index idx_audit_logs_target on audit_logs (target_type, target_id, created_at desc)")


def downgrade() -> None:
    op.execute("drop table if exists saved_filters")
    op.execute("drop table if exists audit_logs")
    op.execute("drop table if exists ingest_events")
    op.execute("drop table if exists ingest_jobs")
    op.execute("drop table if exists document_tags")
    op.execute("drop table if exists document_files")
    op.execute("drop table if exists document_versions")
    op.execute("drop table if exists documents")
    op.execute("drop table if exists files")
    op.execute("alter table if exists rulesets drop constraint if exists fk_rulesets_current_version")
    op.execute("drop table if exists rule_versions")
    op.execute("drop table if exists rulesets")
    op.execute("drop table if exists tags")
    op.execute("drop table if exists categories")
    op.execute("drop table if exists users")

    op.execute("drop type if exists user_role")
    op.execute("drop type if exists review_status")
    op.execute("drop type if exists ingest_state")
    op.execute("drop type if exists source_type")
