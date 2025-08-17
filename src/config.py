import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database Configuration
DATABASE_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'servicedeskhelper'),
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD')
}

# Database Table Names
ONENOTE_CHUNKS_TABLE = 'onenote_chunks'

# Database Connection String
DATAauth_url = os.getenv('DATAauth_url')

# Databricks Configuration
DATABRICKS_CONFIG = {
    'embedding_url': os.getenv('DATABRICKS_EMBEDDING_URL'),
    'text_generation_url': os.getenv('DATABRICKS_TEXT_GENERATION_URL'),
    'api_key': os.getenv('DATABRICKS_API_KEY')
}

# Vector Database Configuration
VECTOR_CONFIG = {
    'dimension': int(os.getenv('VECTOR_DIMENSION', 1024))
}

# File Processing Configuration
FILE_PATHS = {
    'onenote_data_dir': os.getenv('ONENOTE_DATA_DIR', './data/onenote/workbooks'),
    'debug_file_path': os.getenv('DEBUG_FILE_PATH', './debug.txt')
}

# Application Configuration
APP_CONFIG = {
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'debug': os.getenv('DEBUG', 'false').lower() == 'true'
}

# Athena Configuration
ATHENA_CONFIG = {
    'auth_url': os.getenv('ATHENA_AUTH_URL'),
    'base_url': os.getenv('ATHENA_BASE_URL'),
    'client_id': os.getenv('ATHENA_CLIENT_ID'), # Renamed from API_KEY
    'username': os.getenv('ATHENA_USERNAME'),
    'password': os.getenv('ATHENA_PASSWORD'),
    'json_template': os.getenv('ATHENA_JSON_TEMPLATE')
}

# PostgreSQL database athena_tickets column key to API JSON key mapping
# Key1 = column name from table athena_tickets 
# Key2 = JSON response object key
ATHENA_TICKETS_FIELD_MAPPING = {
    "entity_id":"entityId",
    "ticket_id":"id",
    "title":"title",
    "description":"description",
    "escalated":"escalated",
    "resolution_description":"",
    "message":"resolutionDescription",
    "priority":"priority",
    "location_name":"location.name",
    "floor_name":"floor.name",
    "affect_patient_care":"affect_Patient_Care",
    "confirmed_resolution":"confrimed_Resolution.name",
    "tier_queue_name":"tierQueue.name",
    "created_date":"createdDate",
    "last_modified":"lastModified",
    "affected_user_domain":"affectedUser.domain",
    "affected_user_company":"affectedUser.company",
    "affected_user_department":"affectedUser.department",
    "affected_user_title":"affectedUser.title",
    "assigned_to_user_domain":"assignedToUser.domain",
    "assigned_to_user_company":"assignedToUser.company",
    "assigned_to_user_department":"assignedToUser.department",
    "assigned_to_user_title":"assignedToUser.title",
    "resolved_by_user_domain":"resolvedByUser.domain",
    "resolved_by_user_company":"resolvedByUser.company",
    "resolved_by_user_department":"resolvedByUser.department",
    "resolved_by_user_title":"resolvedByUser.title",
    "analyst_comments":"analystComments"
}

# Validation
def validate_config():
    """Validate that required environment variables are set and test Databricks endpoints"""
    print("🔍 Validating configuration...")
    
    # Check required environment variables
    required_vars = [
        'POSTGRES_USER',
        'POSTGRES_PASSWORD', 
        'DATABRICKS_EMBEDDING_URL',
        'DATABRICKS_TEXT_GENERATION_URL',
        'DATABRICKS_API_KEY',
        'ATHENA_AUTH_URL',
        'ATHENA_BASE_URL',
        'ATHENA_CLIENT_ID', # Renamed from API_KEY
        'ATHENA_USERNAME',
        'ATHENA_PASSWORD',
        'ATHENA_JSON_TEMPLATE'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise ValueError(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
    
    print("✅ All required environment variables are set")
    
    # Test Databricks endpoints with direct HTTP requests
    headers = {
        'Authorization': f'Bearer {DATABRICKS_CONFIG["api_key"]}',
        'Content-Type': 'application/json'
    }
    
    # Test embedding endpoint
    print("\n🧪 Testing Databricks embedding endpoint...")
    embedding_payload = {
        "input": "This is a test sentence for embedding."
    }
    
    try:
        response = requests.post(
            DATABRICKS_CONFIG['embedding_url'],
            headers=headers,
            json=embedding_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'data' in result and len(result['data']) > 0:
                embedding_dim = len(result['data'][0]['embedding'])
                print(f"✅ Embedding endpoint working! Vector dimension: {embedding_dim}")
            else:
                print(f"⚠️  Embedding endpoint responded but unexpected format: {result}")
        else:
            print(f"❌ Embedding endpoint failed: {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Embedding endpoint connection error: {str(e)}")
    
    # Test text generation endpoint
    print("\n🧪 Testing Databricks text generation endpoint...")
    text_gen_payload = {
        "messages": [
            {
                "role": "user",
                "content": "Say hello in one sentence."
            }
        ],
        "max_tokens": 50
    }
    
    try:
        response = requests.post(
            DATABRICKS_CONFIG['text_generation_url'],
            headers=headers,
            json=text_gen_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                generated_text = result['choices'][0]['message']['content']
                print(f"✅ Text generation endpoint working! Sample output: {generated_text}")
            else:
                print(f"⚠️  Text generation endpoint responded but unexpected format: {result}")
        else:
            print(f"❌ Text generation endpoint failed: {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Text generation endpoint connection error: {str(e)}")
    
    print("\n🎉 Configuration validation complete!")
    return True

# Debug logging function
def write_debug(message, data=None, append=False):
    """
    Write debug information to debug.txt file.
    
    Args:
        message (str): Debug message to write
        data (any, optional): Additional data to write (will be converted to string)
        append (bool, optional): If True, appends to the file. If False, clears the file before writing. Defaults to False.
    """
    debug_file_path = FILE_PATHS['debug_file_path']
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        mode = 'a' if append else 'w'
        with open(debug_file_path, mode, encoding='utf-8') as f:
            if not append:
                f.write(f"[{timestamp}] DEBUG LOG\n")
                f.write("=" * 50 + "\n\n")
            else:
                f.write(f"\n\n[{timestamp}] APPENDED LOG\n")
                f.write("=" * 50 + "\n\n")

            f.write(f"Message:\n\n{message}\n\n")
            
            if data is not None:
                f.write("Data:\n")
                f.write("-" * 20 + "\n")
                
                # Handle different data types
                if isinstance(data, (dict, list)):
                    f.write(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    f.write(str(data))
                
                f.write("\n\n")
            
            f.write("=" * 50 + "\n")
            f.write(f"End of debug log [{timestamp}]\n")
            
        print(f"📝 Debug written to: {debug_file_path}")
        
    except Exception as e:
        print(f"❌ Error writing to debug file: {str(e)}")
