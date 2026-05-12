-- Clinical LLMOps platform - Reference Schema
-- This is the documentation DDL.  Alembic manages the actual migrations.

CREATE TABLE encounters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(64) NOT NULL,
    provider_npi VARCHAR(10),
    specialty VARCHAR(50) NOT NULL,
    encounter_type VARCHAR(20) NOT NULL DEFAULT 'ambulatory',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters(id),
    raw_text TEXT NOT NULL,
    word_count INTEGER,
    duration_seconds INTEGER,
    source VARCHAR(30) NOT NULL DEFAULT 'synthetic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE generated_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters(id),
    transcript_id UUID NOT NULL REFERENCES transcripts(id),
    note_format VARCHAR(10) NOT NULL DEFAULT 'soap',
    note_text TEXT NOT NULL,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(50) NOT NULL,
    version_fingerprint VARCHAR(64) NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tool_calls(
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id UUID NOT NULL REFERENCES generated_notes(id),
    tool_name VARCHAR(50) NOT NULL,
    tool_input JSONB NOT NULL DEFAULT '{}',
    tool_output JSONB,
    latency_ms INTEGER,
    call_order SMALLINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attestations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id UUID NOT NULL REFERENCES generated_notes(id),
    status VARCHAR(20) NOT NULL DEFAULT 'generated',
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor VARCHAR(64),
    edit_distance INTEGER,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters(id),
    event_type VARCHAR(50) NOT NULL,
    event_source VARCHAR(30) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transcripts_encounter ON transcripts(encounter_id);
CREATE INDEX idx_notes_encounter ON generated_notes(encounter_id);
CREATE INDEX idx_tool_calls_note ON tool_calls(note_id);
CREATE INDEX idx_attestations_note ON attestations(note_id);
CREATE INDEX idx_attestations_status ON attestations(status);
CREATE INDEX idx_audit_encounter ON audit_events(encounter_id);
CREATE INDEX idx_audit_type_created ON audit_events(event_type, created_at);