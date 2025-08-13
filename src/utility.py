import requests
import json
import os
import sys

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.config import DATABRICKS_CONFIG, write_debug
from src.processors.onenote_operations import hybrid_search_onenote
# Assuming prompts.py contains a variable like LLM_PROMPT_TEMPLATE
from src.prompts import LLM_PROMPT_TEMPLATE 

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

def generate_context_aware_response(user_question, keywords=None):
    """
    Generates a context-aware response using a text generation LLM,
    based on a user question and relevant data retrieved from the database.
    
    Args:
        user_question (str): The question from the user.
        keywords (list, optional): A list of strings representing keywords for the search. Defaults to None.
        
    Returns:
        dict: The response object from the LLM.
    """
    write_debug(f"Starting context-aware response generation for question: '{user_question}' with keywords: {keywords}", append=True)
    
    try:
        # Convert list of keywords to a single string if provided
        keywords_str = " ".join(keywords) if isinstance(keywords, list) else keywords

        # 1. Call hybrid_search_onenote to get relevant data
        search_results = hybrid_search_onenote(query_string=user_question, num_records=5, keywords=keywords_str) # Retrieve 5 records by default
        
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
    
ticket_description = """
EU unable to open pharmacy cabniets with badge.
unable to open med cart cabinet 
with badge. 

location : pvaillion campus. ground floor. 
time of evvent. : 8/11/2025
badge number : 488268
user : matheani
"""

# write_debug(f"LLM response:\n\n{generate_context_aware_response(f"What groups support the ticket with the following description:\n\n{ticket_description}")}")
write_debug(f"LLM response:\n\n{generate_context_aware_response("What Penn Medicine UPHS on-call groups support Citrix?")}")
