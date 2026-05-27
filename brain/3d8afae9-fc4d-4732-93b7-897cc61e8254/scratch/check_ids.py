import mysql.connector

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '852456',
    'database': 'taskmaster_db'
}

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(id) FROM users")
    max_user_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT MAX(id) FROM projects")
    max_project_id = cursor.fetchone()[0]
    
    print(f"Max User ID: {max_user_id}")
    print(f"Max Project ID: {max_project_id}")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
