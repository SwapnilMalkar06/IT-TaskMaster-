import random
from datetime import datetime, timedelta

def generate_sql():
    # 25 Project names
    project_names = [
        "Website Redesign", "Mobile App Development", "Inventory System", "Marketing Campaign",
        "Data Migration", "Security Audit", "API Integration", "Cloud Infrastructure",
        "User Research", "SEO Optimization", "CRM Implementation", "E-commerce Launch",
        "Legacy Code Refactor", "Machine Learning Model", "Social Media Bot", "HR Portal",
        "FinTech Dashboard", "Legal Compliance", "QA Automation", "DevOps Pipeline",
        "Customer Support Tool", "Analytics Dashboard", "Blockchain POC", "IoT Prototype", "AR Filter Design"
    ]
    
    # 23 Employee names (to reach 25 with 21, 22)
    employee_names = [
        "Aarav Sharma", "Aditi Rao", "Arjun Singh", "Ananya Verma", "Ishaan Gupta",
        "Kavya Nair", "Rohan Mehta", "Sia Kapoor", "Vivaan Jha", "Diya Mishra",
        "Kabir Joshi", "Myra Shah", "Aryan Malhotra", "Anvi Desai", "Reyansh Reddy",
        "Zoya Khan", "Aaryan Patil", "Saanvi Choudhary", "Krishna Iyer", "Tara Bose",
        "Shaurya Pandey", "Prisha Saxena", "Advait Kulkarni"
    ]
    
    designations = ["Frontend Developer", "Backend Developer", "UI/UX Designer", "Full Stack Developer", "Data Analyst", "QA Engineer", "DevOps Engineer"]
    
    sql = []
    sql.append("-- TaskMaster Data Seeding Script\n")
    sql.append("USE taskmaster_db;\n")
    
    # 1. Insert Projects
    sql.append("-- 1. Inserting 25 Projects")
    for i, name in enumerate(project_names):
        start_date = datetime(2026, 1, 1) + timedelta(days=random.randint(0, 90))
        deadline = start_date + timedelta(days=random.randint(30, 180))
        status = random.choice(["Active", "Completed", "On Hold"])
        desc = f"Detailed work plan for {name}. Requirements gathering and implementation."
        sql.append(f"INSERT INTO projects (title, description, start_date, deadline, status) VALUES ('{name}', '{desc}', '{start_date.strftime('%Y-%m-%d')}', '{deadline.strftime('%Y-%m-%d')}', '{status}');")
    
    # 2. Insert 23 Employees
    sql.append("\n-- 2. Inserting 23 Employees")
    for i, name in enumerate(employee_names):
        email = name.lower().replace(" ", ".") + "@taskmaster.com"
        pwd = "111"
        desg = random.choice(designations)
        sql.append(f"INSERT INTO users (name, email, password_hash, role, designation) VALUES ('{name}', '{email}', '{pwd}', 'employee', '{desg}');")
    
    # 3. Get Project IDs and User IDs (Assuming they are contiguous for simplicity in the script generation, but I'll use subqueries for robustness in SQL)
    # Actually, it's better to use variables in SQL to find the ranges.
    
    sql.append("\n-- 3. Setting Up IDs for Task Assignment")
    sql.append("SET @first_project_id = (SELECT MIN(id) FROM projects WHERE title = 'Website Redesign');")
    sql.append("SET @first_new_user_id = (SELECT MIN(id) FROM users WHERE email = 'aarav.sharma@taskmaster.com');")
    
    # List of all user IDs we want to assign tasks to: 21, 22, and the new ones.
    # We will generate a list starting from @first_new_user_id to @first_new_user_id + 22.
    
    sql.append("\n-- 4. Inserting 250 Tasks (10 per employee)")
    
    employees_to_assign = [21, 22]
    # We will use a SQL loop or just static inserts for the 250 tasks based on the range.
    # Since writing 250 inserts is better for a static SQL file, I'll generate them in Python.
    
    statuses = ["Completed", "Completed", "Completed", "Completed", "Pending", "Pending", "Pending", "Pending", "In-Progress", "In-Progress"]
    ver_status = ["Verified", "Verified", "Pending Review", "Re-do Required"]
    
    # Target User IDs: 21, 22, and then the next 23.
    # I'll use a loop in Python to generate the SQL statements.
    
    user_ids_code = ["21", "22"]
    for i in range(23):
        user_ids_code.append(f"@first_new_user_id + {i}")
        
    for user_id_sql in user_ids_code:
        # Pick 5 projects from the new 25
        # We assume project IDs are @first_project_id + k
        project_offsets = random.sample(range(25), 5)
        
        random.shuffle(statuses) # Randomize which tasks are completed for this user
        task_idx = 0
        
        for p_offset in project_offsets:
            proj_id_sql = f"@first_project_id + {p_offset}"
            
            # 2 tasks for this project
            for _ in range(2):
                status = statuses[task_idx]
                task_idx += 1
                
                title = f"Task {task_idx} for Project {p_offset + 1}"
                desc = f"Complete the module {task_idx} and verify the integration."
                priority = random.choice(["High", "Medium", "Low"])
                deadline = (datetime.now() + timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d')
                
                v_status = "NULL"
                sub_file = "NULL"
                remarks = "NULL"
                
                if status == "Completed":
                    # Assign a verification status from the list
                    # We need to make sure we use all 2 Verified, 1 Pending, 1 Redo per user
                    # But since we randomized the statuses list, we can just pick from ver_status sequentially for completed tasks
                    comp_tasks_count = sum(1 for i in range(task_idx) if statuses[i] == "Completed")
                    v_status_val = ver_status[(comp_tasks_count - 1) % 4]
                    v_status = f"'{v_status_val}'"
                    sub_file = f"'task_submission_{random.randint(100,999)}.pdf'"
                    remarks = f"'Successfully completed task {task_idx}. All tests passed.'"
                
                sql.append(f"INSERT INTO tasks (project_id, assigned_to_user_id, title, description, priority, deadline, status, verification_status, submission_file, remarks) VALUES "
                           f"({proj_id_sql}, {user_id_sql}, '{title}', '{desc}', '{priority}', '{deadline}', '{status}', {v_status}, {sub_file}, {remarks});")
    
    return "\n".join(sql)

with open(r"d:\TaskMaster\seed_data.sql", "w", encoding='utf-8') as f:
    f.write(generate_sql())
    print("Success: seed_data.sql generated.")
