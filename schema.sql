-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE onenote_chunks (
    id SERIAL PRIMARY KEY,
    chunk_title TEXT,  -- Generated from first line or keywords
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER,  -- Position within the section
    notebook_name TEXT NOT NULL,
    section_name TEXT NOT NULL,
    embedding vector(1024),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE athena_tickets (
    -- Primary identifiers
    id SERIAL PRIMARY KEY,
    entity_id TEXT UNIQUE NOT NULL,
    ticket_id TEXT NOT NULL,
    
    -- Core ticket information
    title TEXT NOT NULL,
    description TEXT,
    escalated BOOLEAN DEFAULT FALSE,
    resolution_description TEXT,
    message TEXT,
    priority INTEGER,
    
    -- Location information
    location_name TEXT,
    floor_name TEXT,
    affect_patient_care TEXT,
    confirmed_resolution TEXT,
    
    -- Dates
    created_date TIMESTAMP WITH TIME ZONE,
    last_modified TIMESTAMP WITH TIME ZONE,
    
    -- Affected User (minimal info)
    affected_user_domain TEXT,
    affected_user_company TEXT,
    affected_user_department TEXT,
    affected_user_title TEXT,
    
    -- Assigned To User (minimal info)
    assigned_to_user_domain TEXT,
    assigned_to_user_company TEXT,
    assigned_to_user_department TEXT,
    assigned_to_user_title TEXT,
    
    -- Resolved By User (minimal info)
    resolved_by_user_domain TEXT,
    resolved_by_user_company TEXT,
    resolved_by_user_department TEXT,
    resolved_by_user_title TEXT,
    
    -- Analyst Comments (stored as JSONB for flexibility)
    analyst_comments JSONB,
    
    -- Vector embeddings (separate for more precise search)
    title_embedding vector(1024),
    description_embedding vector(1024),
    
    -- System tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);