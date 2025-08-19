import requests
import json
import os
import sys
from datetime import datetime

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.config import DATABRICKS_CONFIG, write_debug
# Assuming prompts.py contains a variable like LLM_PROMPT_TEMPLATE
from src.prompts import LLM_PROMPT_TEMPLATE, TICKET_QUESTION_GENERATION_PROMPT, TICKET_ASSIGNMENT_PROMPT

# Helper to safely get nested values
def get_nested_value(data, keys, default=None):
    if not isinstance(data, dict):
        return default
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current

def _to_json_string_or_iterate(data):
    """
    Attempts to convert data to a JSON string. If not possible,
    iterates through the data (if iterable) and formats it into a string.
    """
    try:
        # Try to dump as JSON first
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except TypeError:
        # If direct JSON dump fails, try to format iterables
        if hasattr(data, '__iter__') and not isinstance(data, str):
            formatted_str = []
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    formatted_str.append(f"  Item {i}:")
                    for k, v in item.items():
                        formatted_str.append(f"    {k}: {v}")
                else:
                    formatted_str.append(f"  - {item}")
            return "\n".join(formatted_str)
        else:
            # Fallback for non-iterable or other problematic types
            return str(data)

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

def generate_context_aware_response(user_question, hybrid_search_function, keywords=None):
    """
    Generates a context-aware response using a text generation LLM,
    based on a user question and relevant data retrieved from the database.
    
    Args:
        user_question (str): The question from the user.
        hybrid_search_function (function): The function to use for hybrid search (e.g., hybrid_search_onenote).
        keywords (list, optional): A list of strings representing keywords for the search. Defaults to None.
        
    Returns:
        dict: The response object from the LLM.
    """
    write_debug(f"Starting context-aware response generation for question: '{user_question}' with keywords: {keywords}", append=True)
    
    try:
        # Convert list of keywords to a single string if provided
        keywords_str = " ".join(keywords) if isinstance(keywords, list) else keywords

        # 1. Call hybrid_search_function to get relevant data
        search_results = hybrid_search_function(query_string=user_question, num_records=5, keywords=keywords_str) # Retrieve 5 records by default
        
        retrieved_chunks = search_results.get("retrieved_records", [])
        
        context_text = ""
        if retrieved_chunks:
            context_text = "\n\n".join([chunk.get("chunk_text", "") for chunk in retrieved_chunks])
            write_debug(f"Retrieved {len(retrieved_chunks)} relevant chunks for context.", append=True)
        else:
            write_debug("No relevant chunks found for context.", append=True)

        # 2. Combine LLM prompt, user question, and retrieved context
        # Assuming LLM_PROMPT_TEMPLATE is a f-string or similar that expects context and question
        combined_prompt = LLM_PROMPT_TEMPLATE.format(context=context_text, question=user_question)
        
        write_debug(f"Combined prompt for LLM:\n{combined_prompt[:500]}...", append=True) # Log first 500 chars

        # 3. Send to LLM
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
                    "content": combined_prompt
                }
            ],
            "max_tokens": 500 # Limit response length
        }

        response = requests.post(
            text_generation_url,
            headers=headers,
            json=payload,
            timeout=60 # Increased timeout for LLM response
        )
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        llm_response = response.json()
        write_debug(f"Received response from LLM: {llm_response}", append=True)

        # 4. Return LLM response object
        return llm_response

    except Exception as e:
        write_debug(f"Error generating context-aware response: {str(e)}", append=True)
        return {"error": f"Failed to generate response: {str(e)}"}

def generate_question_from_ticket_data(original_ticket_data, log_debug=True):
    """
    Generates a question based on the original ticket data.
    
    Args:
        original_ticket_data (dict): The JSON object containing the original ticket data.
        log_debug (bool, optional): If True, prints debug information to debug.txt. Defaults to True.
    """
    if log_debug:
        write_debug(f"Generating question from ticket data for ticket: {original_ticket_data.get('id')}", append=True)

    # Extract data from original_ticket_data using direct keys from the provided JSON example
    title = original_ticket_data.get('title', 'N/A')
    description = original_ticket_data.get('description', 'N/A')
    department = original_ticket_data.get('affectedUser_Department', 'N/A')
    user_role = original_ticket_data.get('affectedUser_Title', 'N/A')
    location = original_ticket_data.get('locationValue', 'N/A')
    floor = original_ticket_data.get('floorValue') 
    priority = original_ticket_data.get('priority', 'N/A')
    support_group = original_ticket_data.get('supportGroupValue', 'N/A')
    status = original_ticket_data.get('statusValue', 'N/A')
    urgency = original_ticket_data.get('urgencyValue', 'N/A')
    impact = original_ticket_data.get('impactValue', 'N/A')
    classification = original_ticket_data.get('classification', 'N/A') 

    created_date_str = original_ticket_data.get('createdDate')
    resolved_date_str = original_ticket_data.get('resolvedDate')

    # Calculate resolution_time_days
    resolution_time_days = 'N/A'
    if created_date_str and resolved_date_str:
        try:
            # Assuming ISO format, e.g., "2025-08-16T15:00:00"
            created_dt = datetime.fromisoformat(created_date_str.replace('Z', '+00:00'))
            resolved_dt = datetime.fromisoformat(resolved_date_str.replace('Z', '+00:00'))
            resolution_time_days = (resolved_dt - created_dt).days
        except ValueError:
            if log_debug:
                write_debug(f"Warning: Could not parse date strings for resolution time calculation: Created='{created_date_str}', Resolved='{resolved_date_str}'", append=True)

    # Fill the template
    formatted_question_prompt = TICKET_QUESTION_GENERATION_PROMPT.format(
        title=title,
        description=description,
        department=department,
        user_role=user_role,
        location=location,
        floor=floor,
        support_group=support_group,
        status=status,
        priority=priority,
        urgency=urgency,
        impact=impact,
        classification=classification,
        created_date=created_date_str if created_date_str else 'N/A',
        resolved_date=resolved_date_str if resolved_date_str else 'N/A',
        resolution_time_days=resolution_time_days
    )
    
    if log_debug:
        write_debug(f"Generated question prompt:\n{formatted_question_prompt}", append=True)
    
    # Send to LLM
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
                "content": formatted_question_prompt
            }
        ],
        "max_tokens": 500 # Limit response length
    }

    try:
        response = requests.post(
            text_generation_url,
            headers=headers,
            json=payload,
            timeout=60 # Increased timeout for LLM response
        )
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        llm_response = response.json()
        if log_debug:
            write_debug(f"Received response from LLM: {llm_response}", append=True)

        return llm_response

    except requests.exceptions.RequestException as e:
        if log_debug:
            write_debug(f"LLM API call failed for question generation: {e}", append=True)
        return {"error": f"Failed to generate question: API call error - {e}"}
    except Exception as e:
        if log_debug:
            write_debug(f"An unexpected error occurred during question generation: {e}", append=True)
        return {"error": f"Failed to generate question: Unexpected error - {e}"}

