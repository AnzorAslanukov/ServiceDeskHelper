import requests
import json
import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import ATHENA_CONFIG, write_debug

# Global variable to store the token and its expiration time
_ATHENA_TOKEN = None
_ATHENA_TOKEN_EXPIRY = None

def _get_athena_token():
    """
    Obtains an authentication token from the Athena API.
    Tokens are cached and refreshed when expired.
    
    Returns:
        str: The JWT token.
    """
    global _ATHENA_TOKEN, _ATHENA_TOKEN_EXPIRY
    
    # Check if token exists and is not expired
    if _ATHENA_TOKEN and _ATHENA_TOKEN_EXPIRY and datetime.now() < _ATHENA_TOKEN_EXPIRY:
        write_debug("Using cached Athena token.", append=True)
        return _ATHENA_TOKEN

    write_debug("Attempting to obtain new Athena token.", append=True)
    
    base_url = ATHENA_CONFIG.get('base_url')
    if not base_url:
        write_debug("Error: ATHENA_BASE_URL is not set in config. Please check your .env file.", append=True)
        raise Exception("ATHENA_BASE_URL is not configured.")

    token_url = f"{base_url}/oauth2/token"
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    payload = {
        'username': ATHENA_CONFIG['username'],
        'password': ATHENA_CONFIG['password'],
        'grant_type': 'password',
        'client_id': ATHENA_CONFIG['client_id']
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=payload, timeout=30)
        response.raise_for_status() # Raise an exception for HTTP errors
        
        token_data = response.json()
        _ATHENA_TOKEN = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600) # Default to 1 hour if not provided
        _ATHENA_TOKEN_EXPIRY = datetime.now() + timedelta(seconds=expires_in - 60) # Expire 60 seconds early for buffer
        
        if _ATHENA_TOKEN:
            write_debug("Successfully obtained new Athena token.", append=True)
            return _ATHENA_TOKEN
        else:
            write_debug(f"Failed to obtain Athena token: 'access_token' not found in response.", token_data, append=True)
            raise Exception("Failed to obtain Athena token.")
            
    except requests.exceptions.RequestException as e:
        write_debug(f"Error obtaining Athena token: {str(e)}", append=True)
        raise Exception(f"Error obtaining Athena token: {str(e)}")
    except Exception as e:
        write_debug(f"An unexpected error occurred while obtaining Athena token: {str(e)}", append=True)
        raise Exception(f"An unexpected error occurred while obtaining Athena token: {str(e)}")

write_debug(f"Athena JSON object:\n\n{_get_athena_token()}", append=True) 
