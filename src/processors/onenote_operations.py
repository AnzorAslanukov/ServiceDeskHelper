import os
import sys
import json
import re # Import regex module
import requests
from datetime import datetime
from docx import Document # pip install python-docx
import mammoth # pip install mammoth
from bs4 import BeautifulSoup # pip install beautifulsoup4

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABRICKS_CONFIG, FILE_PATHS, write_debug
from src.processors.database_operations import add_onenote_chunk, onenote_section_exists, delete_onenote_records, check_table_and_columns_exist, perform_hybrid_search


def extract_text_from_docx(filepath):
    """
    Extracts all text from a .docx file, including paragraphs and tables.
    Uses multiple methods in order of complexity, falling back to simpler methods if needed.
    
    Args:
        filepath (str): The path to the .docx file.
        
    Returns:
        str: The concatenated text content of the .docx file.
    """
    write_debug(f"Attempting to extract text from DOCX using mammoth: {filepath}", append=True)
    try:
        with open(filepath, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
            html = result.value # The generated HTML
            messages = result.messages # Any messages from the conversion

            for msg in messages:
                write_debug(f"Mammoth conversion message: {msg.message} (Type: {msg.type})", append=True)

            soup = BeautifulSoup(html, 'html.parser')
            full_text_parts = []

            # Extract text from paragraphs
            for p in soup.find_all('p'):
                if p.get_text(strip=True):
                    full_text_parts.append(p.get_text(separator='\n', strip=True))
            
            # Extract text from tables
            for table in soup.find_all('table'):
                table_text = []
                for row in table.find_all('tr'):
                    row_text = []
                    for cell in row.find_all(['td', 'th']):
                        cell_content = cell.get_text(separator='\n', strip=True)
                        if cell_content:
                            row_text.append(cell_content)
                    if row_text:
                        table_text.append('\t'.join(row_text)) # Use tab for cell separation
                if table_text:
                    full_text_parts.append('\n'.join(table_text)) # Use newline for row separation

            result_text = '\n\n'.join(full_text_parts) # Double newline for block separation

            write_debug(f"DOCX extraction complete using mammoth: {filepath}", {
                "extracted_length": len(result_text),
                "method_used": "mammoth_html_parsing"
            }, append=True)
            
            return result_text
        
    except FileNotFoundError:
        write_debug(f"DOCX file not found: {filepath}", append=True)
        raise
    except Exception as e:
        write_debug(f"Error extracting text from DOCX using mammoth: {filepath}: {str(e)}", append=True)
        raise

def get_text_embeddings(text):
    """
    Generates embeddings for a given text using the Databricks embedding model.
    
    Args:
        text (str): The text content to vectorize.
        
    Returns:
        list: A list of floats representing the embedding vector.
    """
    write_debug(f"Attempting to generate embeddings for text of length {len(text)}", append=True)
    embedding_url = DATABRICKS_CONFIG['embedding_url']
    api_key = DATABRICKS_CONFIG['api_key']

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    payload = {
        "input": text
    }

    try:
        response = requests.post(
            embedding_url,
            headers=headers,
            json=payload,
            timeout=30 # Standard timeout for embedding
        )
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx) 
        
        embedding_response = response.json()
        
        if 'data' in embedding_response and len(embedding_response['data']) > 0:
            embeddings = embedding_response['data'][0]['embedding']
            write_debug(f"Successfully generated embeddings for text (first 10 elements): {embeddings[:10]}...", append=True)
            return embeddings
        else:
            write_debug(f"Embedding API response missing 'data' or empty.", embedding_response, append=True)
            raise Exception("Failed to get embeddings: Invalid API response format.")

    except requests.exceptions.RequestException as e:
        write_debug(f"Embedding API call failed: {e}", append=True)
        raise Exception(f"Failed to get embeddings: API call error - {e}")
    except Exception as e:
        write_debug(f"An unexpected error occurred during embedding generation: {e}", append=True)
        raise Exception(f"Failed to get embeddings: Unexpected error - {e}")

