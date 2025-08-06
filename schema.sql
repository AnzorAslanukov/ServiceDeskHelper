-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- OneNote Pages table
CREATE TABLE onenote_pages (
    id SERIAL PRIMARY KEY,
    page_title TEXT NOT NULL,
    page_body_text TEXT NOT NULL,
    is_summary BOOLEAN DEFAULT FALSE,
    page_datetime TIMESTAMP WITH TIME ZONE,
    workbook_name TEXT NOT NULL,
    section_name TEXT NOT NULL,
    embedding vector(1024),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
