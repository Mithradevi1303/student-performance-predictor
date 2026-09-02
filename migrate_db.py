import sqlite3
import os
import sys
import shutil
from datetime import datetime, timezone

DB_PATH = "predictions_new.db"

def get_db_connection():
    """Get a database connection with row factory for named columns"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def table_exists(cursor, table_name):
    """Check if a table exists in the database"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None

def column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def backup_database():
    """Create a backup of the database before migration"""
    if os.path.exists(DB_PATH):
        backup_path = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return backup_path
    return None

def create_users_table(cursor):
    """Create the users table if it doesn't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    print("✅ Users table ready")

def update_predictions_table(cursor):
    """Add user_id column to predictions table if it doesn't exist"""
    if not column_exists(cursor, 'predictions', 'user_id'):
        cursor.execute(
            "ALTER TABLE predictions ADD COLUMN user_id INTEGER REFERENCES users(id)"
        )
        print("✅ Added user_id column to predictions table")
    else:
        print("ℹ️ user_id column already exists in predictions table")

def create_indices(cursor):
    """Create indices for better query performance"""
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_predictions_user_id ON predictions(user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
    )
    print("✅ Indices created")

def create_admin_user(cursor):
    """Create admin user if no users exist"""
    # Check if any users exist
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    if user_count > 0:
        print(f"ℹ️ Users already exist ({user_count} users). Skipping admin creation.")
        return None
    
    # Create default admin user
    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        ('admin', 'admin@example.com', 'migrated_default_user_please_change', 
         datetime.now(timezone.utc).isoformat(timespec='seconds'))
    )
    
    admin_id = cursor.lastrowid
    print(f"✅ Created default admin user (ID: {admin_id})")
    print("   ⚠️  Note: This account is for data migration only.")
    print("   ℹ️  Please register a real account after migration.")
    return admin_id

def assign_existing_predictions(cursor, admin_id):
    """Assign existing predictions to admin user"""
    cursor.execute(
        "SELECT COUNT(*) FROM predictions WHERE user_id IS NULL"
    )
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("ℹ️ No existing predictions to assign.")
        return 0
    
    cursor.execute(
        "UPDATE predictions SET user_id = ? WHERE user_id IS NULL",
        (admin_id,)
    )
    print(f"✅ Assigned {count} existing predictions to admin user")
    return count

def clean_up_admin_user(cursor, target_username):
    """
    Assign predictions from admin to a specific user, then delete the admin user
    """
    # Get target user
    cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (target_username,)
    )
    target = cursor.fetchone()
    
    if not target:
        print(f"⚠️ Target user '{target_username}' not found. Skipping cleanup.")
        return
    
    # Get admin user
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    admin = cursor.fetchone()
    
    if not admin:
        return
    
    # Move predictions from admin to target
    cursor.execute(
        "UPDATE predictions SET user_id = ? WHERE user_id = ?",
        (target[0], admin[0])
    )
    
    # Delete admin user
    cursor.execute("DELETE FROM users WHERE username = 'admin'")
    
    print(f"✅ Moved predictions from admin to '{target_username}' and removed admin user")

def print_database_stats(cursor):
    """Print useful statistics about the database"""
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM predictions")
    pred_count = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT COUNT(*) FROM predictions WHERE user_id IS NULL"
    )
    orphaned = cursor.fetchone()[0]
    
    print("\n📊 Database Statistics:")
    print(f"   Total users: {user_count}")
    print(f"   Total predictions: {pred_count}")
    print(f"   Orphaned predictions (no user): {orphaned}")

def main():
    """Main migration function"""
    print("🔄 Starting database migration...")
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print("❌ Database file not found. Run the app first to create it.")
        return
    
    # Backup database
    backup_path = backup_database()
    
    # Connect to database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Create users table
        create_users_table(cursor)
        
        # 2. Update predictions table
        update_predictions_table(cursor)
        
        # 3. Create indices
        create_indices(cursor)
        
        # 4. Create admin user if needed
        admin_id = create_admin_user(cursor)
        
        # 5. Assign existing predictions
        if admin_id:
            assign_existing_predictions(cursor, admin_id)
        
        # 6. Print statistics
        print_database_stats(cursor)
        
        # Commit all changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Optional: Ask about cleanup
        if admin_id:
            print("\n💡 Tip: You can now:")
            print("   1. Register a real user account")
            print("   2. Then run this script again with a username to migrate data")
            print("   Example: python migrate_db.py your_username")
        
        # Check if we should clean up admin
        if len(sys.argv) > 1:
            target_user = sys.argv[1]
            clean_up_admin_user(cursor, target_user)
            conn.commit()
            print(f"✅ Cleanup completed. Data migrated to '{target_user}'")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if backup_path:
            print(f"   Restore backup from: {backup_path}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()