def process_single_docx_file(filepath, overwrite_existing=False):
    """
    Processes a single DOCX file, extracts text, chunks it semantically,
    generates embeddings, and stores them in the database.
    Derives notebook_name and section_name from the filepath.
    
    Args:
        filepath (str): The path to the .docx file.
        overwrite_existing (bool): If True, deletes existing records for the section/notebook
                                   before processing. If False, skips processing if records exist.
                                   Defaults to False.
    """
    write_debug(f"Starting process_single_docx_file for: {filepath}", append=True)
    onenote_data_dir = FILE_PATHS['onenote_data_dir']
    
    # Derive notebook_name and section_name from filepath
    relative_path = os.path.relpath(filepath, onenote_data_dir)
    parts = relative_path.split(os.sep)
    
    if len(parts) >= 2:
        notebook_name = parts[-2]
        section_name = os.path.splitext(parts[-1])[0]
        write_debug(f"Derived notebook: {notebook_name}, section: {section_name}", append=True)
    else:
        write_debug(f"Could not derive notebook and section names from path: {filepath}", append=True)
        return

    write_debug(f"  Processing section: {section_name} in notebook: {notebook_name} ({filepath})", append=True)

    # Check for existing records
    if onenote_section_exists(section_name): # Assuming section_name is unique enough for this check
        write_debug(f"  Records for section '{section_name}' already exist.", append=True)
        if overwrite_existing:
            write_debug(f"  Overwriting existing records for section '{section_name}'.", append=True)
            delete_onenote_records(section_name, 'section')
        else:
            write_debug(f"  Skipping processing for section '{section_name}' (overwrite_existing is False).", append=True)
            return
    
    try:
        full_text = extract_text_from_docx(filepath)
        write_debug(f"  Text extracted from DOCX. Length: {len(full_text)}", append=True)
        
        # Semantic chunking logic
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        write_debug(f"  Split into {len(paragraphs)} paragraphs.", append=True)
        
        current_chunk_text = []
        current_chunk_word_count = 0
        chunk_index = 0
        
        MAX_WORDS = 1000
        BUFFER_WORDS = 200

        for paragraph in paragraphs:
            paragraph_words = len(paragraph.split())
            write_debug(f"  Processing paragraph with {paragraph_words} words.", append=True)
            
            if current_chunk_word_count + paragraph_words <= MAX_WORDS:
                current_chunk_text.append(paragraph)
                current_chunk_word_count += paragraph_words
                write_debug(f"  Added paragraph to current chunk. Current words: {current_chunk_word_count}", append=True)
            else:
                # If adding the next paragraph exceeds max, finalize current chunk
                if current_chunk_text:
                    chunk_content = "\n\n".join(current_chunk_text)
                    chunk_title = " ".join(chunk_content.split()[:10]) # First 10 words as title
                    write_debug(f"  Finalizing chunk {chunk_index} with {current_chunk_word_count} words. Title: {chunk_title}", append=True)
                    embedding = get_text_embeddings(chunk_content)
                    
                    add_onenote_chunk(
                        chunk_title=chunk_title,
                        chunk_text=chunk_content,
                        chunk_index=chunk_index,
                        notebook_name=notebook_name,
                        section_name=section_name,
                        embedding=embedding
                    )
                    write_debug(f"  Chunk {chunk_index} added to database.", append=True)
                    chunk_index += 1
                
                # Start new chunk with buffer logic
                current_chunk_text = [paragraph]
                current_chunk_word_count = paragraph_words
                write_debug(f"  Starting new chunk with current paragraph. Words: {current_chunk_word_count}", append=True)
                
                # Add content from previous chunk to new chunk as buffer
                buffer_content = []
                buffer_word_count = 0
                for prev_paragraph in reversed(current_chunk_text[:-1]): # Exclude current paragraph
                    prev_paragraph_words = len(prev_paragraph.split())
                    if buffer_word_count + prev_paragraph_words <= BUFFER_WORDS:
                        buffer_content.insert(0, prev_paragraph)
                        buffer_word_count += prev_paragraph_words
                    else:
                        break
                current_chunk_text = buffer_content + current_chunk_text
                current_chunk_word_count += buffer_word_count
                write_debug(f"  Added buffer content to new chunk. Total words: {current_chunk_word_count}", append=True)

        # Add the last chunk if any content remains
        if current_chunk_text:
            chunk_content = "\n\n".join(current_chunk_text)
            chunk_title = " ".join(chunk_content.split()[:10])
            write_debug(f"  Finalizing last chunk {chunk_index} with {current_chunk_word_count} words. Title: {chunk_title}", append=True)
            embedding = get_text_embeddings(chunk_content)
            
            add_onenote_chunk(
                chunk_title=chunk_title,
                chunk_text=chunk_content,
                chunk_index=chunk_index,
                notebook_name=notebook_name,
                section_name=section_name,
                embedding=embedding
            )
            write_debug(f"  Last chunk {chunk_index} added to database.", append=True)
            chunk_index += 1
            
    except Exception as e:
        write_debug(f"Error processing section {section_name} in notebook {notebook_name}: {str(e)}", append=True)

