import mysql.connector

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '852456',
    'database': 'taskmaster_db'
}

def execute_sql_file(filename):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        with open(filename, 'r', encoding='utf-8') as f:
            file_content = f.read()
            
        print(f"Executing {filename}...")
        
        # Split statements by semicolon, but be careful with comments and formatting
        # multi=True is a better way to handle multiple statements in one go
        results = cursor.execute(file_content, multi=True)
        
        count = 0
        for result in results:
            if result.with_rows:
                result.fetchall()
            count += 1
            
        conn.commit()
        print(f"Successfully executed {count} statements.")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    execute_sql_file(r"d:\TaskMaster\seed_data.sql")
