import os
import sys
import json
import re # Import regex module
import requests
from datetime import datetime
from docx import Document # pip install python-docx

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABRICKS_CONFIG, FILE_PATHS, write_debug
from src.prompts import LLM_INDEX_PAGES_PROMPT, LLM_EXTRACT_PAGE_DATA_PROMPT
from src.processors.database_operations import insert_onenote_page, onenote_notebook_exists, onenote_section_exists

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

def get_onenote_page_demarcation_data(filepath):
    """
    Extracts page demarcation strings from a DOCX file using an LLM.
    
    Args:
        filepath (str): The path to the .docx file.
        
    Returns:
        list: A list of strings, each representing a page's demarcation string.
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

        # --- Indexing Phase (Get ordered list of page demarcation strings) ---
        write_debug(f"Starting LLM indexing phase (getting page demarcation strings) for {filepath}", append=True)
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

        page_demarcation_strings = None
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
                    
                    # Attempt to parse as JSON list of strings
                    try:
                        parsed_list = json.loads(llm_text_content)
                        if isinstance(parsed_list, list) and all(isinstance(item, str) for item in parsed_list):
                            page_demarcation_strings = parsed_list
                            write_debug(f"LLM indexing successful for {filepath} (JSON parse).", append=True)
                            break
                        else:
                            write_debug(f"LLM indexing output invalid format for {filepath} (Attempt {attempt + 1}) (Not list of strings): {parsed_list}", append=True)
                    except json.JSONDecodeError as e:
                        write_debug(f"LLM indexing response not valid JSON for {filepath} (Attempt {attempt + 1}): {e}. Attempting direct string extraction...", llm_text_content, append=True)
                        
                        # Fallback: Attempt to extract demarcation strings directly using regex
                        extracted_strings = []
                        # This regex looks for a pattern that starts with a quote, captures content, and ends with a quote,
                        # followed by a comma or end of array/string.
                        # It's a heuristic to recover from malformed JSON arrays of strings.
                        matches = re.findall(r'"(.*?)"(?:,\s*|$)', llm_text_content, re.DOTALL)
                        for match_content in matches:
                            # Reconstruct the string, handling escaped quotes if necessary
                            extracted_strings.append(match_content.replace('\\"', '"'))
                        
                        if extracted_strings:
                            page_demarcation_strings = extracted_strings
                            write_debug(f"LLM indexing successful for {filepath} (Direct string extraction). Extracted {len(extracted_strings)} strings.", append=True)
                            break
                        else:
                            write_debug(f"Direct string extraction failed for {filepath} (Attempt {attempt + 1}).", append=True)
                else:
                    write_debug(f"LLM indexing response missing 'choices' or empty for {filepath} (Attempt {attempt + 1})", llm_raw_response, append=True)

            except requests.exceptions.RequestException as e:
                write_debug(f"LLM indexing API call failed for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            except Exception as e:
                write_debug(f"An unexpected error occurred during LLM indexing call for {filepath} (Attempt {attempt + 1}): {e}", append=True)
            
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2)

        if page_demarcation_strings is None or not page_demarcation_strings:
            write_debug(f"LLM indexing failed or returned no demarcation strings after {MAX_RETRIES} attempts for {filepath}", append=True)
            raise Exception(f"LLM indexing failed or returned no demarcation strings after {MAX_RETRIES} attempts for {filepath}.")

        # Post-processing: Filter out records with invalid page_datetime format
        # This step is now done in process_onenote_pages as it needs the page_title
        # from the demarcation string.
        
        write_debug("Final LLM Page Demarcation Strings (Unfiltered)", page_demarcation_strings, append=True)
        return page_demarcation_strings
    except Exception as e:
        write_debug(f"Error in get_onenote_page_demarcation_data for {filepath}", str(e), append=True)
        raise

        # Post-processing: Filter out records with invalid page_datetime format
        filtered_demarcation_data = []
        faulty_records_count = 0
        for record in page_demarcation_data:
            if DATETIME_PATTERN.match(record["page_datetime"]):
                filtered_demarcation_data.append(record)
            else:
                write_debug(f"Invalid page_datetime format for record: {record}. Skipping.", append=True)
                faulty_records_count += 1

        write_debug(f"Removed {faulty_records_count} faulty records due to mismatched datetime patterns.", append=True)
        write_debug("Final LLM Page Demarcation Data (Filtered)", filtered_demarcation_data)
        return filtered_demarcation_data
    except Exception as e:
        write_debug(f"Error in get_onenote_page_demarcation_data for {filepath}", str(e), append=True)
        raise

def process_onenote_pages(filepath, page_demarcation_strings):
    """
    Processes each page of a DOCX file using an LLM to extract detailed page data.
    
    Args:
        filepath (str): The path to the .docx file.
        page_demarcation_strings (list): A list of strings, each representing a page's
                                          demarcation string, as returned by get_onenote_page_demarcation_data.
                                       
    Returns:
        list: A list of dictionaries, each representing a processed page with title, body, datetime, and summary status.
    """
    MAX_RETRIES = 3
    
    try:
        docx_text = extract_text_from_docx(filepath)
        write_debug(f"Extracted DOCX text length for {filepath} for page processing", len(docx_text), append=True)

        text_generation_url = DATABRICKS_CONFIG['text_generation_url']
        api_key = DATABRICKS_CONFIG['api_key']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        processed_pages_data = []
        faulty_records_count = 0

        for i, demarcation_string in enumerate(page_demarcation_strings):
            # Extract page_title and page_datetime from demarcation_string
            match = DATETIME_PATTERN.search(demarcation_string)
            if match:
                page_datetime_str_raw = match.group(0)
                # Handle potential newline in datetime string for title extraction
                page_datetime_str_clean = page_datetime_str_raw.replace('\n', ' ')
                page_title = demarcation_string.replace(page_datetime_str_raw, '').strip()
            else:
                # If datetime pattern not found, use the whole string as title and mark as faulty
                page_title = demarcation_string.strip()
                page_datetime_str_raw = None # No valid datetime found
                faulty_records_count += 1
                write_debug(f"Invalid page_datetime format for demarcation string: '{demarcation_string}'. Skipping datetime validation for this record.", append=True)
                continue # Skip processing this page if datetime is invalid

            start_index = docx_text.find(demarcation_string)
            if start_index == -1:
                write_debug(f"Demarcation string not found for page: '{page_title}'. Skipping.", append=True)
                continue

            end_index = None
            if i < len(page_demarcation_strings) - 1:
                next_demarcation_string = page_demarcation_strings[i+1]
                end_index = docx_text.find(next_demarcation_string, start_index + len(demarcation_string))
                if end_index == -1:
                    write_debug(f"Next demarcation string not found for page: '{page_title}'. Processing until end of document.", append=True)
                    page_content = docx_text[start_index:]
                else:
                    page_content = docx_text[start_index:end_index]
            else:
                page_content = docx_text[start_index:]

            write_debug(f"Processing page: '{page_title}' with content length: {len(page_content)}", append=True)

            extract_prompt_content = LLM_EXTRACT_PAGE_DATA_PROMPT.replace("{{target_page_title}}", page_title).replace("{{page_content}}", page_content)
            
            extract_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": extract_prompt_content
                    }
                ],
                "max_tokens": 8191 # Max output tokens for page data
            }

            page_data = None
            for attempt in range(MAX_RETRIES):
                write_debug(f"Attempt {attempt + 1}/{MAX_RETRIES} for page data extraction LLM call for page: '{page_title}'", append=True)
                try:
                    response = requests.post(
                        text_generation_url,
                        headers=headers,
                        json=extract_payload,
                        timeout=300 # Increased timeout for potentially large page extraction
                    )
                    response.raise_for_status()
                    
                    llm_raw_response = response.json()
                    
                    if 'choices' in llm_raw_response and len(llm_raw_response['choices']) > 0:
                        llm_text_content = llm_raw_response['choices'][0]['message']['content']
                        if llm_text_content.startswith("```json") and llm_text_content.endswith("```"):
                            llm_text_content = llm_text_content[7:-3].strip()
                        try:
                            parsed_data = json.loads(llm_text_content)
                            # Basic validation for expected keys
                            if all(key in parsed_data for key in ["page_title", "page_body_text", "page_datetime", "is_summary"]):
                                page_data = parsed_data
                                write_debug(f"LLM page data extraction successful for page: '{page_title}'", page_data, append=True)
                                break
                            else:
                                write_debug(f"LLM page data output invalid format for page '{page_title}' (Attempt {attempt + 1})", llm_text_content, append=True)
                        except json.JSONDecodeError as e:
                            write_debug(f"LLM page data response not valid JSON for page '{page_title}' (Attempt {attempt + 1}): {e}", llm_text_content, append=True)
                    else:
                        write_debug(f"LLM page data response missing 'choices' or empty for page '{page_title}' (Attempt {attempt + 1})", llm_raw_response, append=True)

                except requests.exceptions.RequestException as e:
                    write_debug(f"LLM page data API call failed for page '{page_title}' (Attempt {attempt + 1}): {e}", append=True)
                except Exception as e:
                    write_debug(f"An unexpected error occurred during LLM page data call for page '{page_title}' (Attempt {attempt + 1}): {e}", append=True)
                
                if attempt < MAX_RETRIES - 1:
                    import time
                    time.sleep(2)

            if page_data:
                processed_pages_data.append(page_data)
            else:
                write_debug(f"Failed to extract data for page: '{page_title}' after {MAX_RETRIES} attempts. Skipping this page.", append=True)

        write_debug(f"Removed {faulty_records_count} faulty records due to mismatched datetime patterns during page processing.", append=True)
        write_debug("Finished processing all pages.", processed_pages_data, append=True)
        return processed_pages_data
    except Exception as e:
        write_debug(f"Error in process_onenote_pages for {filepath}", str(e), append=True)
        raise

def process_single_onenote_doc(filepath, skip_if_exists=True):
    """
    Processes a single DOCX file (OneNote section), extracting page data,
    vectorizing, and inserting into the database.
    
    Args:
        filepath (str): The full path to the .docx file.
        skip_if_exists (bool): If True, skips processing if the notebook and section
                                already exist in the database. Defaults to True.
    """
    try:
        workbook_name = os.path.basename(os.path.dirname(filepath))
        section_name = os.path.splitext(os.path.basename(filepath))[0]
        
        write_debug(f"Attempting to process single section: {section_name} in workbook: {workbook_name}", append=True)

        # Check if the notebook and section already exist in the database
        notebook_exists = onenote_notebook_exists(workbook_name)
        section_exists = onenote_section_exists(section_name)

        if notebook_exists and section_exists:
            if skip_if_exists:
                write_debug(f"Skipping section '{section_name}' in workbook '{workbook_name}'. Already processed and skip_if_exists is True.", append=True)
                return
            else:
                write_debug(f"Reprocessing section '{section_name}' in workbook '{workbook_name}'. Overriding existing records.", append=True)
        elif notebook_exists and not section_exists:
            write_debug(f"Notebook '{workbook_name}' exists, but section '{section_name}' does not. Proceeding with processing.", append=True)
        elif not notebook_exists and section_exists:
            write_debug(f"Section '{section_name}' exists, but notebook '{workbook_name}' does not. This might indicate a naming inconsistency. Proceeding with processing.", append=True)
        else: # Both notebook and section do not exist
            write_debug(f"Neither notebook '{workbook_name}' nor section '{section_name}' exist. Proceeding with processing.", append=True)
        
        # 1. Get page demarcation data
        demarcation_data = get_onenote_page_demarcation_data(filepath)
        
        if not demarcation_data:
            write_debug(f"No demarcation data found for {filepath}. Skipping.", append=True)
            return
        
        # 2. Process pages
        processed_pages = process_onenote_pages(filepath, demarcation_data)
        
        if not processed_pages:
            write_debug(f"No processed pages found for {filepath}. Skipping.", append=True)
            return

        # 3. Prepare and insert data into database
        for page in processed_pages:
            try:
                # Convert page_datetime to SQL timestamp format
                page_datetime_str = page.get('page_datetime')
                if page_datetime_str and DATETIME_PATTERN.match(page_datetime_str):
                    page_datetime_obj = datetime.strptime(page_datetime_str.replace('\n', ' '), "%A, %B %d, %Y %I:%M %p")
                    sql_page_datetime = page_datetime_obj.isoformat()
                else:
                    sql_page_datetime = None
                    write_debug(f"Invalid or missing page_datetime format for page '{page.get('page_title')}' in {filepath}. Setting to None.", page_datetime_str, append=True)

                # Get embeddings
                embeddings = get_text_embeddings(page['page_body_text'])

                # Prepare data for insertion
                page_data_for_db = {
                    'page_title': page['page_title'],
                    'page_body_text': page['page_body_text'],
                    'is_summary': page['is_summary'],
                    'page_datetime': sql_page_datetime,
                    'workbook_name': workbook_name,
                    'section_name': section_name,
                    'embedding': embeddings,
                    'override_on_duplicate': not skip_if_exists # Pass the override flag to insert_onenote_page
                }
                
                # Insert into database
                insert_onenote_page(page_data_for_db)
                write_debug(f"Successfully inserted page '{page['page_title']}' from {section_name} into DB.", append=True)

            except Exception as e:
                write_debug(f"Error processing and inserting page '{page.get('page_title')}' from {filepath}: {str(e)}", append=True)
                
    except Exception as e:
        write_debug(f"Error processing single DOCX file {filepath}: {str(e)}", append=True)
        raise

def process_onenote_notebooks(skip_if_exists=True):
    """
    Orchestrates the processing of all OneNote notebooks and sections (DOCX files),
    extracting page data, vectorizing, and inserting into the database.
    
    Args:
        skip_if_exists (bool): If True, skips processing if the notebook and section
                                already exist in the database. Defaults to True.
    """
    onenote_workbooks_dir = FILE_PATHS['onenote_data_dir']
    
    if not os.path.exists(onenote_workbooks_dir):
        write_debug(f"OneNote workbooks directory not found: {onenote_workbooks_dir}", append=True)
        return

    write_debug(f"Starting OneNote notebooks processing from: {onenote_workbooks_dir}", append=True)

    for workbook_name in os.listdir(onenote_workbooks_dir):
        workbook_path = os.path.join(onenote_workbooks_dir, workbook_name)
        
        if os.path.isdir(workbook_path):
            write_debug(f"Processing workbook: {workbook_name}", append=True)
            
            for section_filename in os.listdir(workbook_path):
                if section_filename.endswith(".docx"):
                    section_filepath = os.path.join(workbook_path, section_filename)
                    process_single_onenote_doc(section_filepath, skip_if_exists)
                        
    write_debug("Finished OneNote notebooks processing.", append=True)

# Example usage (for testing purposes, can be removed later)
if __name__ == "__main__":
    # process_onenote_notebooks()
    # process_single_onenote_doc("")
    get_onenote_page_demarcation_data("")