def process_onenote_data():
    """
    Processes OneNote data from the configured directory by iterating through notebooks
    and calling process_single_docx_file for each DOCX file.
    """
    onenote_data_dir = FILE_PATHS['onenote_data_dir']
    write_debug(f"Starting OneNote data processing from: {onenote_data_dir}", append=True)

    if not os.path.exists(onenote_data_dir):
        write_debug(f"OneNote data directory not found: {onenote_data_dir}", append=True)
        return

    for notebook_name_dir in os.listdir(onenote_data_dir):
        notebook_path = os.path.join(onenote_data_dir, notebook_name_dir)
        if os.path.isdir(notebook_path):
            write_debug(f"Processing notebook directory: {notebook_name_dir}", append=True)
            
            for section_file in os.listdir(notebook_path):
                if section_file.endswith(".docx"):
                    section_filepath = os.path.join(notebook_path, section_file)
                    write_debug(f"Processing new DOCX file: {section_file}")
                    process_single_docx_file(section_filepath)
    
    write_debug("Finished OneNote data processing.", append=True)

def hybrid_search_onenote(query_string, num_records=3, table_name="onenote_chunks", column_names=["chunk_title", "chunk_text", "notebook_name", "section_name"], keywords=None):
    """
    Performs a hybrid search combining vector similarity and keyword matching.
    
    Args:
        query_string (str): The string object to search for.
        num_records (int): The number of records to retrieve (default 3, max 10).
        table_name (str): The name of the table to search in (default "onenote_chunks").
        column_names (list): List of column names to retrieve from the table.
        keywords (str, optional): Keywords for full-text search. Defaults to None.
        
    Returns:
        dict: A JSON object with search results.
    """
    write_debug(f"Starting hybrid search for query: '{query_string}' in table '{table_name}' with keywords: '{keywords}'", append=False)
    
    if not 1 <= num_records <= 10:
        write_debug(f"Error: num_records must be between 1 and 10. Received: {num_records}", append=True)
        return {
            "error": "num_records must be between 1 and 10",
            "num_records_chosen": num_records
        }

    # 1. Check for table and column existence
    if not check_table_and_columns_exist(table_name, column_names + ["embedding"]): # Ensure embedding column exists
        write_debug(f"Hybrid search cancelled due to missing table or columns in table '{table_name}'.", append=True)
        return {
            "error": "Table or specified columns do not exist",
            "table_name": table_name,
            "columns_checked": column_names + ["embedding"]
        }

    start_time = datetime.now()
    
    try:
        # 2. Generate embedding for the query string
        query_embedding = get_text_embeddings(query_string)
        if query_embedding is None:
            write_debug(f"Error: Could not generate embedding for query string: '{query_string}'", append=True)
            return {
                "error": "Could not generate embedding for query string",
                "query_string": query_string
            }

        # 3. Perform hybrid search
        retrieved_records = perform_hybrid_search(table_name, query_embedding, num_records, column_names, keywords)
        
        end_time = datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        total_words_from_retrieved_chunks = 0
        # Calculate word count for each retrieved record
        for record in retrieved_records:
            if 'chunk_text' in record and record['chunk_text'] is not None:
                word_count = len(record['chunk_text'].split())
                record['chunk_word_count'] = word_count
                total_words_from_retrieved_chunks += word_count
            else:
                record['chunk_word_count'] = 0 # Or handle as appropriate if chunk_text is missing/None

        write_debug(f"Hybrid search completed in {time_taken:.2f} seconds. Retrieved {len(retrieved_records)} records.", append=True)

        # 4. Return JSON object
        return {
            "num_records_chosen_for_retrieval": num_records,
            "time_it_took_to_retrieve_data_from_table": f"{time_taken:.2f} seconds",
            "total_words_from_retrieved_chunks": total_words_from_retrieved_chunks,
            "retrieved_records": retrieved_records
        }

    except Exception as e:
        write_debug(f"An unexpected error occurred during hybrid search: {str(e)}", append=True)
        return {
            "error": f"An unexpected error occurred: {str(e)}",
            "query_string": query_string,
            "table_name": table_name
        }



