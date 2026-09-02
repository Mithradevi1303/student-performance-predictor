import sqlite3

def check_database():
    conn = sqlite3.connect('predictions.db')
    conn.row_factory = sqlite3.Row
    
    print("📊 Database Status")
    print("=" * 40)
    
    # Users
    users = conn.execute("SELECT * FROM users").fetchall()
    print(f"\nUsers ({len(users)}):")
    for user in users:
        print(f"  ID: {user['id']}, Username: {user['username']}, Email: {user['email']}")
    
    # Predictions by user
    print("\nPredictions:")
    rows = conn.execute("""
        SELECT 
            u.username,
            COUNT(p.id) as count,
            ROUND(AVG(p.prediction), 1) as avg_score
        FROM users u
        LEFT JOIN predictions p ON u.id = p.user_id
        GROUP BY u.id
    """).fetchall()
    
    for row in rows:
        avg = row['avg_score'] if row['avg_score'] else 0
        print(f"  {row['username']}: {row['count']} predictions, avg score: {avg}")
    
    # Orphaned
    orphaned = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE user_id IS NULL"
    ).fetchone()[0]
    
    if orphaned > 0:
        print(f"\n⚠️ Warning: {orphaned} orphaned predictions found!")
    
    conn.close()

if __name__ == "__main__":
    check_database()