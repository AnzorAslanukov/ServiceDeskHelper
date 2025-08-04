import os
import sys
import json
import requests
from datetime import datetime
from docx import Document # pip install python-docx

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABRICKS_CONFIG, write_debug
from src.prompts import LLM_PARSE_DOCX_PROMPT

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

def _validate_llm_output(llm_output):
    """
    Validates the structure of the LLM's parsed output.
    Expected format: list of dictionaries, each with 'page_title', 'page_body_text', 'page_datetime'.
    """
    if not isinstance(llm_output, list):
        write_debug("LLM output validation failed: Not a list", llm_output, append=True)
        return False
    
    for page in llm_output:
        if not isinstance(page, dict):
            write_debug("LLM output validation failed: List item not a dictionary", page, append=True)
            return False
        
        required_keys = ["page_title", "page_body_text", "page_datetime"]
        if not all(key in page for key in required_keys):
            write_debug(f"LLM output validation failed: Missing required keys in page {page}", page, append=True)
            return False
            
        if not isinstance(page["page_title"], str) or \
           not isinstance(page["page_body_text"], str) or \
           not isinstance(page["page_datetime"], str):
            write_debug(f"LLM output validation failed: Incorrect type for page fields {page}", page, append=True)
            return False
            
    return True

def test_llm_page_identification(filepath):
    """
    Test function to perform LLM-based page identification from DOCX text.
    Connects to the Databricks LLM, validates its output, and retries on failure.
    
    Args:
        filepath (str): The path to the .docx file.
        
    Returns:
        list: A list of dictionaries, each representing a parsed page.
    """
    MAX_RETRIES = 3
    
    try:
        # 1. Extract text from DOCX
        docx_text = extract_text_from_docx(filepath)

        # 2. Prepare prompt for LLM
        prompt_content = LLM_PARSE_DOCX_PROMPT.replace("{{docx_content}}", docx_text)

        # Databricks LLM configuration
        text_generation_url = DATABRICKS_CONFIG['text_generation_url']
        api_key = DATABRICKS_CONFIG['api_key']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt_content
                }
            ],
            "max_tokens": 16384 
        }

        llm_output = None
        for attempt in range(MAX_RETRIES):
            write_debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to call LLM for {filepath}", append=True)
            try:
                response = requests.post(
                    text_generation_url,
                    headers=headers,
                    json=payload,
                    timeout=60 # Increased timeout for LLM response
                )
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                
                llm_raw_response = response.json()
                
                # Extract content from LLM response
                if 'choices' in llm_raw_response and len(llm_raw_response['choices']) > 0:
                    llm_text_content = llm_raw_response['choices'][0]['message']['content']
                    
                    # Attempt to parse the JSON string
                    try:
                        parsed_output = json.loads(llm_text_content)
                        if _validate_llm_output(parsed_output):
                            llm_output = parsed_output
                            write_debug(f"LLM call successful and validated for {filepath}", llm_output, append=True)
                            break # Exit retry loop on success
                        else:
                            write_debug(f"LLM output invalid format for {filepath} (Attempt {attempt + 1})", llm_text_content, append=True)
                    except json.JSONDecodeError as e:
                        write_debug(f"LLM response is not valid JSON for {filepath} (Attempt {attempt + 1}): {e}", llm_text_content, append=True)
                else:
                    write_debug(f"LLM response missing 'choices' or empty for {filepath} (Attempt {attempt + 1})", llm_raw_response, append=True)

            except requests.exceptions.RequestException as e:
                write_debug(f"LLM API call failed for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            except Exception as e:
                write_debug(f"An unexpected error occurred during LLM call for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            
            if attempt < MAX_RETRIES - 1:
                # Optional: Add a small delay before retrying
                import time
                time.sleep(2) # Wait 2 seconds before next retry

        if llm_output is None:
            write_debug(f"LLM failed to provide valid output after {MAX_RETRIES} attempts for {filepath}", append=True)
            raise Exception(f"LLM failed to provide valid output after {MAX_RETRIES} attempts for {filepath}. Terminating to prevent token overuse.")

        # 4. Write final LLM output to debug.txt
        write_debug("Final LLM Page Identification Result", llm_output)

        return llm_output
    except Exception as e:
        write_debug(f"Error in test_llm_page_identification for {filepath}", str(e), append=True)
        raise
