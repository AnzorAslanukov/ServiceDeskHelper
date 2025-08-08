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
from src.processors.database_operations import onenote_notebook_exists, onenote_section_exists

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
        return "".join(full_text).replace('\n', '').replace('\r', '').replace(' ', '')
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
    