def get_ticket_assignment_recommendation(original_ticket, similar_tickets, generated_question_full_response, onenote_chunks, log_debug=True):
    """
    Generates a ticket assignment recommendation using the TICKET_ASSIGNMENT_PROMPT.
    Includes retry mechanism and appends query details.
    
    Args:
        original_ticket (dict): The original ticket data.
        similar_tickets (list): A list of similar historical tickets.
        generated_question_full_response (dict): The full LLM response object for the generated question.
        onenote_chunks (dict): The retrieved OneNote chunks.
        log_debug (bool, optional): If True, prints debug information to debug.txt. Defaults to True.
        
    Returns:
        dict: The JSON response from the LLM with added query details, or an error object.
    """
    text_generation_url = DATABRICKS_CONFIG['text_generation_url']
    api_key = DATABRICKS_CONFIG['api_key']

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    max_retries = 3
    for attempt in range(max_retries):
        if log_debug:
            write_debug(f"Attempt {attempt + 1}/{max_retries} to get ticket assignment recommendation.", append=True)
        
        start_time = datetime.now()

        # Prepare prompt arguments, converting complex objects to JSON strings
        # Ensure generated_question_full_response is a string for the prompt
        generated_question_str = _to_json_string_or_iterate(generated_question_full_response)
        original_ticket_str = _to_json_string_or_iterate(original_ticket)
        similar_tickets_str = _to_json_string_or_iterate(similar_tickets)
        onenote_chunks_str = _to_json_string_or_iterate(onenote_chunks)

        formatted_prompt = TICKET_ASSIGNMENT_PROMPT.format(
            generated_question_full_response=generated_question_str,
            original_ticket=original_ticket_str,
            onenote_chunks=onenote_chunks_str,
            similar_tickets=similar_tickets_str
        )

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": formatted_prompt
                }
            ],
            "max_tokens": 1000 # Allow more tokens for detailed response
        }

        try:
            response = requests.post(
                text_generation_url,
                headers=headers,
                json=payload,
                timeout=120 # Increased timeout for potentially longer LLM processing
            )
            response.raise_for_status()
            
            llm_response = response.json()
            end_time = datetime.now()
            time_taken = (end_time - start_time).total_seconds()

            # Extract content and attempt JSON parsing
            response_content = llm_response.get('choices', [{}])[0].get('message', {}).get('content', None)
            
            parsed_json = None
            if response_content:
                # Preprocess: Remove markdown code block delimiters if present
                if response_content.startswith("```json") and response_content.endswith("```"):
                    response_content = response_content[len("```json"): -len("```")].strip()
                
                try:
                    parsed_json = json.loads(response_content)
                    # Basic validation of the expected structure
                    if all(k in parsed_json for k in ["support_group_assignment", "priority_level", "analysis_summary", "confidence_score"]):
                        if log_debug:
                            write_debug(f"Successfully parsed JSON response from LLM (attempt {attempt + 1}).", parsed_json, append=True)
                        
                        # Append query details
                        parsed_json['query_details'] = {
                            'time_taken_seconds': time_taken,
                            'prompt_tokens': llm_response.get('usage', {}).get('prompt_tokens'),
                            'completion_tokens': llm_response.get('usage', {}).get('completion_tokens'),
                            'total_tokens': llm_response.get('usage', {}).get('total_tokens')
                        }
                        return parsed_json
                    else:
                        if log_debug:
                            write_debug(f"LLM response JSON format invalid (attempt {attempt + 1}). Missing expected keys.", parsed_json, append=True)
                except json.JSONDecodeError as e:
                    if log_debug:
                        write_debug(f"LLM response is not valid JSON (attempt {attempt + 1}): {e}", response_content, append=True)
            else:
                if log_debug:
                    write_debug(f"LLM response content is empty (attempt {attempt + 1}).", llm_response, append=True)

        except requests.exceptions.RequestException as e:
            if log_debug:
                write_debug(f"LLM API call failed (attempt {attempt + 1}): {e}", append=True)
        except Exception as e:
            if log_debug:
                write_debug(f"An unexpected error occurred during LLM call (attempt {attempt + 1}): {e}", append=True)
        
    if log_debug:
        write_debug(f"Failed to get valid LLM response after {max_retries} attempts.", append=True)
    return {"error": f"Failed to get valid LLM response after {max_retries} attempts."}
