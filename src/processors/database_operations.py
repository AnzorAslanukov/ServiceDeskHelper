import psycopg2
import json
import sys
import os
from datetime import datetime
from psycopg2.extras import RealDictCursor

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import DATABASE_CONFIG, ONENOTE_PAGES_TABLE, write_debug

def get_database_connection():
    """
    Create and return a database connection using config settings.
    
    Returns:
        psycopg2.connection: Database connection object
    """
    try:
        connection = psycopg2.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            database=DATABASE_CONFIG['database'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password']
        )
        return connection
    except psycopg2.Error as e:
        write_debug("Database connection error", str(e))
        raise

def onenote_notebook_exists(notebook_name):
    """
    Checks if a OneNote notebook (workbook_name) exists in the onenote_pages table.
    
    Args:
        notebook_name (str): The name of the OneNote notebook.
        
    Returns:
        bool: True if the notebook exists, False otherwise.
    """
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        select_sql = f"SELECT EXISTS(SELECT 1 FROM {ONENOTE_PAGES_TABLE} WHERE workbook_name = %s)"
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

def onenote_section_exists(section_name):
    """
    Checks if a OneNote section (section_name) exists in the onenote_pages table.
    
    Args:
        section_name (str): The name of the OneNote section.
        
    Returns:
        bool: True if the section exists, False otherwise.
    """
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        select_sql = f"SELECT EXISTS(SELECT 1 FROM {ONENOTE_PAGES_TABLE} WHERE section_name = %s)"
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

