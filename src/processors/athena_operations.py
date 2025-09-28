import requests
import json
import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import ATHENA_CONFIG, write_debug
from src.utility import get_text_embeddings, generate_question_from_ticket_data, get_nested_value, get_ticket_assignment_recommendation
from src.processors.database_operations import insert_or_update_athena_ticket, search_athena_tickets_by_embedding
from src.processors.onenote_operations import hybrid_search_onenote
from src.prompts import TICKET_JUDGMENT_PROMPT

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
    
def search_ticket_by_id(ticket_id, log_debug=True):
    """
    Retrieves ticket details from Athena using a ticket ID and a JSON template.

    Args:
        ticket_id (str): The ID of the ticket (e.g., "IR1234567").
        log_debug (bool): If True, prints debug information to debug.txt. Defaults to True.

    Returns:
        dict: The response JSON containing ticket data, or None if failed.
    """
    try:
        token = _get_athena_token()

        # Determine workitem type based on ticket ID prefix
        prefix = ticket_id[:2].upper()
        if prefix == 'IR':
            workitem_type = 'incident'
        elif prefix == 'SR':
            workitem_type = 'servicerequest'
        else:
            workitem_type = 'incident'  # Default to incident for unknown prefixes

        url = f"{ATHENA_CONFIG['base_url']}view/workitem?type={workitem_type}"
        if log_debug:
            write_debug(f"Workitem type: {workitem_type}", append=True)
            write_debug(f"URL:\n{url}", append=True)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"  
        }
        
        # Replace placeholder in template with actual ticket ID
        json_payload_str = ATHENA_CONFIG['json_template'].replace("{{TICKET_ID}}", ticket_id)
        json_payload = json.loads(json_payload_str)

        if log_debug:
            write_debug(f"Making Athena API request for ticket ID: {ticket_id}", {
                "url": url,
                "json_payload": json_payload
            }, append=True)
        
        response = requests.post(url, headers=headers, json=json_payload, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            
            if log_debug:
                write_debug(f"Successfully retrieved ticket details for {ticket_id}", {
                    "status_code": response.status_code,
                    "result_count": len(response_data.get("result", []))
                }, append=True)
            
            return response_data
        else:
            if log_debug:
                write_debug(f"Failed to get ticket details for {ticket_id}: {response.status_code} - {response.text}", append=True)
            return None
            
    except Exception as e:
        if log_debug:
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
        extracted_data['tier_queue_name'] = get_nested_value(raw_ticket_data, ['tierQueue', 'name'])
        
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

def process_athena_tickets_in_range(start_ticket_id):
    """
    Iterates through a range of ticket IDs, fetches data, extracts relevant fields,
    and inserts/updates them into the athena_tickets table.
    
    Args:
        start_ticket_id (str): The starting ticket ID (e.g., "ticket_number").
    """
    write_debug(f"Starting process_athena_tickets_in_range from {start_ticket_id}", append=True)

    # Extract the non-numeric prefix (e.g., "IR") from the ticket ID
    prefix = start_ticket_id[:2] 
    # Extract the numeric part of the ticket ID and convert to integer
    current_num = int(start_ticket_id[2:])
    
    tickets_found_count = 0
    iterations_count = 0
    records_added_count = 0
    consecutive_failures = 0 # New counter for consecutive failures
    MAX_CONSECUTIVE_FAILURES = 1000 # Define the threshold for breaking the loop
    
    while True:
        iterations_count += 1
        current_ticket_id = f"{prefix}{current_num}" # Reconstruct the ticket ID for the current iteration
        
        # Clear debug.txt every 5 iterations to prevent bloating
        clear_file = (iterations_count % 5 == 1) # Clear on 1st, 6th, 11th, etc. iteration
        write_debug(f"Processing ticket number: {current_ticket_id}", append=not clear_file)

        try:
            # 1. Call search_ticket_by_id with log_debug=False
            ticket_response = search_ticket_by_id(current_ticket_id, log_debug=False)
            
            if ticket_response and ticket_response.get('resultCount', 0) > 0:
                consecutive_failures = 0 # Reset consecutive failures on success
                tickets_found_count += 1
                # Assuming the first result is the relevant one
                entity_id = ticket_response['result'][0].get('entityId')
                
                if entity_id:
                    # 2. Get full JSON object payload
                    raw_ticket_data = get_all_ticket_details(entity_id)
                    
                    if raw_ticket_data:
                        # 3. Extract relevant data
                        extracted_ticket_data = extract_ticket_data(raw_ticket_data)
                        
                        if extracted_ticket_data:
                            # 4. Insert/update into athena_tickets table
                            success = insert_or_update_athena_ticket(extracted_ticket_data, overwrite_existing=True)
                            if success:
                                records_added_count += 1
                                write_debug(f"Successfully processed and added/updated record for {current_ticket_id}.", append=True)
                            else:
                                write_debug(f"Failed to add/update record for {current_ticket_id}.", append=True)
                        else:
                            write_debug(f"Extraction of data failed for {current_ticket_id}.", append=True)
                    else:
                        write_debug(f"Failed to get all details for entity ID from {current_ticket_id}.", append=True)
                else:
                    write_debug(f"No entityId found for ticket {current_ticket_id}.", append=True)
            else:
                # No ticket found by search_ticket_by_id
                consecutive_failures += 1
                write_debug(f"Ticket {current_ticket_id} not found by search_ticket_by_id. Consecutive failures: {consecutive_failures}", append=True)
                
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    write_debug(f"Breaking loop: {MAX_CONSECUTIVE_FAILURES} consecutive failures to find tickets.", append=True)
                    break # Break the loop if consecutive failures reach the threshold
        
        except Exception as e:
            consecutive_failures += 1 # Count exception as a failure
            write_debug(f"An error occurred while processing ticket {current_ticket_id}: {str(e)}. Consecutive failures: {consecutive_failures}", append=True)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                write_debug(f"Breaking loop: {MAX_CONSECUTIVE_FAILURES} consecutive failures (including errors).", append=True)
                break # Break the loop if consecutive failures reach the threshold
        
        current_num += 1 # Increment ticket number for the next iteration (counting up)

    write_debug("--- Athena Ticket Processing Summary ---", append=True)
    write_debug(f"Tickets found by search_ticket_by_id: {tickets_found_count}", append=True)
    write_debug(f"Ticket numbers iterated through: {iterations_count}", append=True)
    write_debug(f"Records added/updated in athena_tickets table: {records_added_count}", append=True)

def find_similar_tickets(ticket_id_str, num_tickets_title=3, num_tickets_description=3, log_debug=True):
    """
    Retrieves display name and description for a given ticket ID
    and logs them to debug.txt.
    
    Args:
        ticket_id_str (str): The ID of the ticket (e.g., "ticket_number").
        num_tickets_title (int, optional): Number of tickets to search by title. Defaults to 3.
        num_tickets_description (int, optional): Number of tickets to search by description. Defaults to 3.
        log_debug (bool, optional): If True, prints debug information to debug.txt. Defaults to True.
    """
    if log_debug:
        write_debug(f"Attempting to retrieve display name and description for ticket: {ticket_id_str}", append=True)
    all_found_tickets = []
    try:
        ticket_response = search_ticket_by_id(ticket_id_str, log_debug=False)
        
        if ticket_response and ticket_response.get('resultCount', 0) > 0:
            ticket_data = ticket_response['result'][0]
            display_name = ticket_data.get('displayName')
            description = ticket_data.get('description')
            
            if log_debug:
                write_debug(f"Ticket Display Name: {display_name}", append=True)
                write_debug(f"Ticket Description: {description}", append=True)

            # Add original ticket data to the results
            original_ticket_record = dict(ticket_data) # Convert to dict
            original_ticket_record['source'] = 'original_query_ticket'
            # Normalize entityId to entity_id for consistency in duplicate checking
            if 'entityId' in original_ticket_record:
                original_ticket_record['entity_id'] = original_ticket_record.pop('entityId')
            all_found_tickets.append(original_ticket_record)

            if display_name and num_tickets_title is not None:
                display_name_embedding = get_text_embeddings(display_name)
                if log_debug:
                    write_debug(f"Display Name Embedding (first 5 elements): {display_name_embedding[:5]}...", append=True)
                if display_name_embedding:
                    title_search_results = search_athena_tickets_by_embedding(
                        display_name_embedding, num_tickets_title, search_by_description=False
                    )
                    for record in title_search_results:
                        record['source'] = 'ticket_title_search'
                        all_found_tickets.append(dict(record)) # Convert RealDictRow to dict
                    if log_debug:
                        write_debug(f"Found {len(title_search_results)} tickets by title search.", append=True)
            else:
                if log_debug:
                    write_debug("Warning: Display Name is missing or num_tickets_title is None, cannot perform title embedding search.", append=True)

            if description and num_tickets_description is not None:
                description_embedding = get_text_embeddings(description)
                if log_debug:
                    write_debug(f"Description Embedding (first 5 elements): {description_embedding[:5]}...", append=True)
                if description_embedding:
                    description_search_results = search_athena_tickets_by_embedding(
                        description_embedding, num_tickets_description, search_by_description=True
                    )
                    for record in description_search_results:
                        record['source'] = 'ticket_description_search'
                        all_found_tickets.append(dict(record)) # Convert RealDictRow to dict
                    if log_debug:
                        write_debug(f"Found {len(description_search_results)} tickets by description search.", append=True)
            else:
                if log_debug:
                    write_debug("Warning: Description is missing or num_tickets_description is None, cannot perform description embedding search.", append=True)
        else:
            if log_debug:
                write_debug(f"Ticket {ticket_id_str} not found or no results returned by search_ticket_by_id.", append=True)
            
    except Exception as e:
        if log_debug:
            write_debug(f"Error in find_similar_tickets for {ticket_id_str}: {str(e)}", append=True)
    
    # Process for duplicates and prioritize original ticket
    unique_found_tickets = []
    seen_entity_ids = set()
    
    # First, add the original query ticket if it exists
    original_ticket_record = None
    for record in all_found_tickets:
        if record.get('source') == 'original_query_ticket':
            original_ticket_record = record
            break
    
    if original_ticket_record:
        unique_found_tickets.append(original_ticket_record)
        seen_entity_ids.add(original_ticket_record.get('entity_id'))
        if log_debug:
            write_debug(f"Prioritizing original query ticket: {original_ticket_record.get('entity_id')}", append=True)

    # Then, add other tickets, skipping duplicates or replacing if original was added later
    for record in all_found_tickets:
        entity_id = record.get('entity_id')
        if entity_id and entity_id not in seen_entity_ids:
            unique_found_tickets.append(record)
            seen_entity_ids.add(entity_id)
        elif entity_id and record.get('source') == 'original_query_ticket' and record not in unique_found_tickets:
            # This case handles if original_ticket_record was not found in the first pass
            # and a duplicate was added from search results. Replace the duplicate with original.
            # This part is mostly defensive programming if original_ticket_record was not found first.
            for i, existing_record in enumerate(unique_found_tickets):
                if existing_record.get('entity_id') == entity_id:
                    unique_found_tickets[i] = record # Replace with the original
                    if log_debug:
                        write_debug(f"Replaced duplicate with original ticket: {entity_id}", append=True)
                    break
    
    # Remove embedding fields before returning
    for record in unique_found_tickets:
        record.pop('title_embedding', None)
        record.pop('description_embedding', None)
    
    return unique_found_tickets

def athena_ticket_advisor(ticket_number, log_debug=True):
    """
    Provides advice related to an Athena ticket.
    
    Args:
        ticket_number (str): The ID of the ticket (e.g., "IR1234567").
        log_debug (bool, optional): If True, prints debug information to debug.txt. Defaults to True.
    """
    if log_debug:
        write_debug(f"Athena Ticket Advisor initiated for ticket: {ticket_number}", append=True)
    
    all_tickets_payload = find_similar_tickets(ticket_number, log_debug=log_debug)
    
    original_ticket = None
    similar_tickets = []
    
    for ticket in all_tickets_payload:
        if ticket.get('source') == 'original_query_ticket':
            original_ticket = ticket
        else:
            similar_tickets.append(ticket)
            
    if log_debug:
        write_debug(f"Original Ticket: {original_ticket.get('ticket_id') if original_ticket else 'N/A'}", append=True)
        write_debug(f"Number of Similar Tickets found: {len(similar_tickets)}", append=True)
    
    generated_question_full_response = None
    generated_question_text = None
    if original_ticket:
        generated_question_full_response = generate_question_from_ticket_data(original_ticket, log_debug=log_debug)
        if log_debug:
            write_debug(f"Generated Question (full response): {generated_question_full_response}", append=True)
        
        # Extract the actual question text from the full LLM response
        if isinstance(generated_question_full_response, dict) and 'choices' in generated_question_full_response:
            generated_question_text = generated_question_full_response.get('choices', [{}])[0].get('message', {}).get('content', None)
            if generated_question_text:
                generated_question_text = generated_question_text.strip().strip('"').replace('\\n', '\n')
                if log_debug:
                    write_debug(f"Extracted generated question text: {generated_question_text}", append=True)
        
    onenote_chunks = None
    if generated_question_text: # Use the extracted text for the search
        onenote_chunks = hybrid_search_onenote(generated_question_text, num_records=3, log_debug=log_debug)
        if log_debug:
            write_debug(f"OneNote Chunks: {onenote_chunks}", append=True)

    # Get ticket assignment recommendation
    ticket_assignment_recommendation = get_ticket_assignment_recommendation(
        original_ticket,
        similar_tickets,
        generated_question_full_response,
        onenote_chunks,
        log_debug=log_debug
    )
    if log_debug:
        write_debug(f"Ticket Assignment Recommendation: {ticket_assignment_recommendation}", append=True)

    return ticket_assignment_recommendation

def athena_ticket_judgment(ticket_number, log_debug=True):
    """
    Judges the quality and completeness of an Athena ticket by analyzing its content,
    identifying missing information, and providing recommendations based on similar
    historical tickets and documentation.

    Args:
        ticket_number (str): The ID of the ticket (e.g., "IR1234567").
        log_debug (bool): If True, prints debug information to debug.txt. Defaults to True.

    Returns:
        dict: JSON object containing judgment analysis with missing information,
              inconsistencies, recommendations, and quality assessment.
    """
    if log_debug:
        write_debug(f"Athena Ticket Judgment initiated for ticket: {ticket_number}", append=True)

    try:
        # 1. Get original ticket data
        ticket_response = search_ticket_by_id(ticket_number, log_debug=log_debug)
        if not ticket_response or ticket_response.get('resultCount', 0) == 0:
            if log_debug:
                write_debug(f"No ticket found for {ticket_number}", append=True)
            return {"error": f"No ticket found for {ticket_number}"}

        entity_id = ticket_response['result'][0].get('entityId')
        if not entity_id:
            if log_debug:
                write_debug(f"No entity ID found for ticket {ticket_number}", append=True)
            return {"error": f"No entity ID found for ticket {ticket_number}"}

        raw_ticket_data = get_all_ticket_details(entity_id)
        if not raw_ticket_data:
            if log_debug:
                write_debug(f"Failed to get full ticket details for {ticket_number}", append=True)
            return {"error": f"Failed to get full ticket details for {ticket_number}"}

        original_ticket = extract_ticket_data(raw_ticket_data)
        if not original_ticket:
            if log_debug:
                write_debug(f"Failed to extract ticket data for {ticket_number}", append=True)
            return {"error": f"Failed to extract ticket data for {ticket_number}"}

        if log_debug:
            write_debug(f"Retrieved original ticket data for {ticket_number}", append=True)

        # 2. Find similar tickets
        all_tickets_payload = find_similar_tickets(ticket_number, log_debug=log_debug)
        similar_tickets = [ticket for ticket in all_tickets_payload if ticket.get('source') != 'original_query_ticket']

        if log_debug:
            write_debug(f"Found {len(similar_tickets)} similar tickets", append=True)

        # 3. Search OneNote for relevant documentation
        generated_question_response = generate_question_from_ticket_data(original_ticket, log_debug=log_debug)
        if isinstance(generated_question_response, dict) and 'error' in generated_question_response:
            if log_debug:
                write_debug(f"Failed to generate question: {generated_question_response['error']}", append=True)
            return generated_question_response

        # Extract question text
        generated_question_text = None
        if isinstance(generated_question_response, dict) and 'choices' in generated_question_response:
            generated_question_text = generated_question_response.get('choices', [{}])[0].get('message', {}).get('content', None)
            if generated_question_text:
                generated_question_text = generated_question_text.strip().strip('"').replace('\\n', '\n')

        onenote_chunks = None
        if generated_question_text:
            onenote_chunks = hybrid_search_onenote(generated_question_text, num_records=3, log_debug=log_debug)
            if log_debug:
                write_debug(f"Retrieved OneNote chunks: {onenote_chunks}", append=True)
        else:
            if log_debug:
                write_debug("No question text generated for OneNote search", append=True)

        # 4. Prepare context for LLM
        from src.utility import _to_json_string_or_iterate

        original_ticket_str = _to_json_string_or_iterate(original_ticket)
        similar_tickets_str = _to_json_string_or_iterate(similar_tickets)
        onenote_chunks_str = _to_json_string_or_iterate(onenote_chunks)

        formatted_prompt = TICKET_JUDGMENT_PROMPT.format(
            original_ticket=original_ticket_str,
            onenote_chunks=onenote_chunks_str,
            similar_tickets=similar_tickets_str
        )

        # 5. Call LLM with TICKET_JUDGMENT_PROMPT
        from src.config import DATABRICKS_CONFIG
        import requests

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
                    "content": formatted_prompt
                }
            ],
            "max_tokens": 1500  # Allow more tokens for detailed judgment response
        }

        if log_debug:
            write_debug(f"Sending judgment request to LLM for ticket {ticket_number}", append=True)

        response = requests.post(
            text_generation_url,
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        llm_response = response.json()

        # 6. Parse and return JSON response
        response_content = llm_response.get('choices', [{}])[0].get('message', {}).get('content', None)

        if response_content:
            # Remove markdown code block delimiters if present
            if response_content.startswith("```json") and response_content.endswith("```"):
                response_content = response_content[len("```json"): -len("```")].strip()

            try:
                parsed_json = json.loads(response_content)
                if log_debug:
                    write_debug(f"Successfully parsed judgment JSON response for ticket {ticket_number}", parsed_json, append=True)
                return parsed_json
            except json.JSONDecodeError as e:
                if log_debug:
                    write_debug(f"Failed to parse LLM response as JSON: {e}", response_content, append=True)
                return {"error": f"Failed to parse LLM response as JSON: {e}"}
        else:
            if log_debug:
                write_debug("LLM response content is empty", llm_response, append=True)
            return {"error": "LLM response content is empty"}

    except Exception as e:
        if log_debug:
            write_debug(f"Error in athena_ticket_judgment for {ticket_number}: {str(e)}", append=True)
        return {"error": f"Error in athena_ticket_judgment: {str(e)}"}

# IR9850334
# ticket_assignment_recommendation = athena_ticket_advisor("ir9980245") 
# write_debug("Final Ticket Assignment Recommendation from example call:\n", data=ticket_assignment_recommendation, append=True)

# write_debug("", data=search_ticket_by_id("ir9980245", log_debug=False))
# write_debug("Similar tickets:\n", data=find_similar_tickets("SR9980183", log_debug=False), append=True)
# write_debug("Similar tickets:\n", data=athena_ticket_judgment("IR9957502", log_debug=False), append=True) 