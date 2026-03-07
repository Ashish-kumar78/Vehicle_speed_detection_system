-- Fix existing inconsistency in database
-- This updates vehicle_records to mark challans that were generated

USE vehicle_monitoring;

-- Update all vehicles that have challans in e_challans table
UPDATE vehicle_records v
INNER JOIN e_challans e ON v.vehicle_number = e.vehicle_number
SET v.challan_generated = TRUE, 
    v.challan_amount = e.fine_amount
WHERE v.challan_generated = FALSE OR v.challan_generated IS NULL;

-- Verify the fix
SELECT 
    v.vehicle_number,
    v.challan_generated,
    v.challan_amount,
    e.challan_number,
    e.fine_amount
FROM vehicle_records v
INNER JOIN e_challans e ON v.vehicle_number = e.vehicle_number
ORDER BY v.timestamp DESC;
