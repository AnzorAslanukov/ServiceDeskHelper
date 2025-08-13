import requests
import json
import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import ATHENA_CONFIG, write_debug
from src.utility import get_text_embeddings

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

def extract_ticket_data(raw_ticket_data):
    """
    Extracts and transforms specific fields from a raw Athena ticket JSON object
    into a new JSON object matching the athena_tickets table schema.
    
    Args:
        raw_ticket_data (dict): The raw JSON object from get_all_ticket_details.
        
    Returns:
        dict: A new JSON object with extracted and transformed data.
    """
    write_debug("Starting data extraction and transformation for ticket.", append=True)
    
    if not raw_ticket_data:
        write_debug("No raw ticket data provided for extraction.", append=True)
        return None

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

    # Helper to convert date strings to ISO format or None
    def to_iso_datetime(date_str):
        if date_str:
            try:
                # Handle potential timezone info in string
                dt_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt_obj.isoformat()
            except ValueError:
                write_debug(f"Warning: Could not parse date string: {date_str}", append=True)
                return None
        return None

    extracted_data = {}

    try:
        # Primary identifiers
        extracted_data['entity_id'] = raw_ticket_data.get('entityId')
        extracted_data['ticket_id'] = raw_ticket_data.get('id')
        
        # Core ticket information
        extracted_data['title'] = raw_ticket_data.get('title')
        extracted_data['description'] = raw_ticket_data.get('description')
        extracted_data['escalated'] = raw_ticket_data.get('escalated', False)
        extracted_data['resolution_description'] = raw_ticket_data.get('resolutionDescription')
        extracted_data['message'] = raw_ticket_data.get('message')
        extracted_data['priority'] = raw_ticket_data.get('priority')
        
        # Location information
        extracted_data['location_name'] = get_nested_value(raw_ticket_data, ['location', 'name'])
        extracted_data['floor_name'] = get_nested_value(raw_ticket_data, ['floor', 'name'])
        extracted_data['affect_patient_care'] = raw_ticket_data.get('affect_Patient_Care')
        extracted_data['confirmed_resolution'] = get_nested_value(raw_ticket_data, ['confrimed_Resolution', 'name'])
        
        # Dates
        extracted_data['created_date'] = to_iso_datetime(raw_ticket_data.get('createdDate'))
        extracted_data['last_modified'] = to_iso_datetime(raw_ticket_data.get('lastModified'))
        
        # Affected User (minimal info)
        extracted_data['affected_user_domain'] = get_nested_value(raw_ticket_data, ['affectedUser', 'domain'])
        extracted_data['affected_user_company'] = get_nested_value(raw_ticket_data, ['affectedUser', 'company'])
        extracted_data['affected_user_department'] = get_nested_value(raw_ticket_data, ['affectedUser', 'department'])
        extracted_data['affected_user_title'] = get_nested_value(raw_ticket_data, ['affectedUser', 'title'])
        
        # Assigned To User (minimal info)
        extracted_data['assigned_to_user_domain'] = get_nested_value(raw_ticket_data, ['assignedToUser', 'domain'])
        extracted_data['assigned_to_user_company'] = get_nested_value(raw_ticket_data, ['assignedToUser', 'company'])
        extracted_data['assigned_to_user_department'] = get_nested_value(raw_ticket_data, ['assignedToUser', 'department'])
        extracted_data['assigned_to_user_title'] = get_nested_value(raw_ticket_data, ['assignedToUser', 'title'])
        
        # Resolved By User (minimal info)
        extracted_data['resolved_by_user_domain'] = get_nested_value(raw_ticket_data, ['resolvedByUser', 'domain'])
        extracted_data['resolved_by_user_company'] = get_nested_value(raw_ticket_data, ['resolvedByUser', 'company'])
        extracted_data['resolved_by_user_department'] = get_nested_value(raw_ticket_data, ['resolvedByUser', 'department'])
        extracted_data['resolved_by_user_title'] = get_nested_value(raw_ticket_data, ['resolvedByUser', 'title'])
        
        # Analyst Comments
        analyst_comments_list = raw_ticket_data.get('analystComments', [])
        analyst_comments_dict = {}
        for comment in analyst_comments_list:
            entered_date = to_iso_datetime(comment.get('enteredDate'))
            comment_text = comment.get('comment')
            if entered_date and comment_text:
                analyst_comments_dict[entered_date] = comment_text
        extracted_data['analyst_comments'] = analyst_comments_dict
        
        # Vector embeddings
        title_text = extracted_data.get('title')
        description_text = extracted_data.get('description')
        
        if title_text:
            embedding = get_text_embeddings(title_text)
            extracted_data['title_embedding'] = embedding
            write_debug(f"Generated title_embedding (first 5 elements): {embedding[:5]}...", append=True)
        else:
            extracted_data['title_embedding'] = None
            write_debug("Warning: Title is missing, cannot generate title_embedding.", append=True)
            
        if description_text:
            embedding = get_text_embeddings(description_text)
            extracted_data['description_embedding'] = embedding
            write_debug(f"Generated description_embedding (first 5 elements): {embedding[:5]}...", append=True)
        else:
            extracted_data['description_embedding'] = None
            write_debug("Warning: Description is missing, cannot generate description_embedding.", append=True)

        write_debug("Successfully extracted and transformed ticket data.", data={k: v[:5] if isinstance(v, list) and k.endswith('_embedding') else v for k, v in extracted_data.items()}, append=True)
        return extracted_data
        
    except Exception as e:
        write_debug(f"Error during data extraction and transformation: {str(e)}", append=True)
        return None

# Example usage of the functions
# Replace "IR9882530" with an actual ticket ID for testing search_ticket_by_id
# athena_search_response = search_ticket_by_id("IR9882530")
# write_debug("Athena Search Response:", data=athena_search_response, append=True)

# Replace "837f734e-a72d-d40f-bfa3-1824854cb715" with an actual entity ID for testing get_all_ticket_details
raw_ticket_data = get_all_ticket_details("837f734e-a72d-d40f-bfa3-1824854cb715")
if raw_ticket_data:
    extracted_ticket_data = extract_ticket_data(raw_ticket_data)
    # write_debug("Extracted Ticket Data:", data=extracted_ticket_data, append=True)
else:
    write_debug("Failed to retrieve raw ticket data, skipping extraction.", append=True)
