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

def insert_onenote_page(page_data):
    """
    Insert a single OneNote page record into the database.
    
    Args:
        page_data (dict): Dictionary containing page data with keys:
            - page_title (str): Required
            - page_body_text (str): Required
            - is_summary (bool): Required
            - page_datetime (str): ISO datetime string, optional
            - workbook_name (str): Required
            - section_name (str): Required
            - embedding (list): List of 1024 floats, optional
    
    Returns:
        int: ID of the inserted/updated record, or None if failed or skipped.
    """
    connection = None
    cursor = None
    
    try:
        # Validate required fields
        required_fields = ['page_title', 'page_body_text', 'is_summary', 'workbook_name', 'section_name']
        missing_fields = [field for field in required_fields if page_data.get(field) is None] # Check for None explicitly for boolean
        
        if missing_fields:
            write_debug("Missing required fields", {"missing": missing_fields, "data": page_data})
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        # Get database connection
        connection = get_database_connection()
        cursor = connection.cursor()
        
        # Check for existing record
        select_sql = f"""
            SELECT id FROM {ONENOTE_PAGES_TABLE}
            WHERE page_title = %s AND workbook_name = %s AND section_name = %s
        """
        cursor.execute(select_sql, (page_data['page_title'], page_data['workbook_name'], page_data['section_name']))
        existing_record = cursor.fetchone()
        
        page_id = None
        
        # Prepare values for insert/update
        page_datetime = None
        if page_data.get('page_datetime'):
            try:
                page_datetime = datetime.fromisoformat(page_data['page_datetime'].replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                write_debug("Invalid datetime format", {"datetime": page_data.get('page_datetime'), "error": str(e)})
        
        embedding = page_data.get('embedding')
        if embedding and isinstance(embedding, list):
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        else:
            embedding_str = None
        
        values = (
            page_data['page_title'],
            page_data['page_body_text'],
            page_data['is_summary'],
            page_datetime,
            page_data['workbook_name'],
            page_data['section_name'],
            embedding_str
        )

        if existing_record:
            page_id = existing_record[0]
            if page_data.get('override_on_duplicate', True): # Default to True
                update_sql = f"""
                    UPDATE {ONENOTE_PAGES_TABLE}
                    SET page_body_text = %s, is_summary = %s, page_datetime = %s, embedding = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                update_values = (
                    page_data['page_body_text'],
                    page_data['is_summary'],
                    page_datetime,
                    embedding_str,
                    page_id
                )
                cursor.execute(update_sql, update_values)
                write_debug("Successfully updated page (override)", {
                    "id": page_id,
                    "title": page_data['page_title'],
                    "workbook": page_data['workbook_name'],
                    "section": page_data['section_name']
                })
            else:
                write_debug("Skipping page insertion (duplicate found, override_on_duplicate is False)", {
                    "id": page_id,
                    "title": page_data['page_title'],
                    "workbook": page_data['workbook_name'],
                    "section": page_data['section_name']
                })
        else:
            insert_sql = f"""
                INSERT INTO {ONENOTE_PAGES_TABLE} 
                (page_title, page_body_text, is_summary, page_datetime, workbook_name, section_name, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            cursor.execute(insert_sql, values)
            page_id = cursor.fetchone()[0]
            write_debug("Successfully inserted new page", {
                "id": page_id,
                "title": page_data['page_title'],
                "workbook": page_data['workbook_name'],
                "section": page_data['section_name']
            })
        
        connection.commit()
        return page_id
        
    except psycopg2.Error as e:
        if connection:
            connection.rollback()
        write_debug("Database operation error in insert_onenote_page", str(e))
        raise
    except Exception as e:
        if connection:
            connection.rollback()
        write_debug("Unexpected error in insert_onenote_page", str(e))
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

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

def onenote_page_exists(page_title):
    """
    Checks if a OneNote page (page_title) exists in the onenote_pages table.
    
    Args:
        page_title (str): The title of the OneNote page.
        
    Returns:
        bool: True if the page exists, False otherwise.
    """
    connection = None
    cursor = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        select_sql = f"SELECT EXISTS(SELECT 1 FROM {ONENOTE_PAGES_TABLE} WHERE page_title = %s)"
        cursor.execute(select_sql, (page_title,))
        exists = cursor.fetchone()[0]
        write_debug(f"Page '{page_title}' exists: {exists}", append=True)
        return exists
    except Exception as e:
        write_debug(f"Error checking if page '{page_title}' exists: {str(e)}", append=True)
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def add_test_data_to_onenote_pages(num_records=1):
    """
    Adds test data to the onenote_pages table.
    
    Args:
        num_records (int): Number of test records to add.
        
    Returns:
        list: A list of IDs of the inserted test records.
    """
    inserted_ids = []
    for i in range(num_records):
        timestamp = datetime.now().isoformat()
        test_page_data = {
            'page_title': f'TEST_DATA_Page Title {timestamp}_{i}',
            'page_body_text': f'This is test body text for page {i} created at {timestamp}. It contains various details for testing purposes.',
            'page_datetime': timestamp,
            'workbook_name': f'TEST_DATA_Workbook {i % 2}', # Alternate between two workbooks
            'section_name': f'Test Section {i % 3}', # Alternate between three sections
            'embedding': [float(j % 100) / 100.0 for j in range(1024)] # Dummy embedding
        }
        try:
            inserted_id = insert_onenote_page(test_page_data)
            if inserted_id:
                inserted_ids.append(inserted_id)
                write_debug(f"Added test record {i+1}/{num_records}", {"id": inserted_id, "title": test_page_data['page_title']}, append=True)
        except Exception as e:
            write_debug(f"Failed to add test record {i+1}/{num_records}", str(e), append=True)
    return inserted_ids

def delete_test_data_from_onenote_pages():
    """
    Deletes all test data from the onenote_pages table.
    Test data is identified by 'TEST_DATA_' prefix in page_title or workbook_name.
    
    Returns:
        int: Number of records deleted.
    """
    connection = None
    cursor = None
    deleted_count = 0
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        
        delete_sql = f"""
            DELETE FROM {ONENOTE_PAGES_TABLE}
            WHERE page_title LIKE 'TEST_DATA_%%' OR workbook_name LIKE 'TEST_DATA_%%';
        """
        
        cursor.execute(delete_sql)
        deleted_count = cursor.rowcount
        connection.commit()
        
        write_debug(f"Deleted {deleted_count} test records from {ONENOTE_PAGES_TABLE}", append=True)
        
    except psycopg2.Error as e:
        if connection:
            connection.rollback()
        write_debug("Database delete error for test data", str(e), append=True)
        raise
    except Exception as e:
        if connection:
            connection.rollback()
        write_debug("Unexpected error in delete_test_data_from_onenote_pages", str(e), append=True)
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    return deleted_count

def test_database_connection():
    """
    Test database connection and table existence.
    
    Returns:
        bool: True if connection and table exist, False otherwise
    """
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        
        # Test if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (ONENOTE_PAGES_TABLE,))
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            # Get table info
            cursor.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (ONENOTE_PAGES_TABLE,))
            
            columns = cursor.fetchall()
            
            write_debug("Database connection test successful", {
                "table_exists": True,
                "table_name": ONENOTE_PAGES_TABLE,
                "columns": columns
            })
            
            cursor.close()
            connection.close()
            return True
        else:
            write_debug("Database table does not exist", {"table_name": ONENOTE_PAGES_TABLE})
            cursor.close()
            connection.close()
            return False
            
    except Exception as e:
        write_debug("Database connection test failed", str(e))
        return False

'''
# Test code - runs when script is executed directly
if __name__ == "__main__":
    print("🔍 Testing database connection...")
    
    try:
        if test_database_connection():
            print("✅ Database connection test passed!")
        else:
            print("❌ Database connection test failed!")
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
'''