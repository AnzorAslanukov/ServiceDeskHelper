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
            - page_datetime (str): ISO datetime string, optional
            - workbook_name (str): Required
            - section_name (str): Required
            - embedding (list): List of 1024 floats, optional
    
    Returns:
        int: ID of the inserted record, or None if failed
    """
    connection = None
    cursor = None
    
    try:
        # Validate required fields
        required_fields = ['page_title', 'page_body_text', 'workbook_name', 'section_name']
        missing_fields = [field for field in required_fields if not page_data.get(field)]
        
        if missing_fields:
            write_debug("Missing required fields", {"missing": missing_fields, "data": page_data})
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        # Get database connection
        connection = get_database_connection()
        cursor = connection.cursor()
        
        # Prepare the SQL insert statement
        insert_sql = f"""
            INSERT INTO {ONENOTE_PAGES_TABLE} 
            (page_title, page_body_text, page_datetime, workbook_name, section_name, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        # Prepare values
        page_datetime = None
        if page_data.get('page_datetime'):
            try:
                # Convert datetime string to timestamp
                page_datetime = datetime.fromisoformat(page_data['page_datetime'].replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                write_debug("Invalid datetime format", {"datetime": page_data.get('page_datetime'), "error": str(e)})
                # Continue with None if datetime parsing fails
        
        # Handle embedding vector
        embedding = page_data.get('embedding')
        if embedding and isinstance(embedding, list):
            # Convert list to PostgreSQL array format for pgvector
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        else:
            embedding_str = None
        
        values = (
            page_data['page_title'],
            page_data['page_body_text'],
            page_datetime,
            page_data['workbook_name'],
            page_data['section_name'],
            embedding_str
        )
        
        # Execute the insert
        cursor.execute(insert_sql, values)
        
        # Get the inserted record ID
        inserted_id = cursor.fetchone()[0]
        
        # Commit the transaction
        connection.commit()
        
        write_debug("Successfully inserted page", {
            "id": inserted_id,
            "title": page_data['page_title'],
            "workbook": page_data['workbook_name'],
            "section": page_data['section_name']
        })
        
        return inserted_id
        
    except psycopg2.Error as e:
        if connection:
            connection.rollback()
        write_debug("Database insert error", str(e))
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
