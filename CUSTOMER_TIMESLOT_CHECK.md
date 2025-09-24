# Updated Unavailable Slots API - Customer Timeslot Availability Check

## Overview
The `/unavailable-slots` GET endpoint has been enhanced to allow customer users to check if a specific timeslot is available on a given date, while preserving all existing functionalities.

## New Feature: Customer Timeslot Availability Check

### New Parameter
- **`checkSlot`** (optional): Timeslot to check for availability in format "HH:MM-HH:MM" (e.g., "09:00-10:30")

### New Response Format
When the `checkSlot` parameter is provided along with a `date` parameter, the API will:
1. Validate the timeslot format
2. Count appointments that overlap with the requested timeslot
3. Check if the timeslot is manually blocked
4. Return detailed availability metrics

### Response Attributes
- **`appointmentsCount`**: Number of appointments that overlap with the requested timeslot, including:
  - Scheduled appointments (confirmed, not cancelled/completed) with overlapping scheduled time
  - Pending paid appointments with overlapping priority 1 slots
- **`blocked`**: Boolean indicating if the requested timeslot overlaps with any manually blocked timeslot

### Example Requests

#### Check if 09:00-10:30 is available on 2024-01-15
```
GET /unavailable-slots?date=2024-01-15&checkSlot=09:00-10:30
```

#### Response when slot is available
```json
{
  "availabilityCheck": {
    "date": "2024-01-15",
    "requestedSlot": "09:00-10:30",
    "appointmentsCount": 0,
    "blocked": false
  },
  "fullUnavailableSlots": {
    "date": "2024-01-15",
    "unavailableSlots": [...],
    "manuallyUnavailableSlots": [...],
    "scheduledSlots": [...]
  }
}
```

#### Response when slot has conflicts
```json
{
  "availabilityCheck": {
    "date": "2024-01-15",
    "requestedSlot": "09:00-10:30",
    "appointmentsCount": 2,
    "blocked": true
  },
  "fullUnavailableSlots": {
    "date": "2024-01-15",
    "unavailableSlots": [...],
    "manuallyUnavailableSlots": [...],
    "scheduledSlots": [...]
  }
}
```

## Existing Functionality (Unchanged)

### 1. Get unavailable slots for single date
```
GET /unavailable-slots?date=2024-01-15
```

### 2. Get unavailable slots for date range
```
GET /unavailable-slots?startDate=2024-01-15&endDate=2024-01-17
```

## Implementation Details

### Availability Logic
The system uses the same logic as the existing appointment system to determine unavailability:

1. **Manual Unavailable Slots**: Slots manually marked as unavailable by staff (affects `blocked`)
2. **Scheduled Appointment Slots**: 
   - Confirmed appointments (status != 'CANCELLED' and != 'COMPLETED') with scheduled time overlapping (affects `appointmentsCount`)
   - Pending appointments with paid status and priority 1 slots overlapping (affects `appointmentsCount`)

### Conflict Detection
- Uses existing `time_slots_overlap()` function to detect conflicts
- Considers adjacent timeslots as overlapping (to prevent double-booking)
- Returns detailed metrics: appointment count and manual blocking status

### Validation
- Validates timeslot format (HH:MM-HH:MM)
- Validates date format (YYYY-MM-DD)
- Ensures `checkSlot` is only used with single date (not date ranges)

## Error Responses

### Invalid timeslot format
```json
{
  "error": "Invalid timeslot format: Invalid time slot format: invalid-format",
  "statusCode": 400
}
```

### Using checkSlot with date range
```json
{
  "error": "Parameter 'checkSlot' can only be used with single 'date' parameter, not with date ranges",
  "statusCode": 400
}
```

## Benefits for Customers

1. **Real-time Availability**: Customers can check availability before starting appointment booking
2. **Detailed Metrics**: Know how many appointments conflict and if the slot is manually blocked
3. **Same Logic**: Uses identical availability logic as the appointment booking system
4. **No Authentication Required**: Customers can check availability without logging in

## Backward Compatibility

- All existing API functionality remains unchanged
- Existing parameters work exactly as before
- New parameter is optional - no impact on current users
- Response format for existing functionality is identical