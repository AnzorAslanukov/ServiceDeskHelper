import psycopg2
import json
import sys
import os
from datetime import datetime
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector # Import register_vector

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABASE_CONFIG, ONENOTE_CHUNKS_TABLE, write_debug

def get_database_connection():
    """
    Create and return a database connection using config settings.
    
    Returns:
        psycopg2.connection: Database connection object
    """
    write_debug("Attempting to get database connection.", append=True)
    try:
        connection = psycopg2.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            database=DATABASE_CONFIG['database'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password']
        )
        # IMPORTANT: Register vector type for the connection
        register_vector(connection)
        write_debug("Successfully obtained database connection and registered vector type.", append=True)
        return connection
    except psycopg2.Error as e:
        write_debug(f"Database connection error: {str(e)}", append=True)
        raise

def onenote_notebook_exists(notebook_name):
    """
    Checks if a OneNote notebook (workbook_name) exists in the onenote_pages table.
    
    Args:
        notebook_name (str): The name of the OneNote notebook.
        
    Returns:
        bool: True if the notebook exists, False otherwise.
    """
    write_debug(f"Checking if notebook '{notebook_name}' exists.", append=True)
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        select_sql = f"SELECT EXISTS(SELECT 1 FROM {ONENOTE_CHUNKS_TABLE} WHERE notebook_name = %s)" # Changed workbook_name to notebook_name
        cursor.execute(select_sql, (notebook_name,))
        exists = cursor.fetchone()[0]
        write_debug(f"Notebook '{notebook_name}' exists: {exists}", append=True)
        return exists
    except Exception as e:
        write_debug(f"Error checking if notebook '{notebook_name}' exists: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def insert_or_update_athena_ticket(ticket_data, overwrite_existing=False):
    """
    Inserts new Athena ticket data or updates an existing record in the athena_tickets table.
    
    Args:
        ticket_data (dict): A dictionary containing ticket data, typically from extract_ticket_data.
        overwrite_existing (bool): If True, updates the record if entity_id exists.
                                   If False, skips insertion/update if entity_id exists.
                                   Defaults to False.
                                   
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    write_debug(f"Attempting to insert/update Athena ticket with entity_id: {ticket_data.get('entity_id')}", append=True)
    connection = None
    cursor = None
    
    if not ticket_data or 'entity_id' not in ticket_data:
        write_debug("Invalid ticket_data provided for insert/update.", append=True)
        return False

    entity_id = ticket_data['entity_id']

    try:
        connection = get_database_connection()
        cursor = connection.cursor()

        # Check if record exists
        cursor.execute("SELECT entity_id FROM athena_tickets WHERE entity_id = %s", (entity_id,))
        existing_record = cursor.fetchone()

        if existing_record:
            if not overwrite_existing:
                write_debug(f"Record with entity_id {entity_id} already exists. Skipping insertion (overwrite_existing=False).", append=True)
                return True # Considered successful as no error occurred
            else:
                write_debug(f"Record with entity_id {entity_id} exists. Updating record.", append=True)
                # Build UPDATE statement
                update_columns = []
                update_values = []
                
                # Exclude 'id' and 'entity_id' from update columns as they are primary/unique keys
                # Also exclude 'created_at' as it's set on creation
                for key, value in ticket_data.items():
                    if key not in ['id', 'entity_id', 'created_at']:
                        update_columns.append(f"{key} = %s")
                        # Special handling for vector types and JSONB
                        if key.endswith('_embedding'):
                            update_values.append(value) # psycopg2.extras.register_vector handles list to vector
                        elif key == 'analyst_comments':
                            update_values.append(json.dumps(value)) # Convert dict to JSON string for JSONB
                        else:
                            update_values.append(value)
                
                update_values.append(datetime.now()) # for updated_at
                update_values.append(entity_id) # for WHERE clause

                update_sql = f"""
                UPDATE athena_tickets
                SET {', '.join(update_columns)}, updated_at = %s
                WHERE entity_id = %s
                """
                cursor.execute(update_sql, tuple(update_values))
                write_debug(f"Successfully updated record for entity_id: {entity_id}", append=True)

        else:
            write_debug(f"Record with entity_id {entity_id} does not exist. Inserting new record.", append=True)
            # Build INSERT statement
            columns = []
            values = []
            placeholders = []

            for key, value in ticket_data.items():
                # Skip 'id' as it's SERIAL PRIMARY KEY
                if key == 'id':
                    continue
                columns.append(key)
                
                # Special handling for vector types and JSONB
                if key.endswith('_embedding'):
                    values.append(value) # psycopg2.extras.register_vector handles list to vector
                    placeholders.append("%s::vector")
                elif key == 'analyst_comments':
                    values.append(json.dumps(value)) # Convert dict to JSON string for JSONB
                    placeholders.append("%s::jsonb")
                else:
                    values.append(value)
                    placeholders.append("%s")
            
            # Add processed_at, created_at, updated_at
            columns.extend(['processed_at', 'created_at', 'updated_at'])
            values.extend([datetime.now(), datetime.now(), datetime.now()])
            placeholders.extend(["%s", "%s", "%s"])

            insert_sql = f"""
            INSERT INTO athena_tickets ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            """
            cursor.execute(insert_sql, tuple(values))
            write_debug(f"Successfully inserted new record for entity_id: {entity_id}", append=True)

        connection.commit()
        return True

    except Exception as e:
        write_debug(f"Error inserting/updating Athena ticket {entity_id}: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def check_table_and_columns_exist(table_name, column_names):
    """
    Checks if a given table exists and if all specified columns exist within that table.
    
    Args:
        table_name (str): The name of the table to check.
        column_names (list): A list of column names to check for existence.
        
    Returns:
        bool: True if the table and all columns exist, False otherwise.
    """
    write_debug(f"Checking existence of table '{table_name}' and columns: {column_names}", append=True)
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()

        # Check if table exists
        cursor.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (table_name,))
        table_exists = cursor.fetchone()[0]
        if not table_exists:
            write_debug(f"Error: Table '{table_name}' does not exist.", append=True)
            return False

        # Check if columns exist
        for col_name in column_names:
            cursor.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s)", (table_name, col_name))
            col_exists = cursor.fetchone()[0]
            if not col_exists:
                write_debug(f"Error: Column '{col_name}' does not exist in table '{table_name}'.", append=True)
                return False
        
        write_debug(f"Table '{table_name}' and all specified columns exist.", append=True)
        return True
    except Exception as e:
        write_debug(f"Error checking table and column existence: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def perform_hybrid_search(table_name, query_embedding, num_records, column_names, keywords=None):
    """
    Performs a hybrid search combining vector similarity and keyword matching.
    
    Args:
        table_name (str): The name of the table to search.
        query_embedding (list): The embedding vector of the query string.
        num_records (int): The number of records to retrieve.
        column_names (list): A list of column names to retrieve for each record.
        keywords (str, optional): Keywords for full-text search. Defaults to None.
        
    Returns:
        list: A list of dictionaries, where each dictionary represents a retrieved record.
    """
    write_debug(f"Performing hybrid search on table '{table_name}' for {num_records} records with keywords: '{keywords}'", append=True)
    connection = None
    cursor = None
    combined_records = []
    try:
        connection = get_database_connection()
        cursor = connection.cursor(cursor_factory=RealDictCursor) # Use RealDictCursor to get results as dictionaries

        # Construct the SELECT clause for specified columns
        select_columns_str = ", ".join(column_names)
        
        # --- 1. Vector Similarity Search ---
        vector_search_sql = f"""
        SELECT {select_columns_str}, 1 - (embedding <=> %s::vector) AS similarity
        FROM {table_name}
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """
        write_debug(f"Executing vector search query: {vector_search_sql}", append=True)
        cursor.execute(vector_search_sql, (query_embedding, query_embedding, num_records))
        vector_results = cursor.fetchall()
        write_debug(f"Retrieved {len(vector_results)} records from vector search.", append=True)
        
        combined_records.extend(vector_results)

        # --- 2. Keyword Search (if keywords provided) ---
        if keywords:
            keyword_search_sql = f"""
            SELECT {select_columns_str}, 0.0 AS similarity -- Assign a default similarity for keyword matches
            FROM {table_name}
            WHERE chunk_text ILIKE %s -- Assuming 'chunk_text' is the column for keyword search
            LIMIT %s;
            """
            # Add wildcards for broader search
            search_pattern = f"%{keywords}%"
            write_debug(f"Executing keyword search query: {keyword_search_sql} with pattern: {search_pattern}", append=True)
            cursor.execute(keyword_search_sql, (search_pattern, num_records))
            keyword_results = cursor.fetchall()
            write_debug(f"Retrieved {len(keyword_results)} records from keyword search.", append=True)

            # Combine and de-duplicate results
            # Prioritize vector results, add unique keyword results
            existing_ids = {record['id'] for record in combined_records if 'id' in record} # Assuming 'id' is a unique identifier
            
            for record in keyword_results:
                if 'id' in record and record['id'] not in existing_ids:
                    combined_records.append(record)
                    existing_ids.add(record['id'])
                elif 'id' not in record: # If no ID, just append (less ideal but handles cases without ID)
                    combined_records.append(record)
        
        write_debug(f"Successfully retrieved {len(combined_records)} records from hybrid search.", append=True)
        return combined_records
    except Exception as e:
        write_debug(f"Error performing hybrid search on table '{table_name}': {str(e)}", append=True)
        return []
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def delete_onenote_records(name_value, field_type):
    """
    Deletes records from the onenote_chunks table based on section_name or notebook_name.
    
    Args:
        name_value (str): The value of the section_name or notebook_name to delete.
        field_type (str): 'section' to delete by section_name, 'notebook' to delete by notebook_name.
        
    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    write_debug(f"Attempting to delete records for {field_type}: {name_value}", append=True)
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        
        if field_type == 'section':
            delete_sql = f"DELETE FROM {ONENOTE_CHUNKS_TABLE} WHERE section_name = %s"
            write_debug(f"Deleting records for section: {name_value}", append=True)
        elif field_type == 'notebook':
            delete_sql = f"DELETE FROM {ONENOTE_CHUNKS_TABLE} WHERE notebook_name = %s"
            write_debug(f"Deleting records for notebook: {name_value}", append=True)
        else:
            write_debug(f"Invalid field_type provided for deletion: {field_type}", append=True)
            return False
            
        cursor.execute(delete_sql, (name_value,))
        connection.commit()
        write_debug(f"Successfully deleted records for {field_type}: {name_value}", append=True)
        return True
    except Exception as e:
        write_debug(f"Error deleting records for {field_type} {name_value}: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def onenote_section_exists(section_name):
    """
    Checks if a OneNote section (section_name) exists in the onenote_pages table.
    
    Args:
        section_name (str): The name of the OneNote section.
        
    Returns:
        bool: True if the section exists, False otherwise.
    """
    write_debug(f"Checking if section '{section_name}' exists.", append=True)
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        select_sql = f"SELECT EXISTS(SELECT 1 FROM {ONENOTE_CHUNKS_TABLE} WHERE section_name = %s)"
        cursor.execute(select_sql, (section_name,))
        exists = cursor.fetchone()[0]
        write_debug(f"Section '{section_name}' exists: {exists}", append=True)
        return exists
    except Exception as e:
        write_debug(f"Error checking if section '{section_name}' exists: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def add_onenote_chunk(chunk_title, chunk_text, chunk_index, notebook_name, section_name, embedding):
    """
    Adds a new chunk of OneNote data to the onenote_chunks table.
    
    Args:
        chunk_title (str): The title of the chunk.
        chunk_text (str): The text content of the chunk.
        chunk_index (int): The index of the chunk within its section.
        notebook_name (str): The name of the OneNote notebook.
        section_name (str): The name of the OneNote section.
        embedding (list): The embedding vector for the chunk text.
        
    Returns:
        bool: True if the chunk was added successfully, False otherwise.
    """
    write_debug(f"Attempting to add chunk for section: {section_name}, notebook: {notebook_name}", append=True)
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        
        insert_sql = f"""
        INSERT INTO {ONENOTE_CHUNKS_TABLE} (
            chunk_title, chunk_text, chunk_index, notebook_name, section_name, embedding
        ) VALUES (%s, %s, %s, %s, %s, %s::vector)
        """
        
        cursor.execute(insert_sql, (
            chunk_title, chunk_text, chunk_index, notebook_name, section_name, embedding
        ))
        connection.commit()
        write_debug(f"Successfully added chunk for section: {section_name}", append=True)
        return True
    except Exception as e:
        write_debug(f"Error adding chunk for section {section_name}: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
