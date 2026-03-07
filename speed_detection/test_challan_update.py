"""
Test script to verify challan generation updates vehicle_records table
"""
import mysql.connector
from mysql.connector import Error

# Connect to database
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="MySQL@ashish",
        database="vehicle_monitoring"
    )
    
    cursor = conn.cursor(dictionary=True)
    
    print("=" * 60)
    print("Testing Challan Generation Database Update")
    print("=" * 60)
    
    # Check if tables exist
    cursor.execute("SHOW TABLES LIKE 'vehicle_records'")
    if not cursor.fetchone():
        print("❌ vehicle_records table does not exist!")
        exit(1)
    
    cursor.execute("SHOW TABLES LIKE 'e_challans'")
    if not cursor.fetchone():
        print("❌ e_challans table does not exist!")
        exit(1)
    
    print("✅ Both tables exist\n")
    
    # Check if vehicle_records has challan columns
    cursor.execute("SHOW COLUMNS FROM vehicle_records")
    columns = [col['Field'] for col in cursor.fetchall()]
    
    required_columns = ['challan_generated', 'challan_amount']
    missing_columns = [col for col in required_columns if col not in columns]
    
    if missing_columns:
        print(f"❌ Missing columns in vehicle_records: {missing_columns}")
        print("\nRun this SQL to add them:")
        for col in missing_columns:
            if col == 'challan_generated':
                print("ALTER TABLE vehicle_records ADD COLUMN challan_generated BOOLEAN DEFAULT FALSE;")
            elif col == 'challan_amount':
                print("ALTER TABLE vehicle_records ADD COLUMN challan_amount FLOAT DEFAULT 0.0;")
        exit(1)
    
    print("✅ Required columns exist in vehicle_records\n")
    
    # Get recent records
    cursor.execute("""
        SELECT vehicle_number, vehicle_type, status, violation_count, 
               challan_generated, challan_amount, timestamp
        FROM vehicle_records
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    
    records = cursor.fetchall()
    
    print("=" * 60)
    print("Recent Vehicle Records")
    print("=" * 60)
    
    if not records:
        print("⚠️ No records in database yet")
    else:
        for record in records:
            print(f"\nVehicle: {record['vehicle_number']}")
            print(f"  Type: {record['vehicle_type']}")
            print(f"  Status: {record['status']}")
            print(f"  Violations: {record['violation_count']}")
            print(f"  Challan Generated: {'✅ YES' if record['challan_generated'] else '❌ NO'}")
            print(f"  Challan Amount: ₹{record['challan_amount']:.2f}" if record['challan_amount'] > 0 else "  Challan Amount: ₹0.00")
            print(f"  Timestamp: {record['timestamp']}")
    
    # Cross-check with e_challans table
    print("\n" + "=" * 60)
    print("E-Challans Table")
    print("=" * 60)
    
    cursor.execute("""
        SELECT challan_number, vehicle_number, vehicle_type, 
               speed_detected, fine_amount, violation_date
        FROM e_challans
        ORDER BY violation_date DESC
        LIMIT 5
    """)
    
    challans = cursor.fetchall()
    
    if not challans:
        print("⚠️ No e-challans in database yet")
    else:
        for challan in challans:
            print(f"\nChallan: {challan['challan_number']}")
            print(f"  Vehicle: {challan['vehicle_number']}")
            print(f"  Type: {challan['vehicle_type']}")
            print(f"  Speed: {challan['speed_detected']} km/h")
            print(f"  Fine: ₹{challan['fine_amount']:.2f}")
            print(f"  Date: {challan['violation_date']}")
    
    # Verify consistency
    print("\n" + "=" * 60)
    print("Consistency Check")
    print("=" * 60)
    
    # Find vehicles with challans in e_challans but not marked in vehicle_records
    cursor.execute("""
        SELECT DISTINCT e.vehicle_number
        FROM e_challans e
        LEFT JOIN vehicle_records v ON e.vehicle_number = v.vehicle_number
        WHERE v.challan_generated = FALSE OR v.challan_generated IS NULL
    """)
    
    inconsistencies = cursor.fetchall()
    
    if inconsistencies:
        print(f"\n⚠️ Found {len(inconsistencies)} inconsistency(ies):")
        print("Vehicles have challans in e_challans table but not marked in vehicle_records:")
        for inc in inconsistencies:
            print(f"  - {inc['vehicle_number']}")
        print("\nThis indicates the database update is NOT working properly!")
    else:
        print("\n✅ Database is consistent!")
        print("All challans in e_challans are properly marked in vehicle_records")
    
    print("\n" + "=" * 60)
    
    conn.close()
    
except Error as e:
    print(f"❌ Database error: {e}")
