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
    
    auth_url = ATHENA_CONFIG.get('auth_url')
    if not auth_url:
        write_debug("Error: ATHENA_AUTH_URL is not set in config. Please check your .env file.", append=True)
        raise Exception("ATHENA_AUTH_URL is not configured.")

    token_url = f"{auth_url}/oauth2/token"
    
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
    
def search_ticket_by_id(ticket_id):
    """
    Retrieves ticket details from Athena using a ticket ID and a JSON template.
    
    Args:
        ticket_id (str): The ID of the ticket (e.g., "IR1234567").
    
    Returns:
        dict: The response JSON containing ticket data, or None if failed.
    """
    try:
        token = _get_athena_token()
        
        url = f"{ATHENA_CONFIG['base_url']}view/workitem?type=incident"
        write_debug(f"URL:\n{url}", append=True)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"  
        }
        
        # Replace placeholder in template with actual ticket ID
        json_payload_str = ATHENA_CONFIG['json_template'].replace("{{TICKET_ID}}", ticket_id)
        json_payload = json.loads(json_payload_str)

        write_debug(f"Making Athena API request for ticket ID: {ticket_id}", {
            "url": url,
            "json_payload": json_payload
        }, append=True)
        
        response = requests.post(url, headers=headers, json=json_payload, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            
            write_debug(f"Successfully retrieved ticket details for {ticket_id}", {
                "status_code": response.status_code,
                "result_count": len(response_data.get("result", []))
            }, append=True)
            
            return response_data
        else:
            write_debug(f"Failed to get ticket details for {ticket_id}: {response.status_code} - {response.text}", append=True)
            return None
            
    except Exception as e:
        write_debug(f"Error retrieving ticket details for {ticket_id}: {str(e)}", append=True)
        raise Exception(f"Error retrieving ticket details for {ticket_id}: {str(e)}")

def get_all_ticket_details(entity_id):
    """
    Retrieves all details for a ticket directly by its entity ID.
    
    Args:
        entity_id (str): The entity ID (GUID format, e.g., "1de4eb13-42d9-9aa2-1fcc-7322d8395ecc").
    
    Returns:
        dict: The response JSON containing all ticket data, or None if failed.
    """
    try:
        token = _get_athena_token()
        
        url = f"{ATHENA_CONFIG['base_url']}incident/{entity_id}"
        write_debug(f"URL for get_all_details:\n{url}", append=True)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"  
        }
        
        write_debug(f"Making Athena API GET request for entity ID: {entity_id}", {
            "url": url
        }, append=True)
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            
            write_debug(f"Successfully retrieved all details for entity ID: {entity_id}", {
                "status_code": response.status_code,
                "data_keys": list(response_data.keys()) # Log keys to show data is present
            }, append=True)
            
            return response_data
        else:
            write_debug(f"Failed to get all details for entity ID {entity_id}: {response.status_code} - {response.text}", append=True)
            return None
            
    except Exception as e:
        write_debug(f"Error retrieving all details for entity ID {entity_id}: {str(e)}", append=True)
        raise Exception(f"Error retrieving all details for entity ID {entity_id}: {str(e)}")

