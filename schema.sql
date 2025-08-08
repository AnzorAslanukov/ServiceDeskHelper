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

