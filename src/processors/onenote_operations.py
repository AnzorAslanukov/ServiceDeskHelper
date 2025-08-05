import os
import sys
import json
import re # Import regex module
import requests
from datetime import datetime
from docx import Document # pip install python-docx

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABRICKS_CONFIG, write_debug
from src.prompts import LLM_INDEX_PAGES_PROMPT

# Regex pattern for valid date/time formats
# "Friday, December 18, 2020\n9:08 AM" or "Friday, December 18, 2020 9:08 AM"
DATETIME_PATTERN = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
    r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}"
    r"[\n ]\d{1,2}:\d{2} (AM|PM)$"
)

def extract_text_from_docx(filepath):
    """
    Extracts all text from a .docx file.
    
    Args:
        filepath (str): The path to the .docx file.
        
    Returns:
        str: The concatenated text content of the .docx file.
    """
    try:
        document = Document(filepath)
        full_text = []
        for para in document.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        write_debug(f"Error extracting text from DOCX: {filepath}", str(e), append=True)
        raise

def get_text_embeddings(text):
    """
    Generates embeddings for a given text using the Databricks embedding model.
    
    Args:
        text (str): The text content to vectorize.
        
    Returns:
        list: A list of floats representing the embedding vector.
    """
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

def _validate_page_demarcation_output(llm_output):
    """
    Validates the structure of the LLM's page demarcation output.
    Expected format: list of dictionaries, each with 'page_title', 'page_datetime', 'page_demarcation_string'.
    """
    if not isinstance(llm_output, list):
        write_debug("LLM page demarcation validation failed: Not a list", llm_output, append=True)
        return False
    
    for page in llm_output:
        if not isinstance(page, dict):
            write_debug("LLM page demarcation validation failed: List item not a dictionary", page, append=True)
            return False
        
        required_keys = ["page_title", "page_datetime", "page_demarcation_string"]
        if not all(key in page for key in required_keys):
            write_debug(f"LLM page demarcation validation failed: Missing required keys in page {page}", page, append=True)
            return False
            
        if not isinstance(page["page_title"], str) or \
           not isinstance(page["page_datetime"], str) or \
           not isinstance(page["page_demarcation_string"], str):
            write_debug(f"LLM page demarcation validation failed: Incorrect type for page fields {page}", page, append=True)
            return False
            
    return True

def get_onenote_page_demarcation_data(filepath):
    """
    Extracts page demarcation data (title, datetime, combined string) from a DOCX file
    using an LLM. This function focuses solely on the indexing phase.
    
    Args:
        filepath (str): The path to the .docx file.
        
    Returns:
        list: A list of dictionaries, each representing a page's demarcation data.
    """
    MAX_RETRIES = 3
    
    try:
        # 1. Extract text from DOCX
        docx_text = extract_text_from_docx(filepath)
        write_debug(f"Extracted DOCX text length for {filepath}", len(docx_text), append=True)

        # Databricks LLM configuration
        text_generation_url = DATABRICKS_CONFIG['text_generation_url']
        api_key = DATABRICKS_CONFIG['api_key']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        # --- Indexing Phase (Get ordered list of page demarcation data) ---
        write_debug(f"Starting LLM indexing phase (getting page demarcation data) for {filepath}", append=True)
        index_prompt_content = LLM_INDEX_PAGES_PROMPT.replace("{{document_content}}", docx_text)
        
        index_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": index_prompt_content
                }
            ],
            "max_tokens": 8191 # Max output tokens for indexing
        }

        page_demarcation_data = None
        for attempt in range(MAX_RETRIES):
            write_debug(f"Attempt {attempt + 1}/{MAX_RETRIES} for indexing LLM call for {filepath}", append=True)
            try:
                response = requests.post(
                    text_generation_url,
                    headers=headers,
                    json=index_payload,
                    timeout=3000 # Increased timeout for potentially large indexing task (50 minutes)
                )
                response.raise_for_status()
                
                llm_raw_response = response.json()
                
                if 'choices' in llm_raw_response and len(llm_raw_response['choices']) > 0:
                    llm_text_content = llm_raw_response['choices'][0]['message']['content']
                    # Strip markdown code block fences if present
                    if llm_text_content.startswith("```json") and llm_text_content.endswith("```"):
                        llm_text_content = llm_text_content[7:-3].strip()
                    try:
                        parsed_data = json.loads(llm_text_content)
                        if _validate_page_demarcation_output(parsed_data):
                            page_demarcation_data = parsed_data
                            write_debug(f"LLM indexing successful for {filepath}", page_demarcation_data, append=True)
                            break
                        else:
                            write_debug(f"LLM indexing output invalid format for {filepath} (Attempt {attempt + 1})", llm_text_content, append=True)
                    except json.JSONDecodeError as e:
                        write_debug(f"LLM indexing response not valid JSON for {filepath} (Attempt {attempt + 1}): {e}", llm_text_content, append=True)
                else:
                    write_debug(f"LLM indexing response missing 'choices' or empty for {filepath} (Attempt {attempt + 1})", llm_raw_response, append=True)

            except requests.exceptions.RequestException as e:
                write_debug(f"LLM indexing API call failed for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            except Exception as e:
                write_debug(f"An unexpected error occurred during LLM indexing call for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2)

        if page_demarcation_data is None or not page_demarcation_data:
            write_debug(f"LLM indexing failed or returned no demarcation data after {MAX_RETRIES} attempts for {filepath}", append=True)
            raise Exception(f"LLM indexing failed or returned no demarcation data after {MAX_RETRIES} attempts for {filepath}.")

        # Post-processing: Filter out records with invalid page_datetime format
        filtered_demarcation_data = []
        for record in page_demarcation_data:
            if DATETIME_PATTERN.match(record["page_datetime"]):
                filtered_demarcation_data.append(record)
            else:
                write_debug(f"Invalid page_datetime format for record: {record}. Skipping.", append=True)

        write_debug("Final LLM Page Demarcation Data (Filtered)", filtered_demarcation_data)
        return filtered_demarcation_data
    except Exception as e:
        write_debug(f"Error in get_onenote_page_demarcation_data for {filepath}", str(e), append=True)
        raise

get_onenote_page_demarcation_data("C:/Users/aslanuka_wa1/Documents/projects/sd_database_v4/data/onenote/workbooks/Work Notebook/1 SD Daily Post.docx")
