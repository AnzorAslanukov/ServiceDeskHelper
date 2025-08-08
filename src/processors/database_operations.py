import psycopg2
import json
import sys
import os
from datetime import datetime
from psycopg2.extras import RealDictCursor

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
        write_debug("Successfully obtained database connection.", append=True)
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
