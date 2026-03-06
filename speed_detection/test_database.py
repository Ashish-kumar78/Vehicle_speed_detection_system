"""
Test script to verify database connection and storage
Run this to ensure everything is working before testing with video
"""

import mysql.connector
from mysql.connector import Error
import sys

def test_database():
    print("="*60)
    print("Testing Database Connection & Tables")
    print("="*60)
    
    try:
        # Connect to database
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="MySQL@ashish",
            database="vehicle_monitoring"
        )
        
        print("\n✅ Database connection successful!")
        
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        print(f"\n📊 Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Check vehicle_records structure
        print("\n📋 Checking vehicle_records table structure...")
        cursor.execute("DESCRIBE vehicle_records")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]} - {col[1]}")
        
        # Check e_challans structure
        print("\n📋 Checking e_challans table structure...")
        cursor.execute("DESCRIBE e_challans")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]} - {col[1]}")
        
        # Test inserting a record
        print("\n🧪 Testing record insertion...")
        try:
            cursor.execute("""
                INSERT INTO vehicle_records 
                (vehicle_number, vehicle_type, speed_kmh, status, timestamp, violation_count, distance_m, tracking_id, location)
                VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s)
            """, ("TEST123", "car", 75.5, "normal", 1, 10.0, 999, "Test Location"))
            
            conn.commit()
            print("✅ Test record inserted successfully!")
            
            # Verify it was saved
            cursor.execute("SELECT * FROM vehicle_records WHERE vehicle_number='TEST123'")
            result = cursor.fetchone()
            if result:
                print(f"✅ Record verified in database: {result}")
                
                # Clean up test record
                cursor.execute("DELETE FROM vehicle_records WHERE vehicle_number='TEST123'")
                conn.commit()
                print("🗑️ Test record cleaned up")
            else:
                print("❌ Could not verify test record")
                
        except Exception as e:
            print(f"❌ Error during test insertion: {e}")
            return False
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED! Database is ready.")
        print("="*60)
        return True
        
    except Error as e:
        print(f"\n❌ Database error: {e}")
        print("\nPossible issues:")
        print("1. MySQL server is not running")
        print("2. Database 'vehicle_monitoring' doesn't exist")
        print("3. Wrong username/password")
        print("4. Tables haven't been created yet")
        print("\nSolution: Import database.sql into MySQL first!")
        return False

if __name__ == "__main__":
    success = test_database()
    sys.exit(0 if success else 1)
