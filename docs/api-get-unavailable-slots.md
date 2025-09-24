# Get Unavailable Timeslots API Documentation

## Overview

The Get Unavailable Timeslots API allows clients to retrieve information about time slots that are not available for booking on specific dates. This includes both manually blocked time slots and slots that are already occupied by scheduled appointments.

## Endpoint

```
GET /unavailable-slots
```

## Authentication

This is a public endpoint that does not require authentication for reading unavailable slots.

## Query Parameters

### Option 1: Single Date Query

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | Yes | Date in YYYY-MM-DD format (e.g., "2024-03-15") |
| `checkSlot` | string | No | Specific timeslot to check availability in HH:MM-HH:MM format (e.g., "10:00-11:00") |

### Option 2: Date Range Query

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `startDate` | string | Yes | Start date in YYYY-MM-DD format |
| `endDate` | string | Yes | End date in YYYY-MM-DD format |

### Parameter Validation

- You must provide either a single `date` OR both `startDate` and `endDate`
- You cannot mix single date with date range parameters
- `checkSlot` can only be used with single `date` parameter
- Date format must be YYYY-MM-DD
- Timeslot format must be HH:MM-HH:MM (24-hour format)

## Response Format

All responses return JSON with the following structure:

```json
{
  "success": boolean,
  "statusCode": number,
  "headers": {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,PUT"
  },
  "body": {
    // Response data (see specific examples below)
  }
}
```

## Use Cases and Examples

### 1. Get Unavailable Slots for a Single Date

#### Request
```
GET /unavailable-slots?date=2024-03-15
```

#### Response
```json
{
  "success": true,
  "date": "2024-03-15",
  "unavailableSlots": [
    {
      "timeSlot": "09:00-10:00",
      "reason": "manually_set"
    },
    {
      "timeSlot": "14:00-15:00",
      "reason": "scheduled_appointment",
      "appointmentId": "APPT-123456",
      "status": "CONFIRMED"
    },
    {
      "timeSlot": "16:00-17:00",
      "reason": "pending_appointment",
      "appointmentId": "APPT-789012",
      "status": "PENDING"
    }
  ],
  "manuallyUnavailableSlots": [
    "09:00-10:00",
    "12:00-13:00"
  ],
  "scheduledSlots": [
    {
      "timeSlot": "14:00-15:00",
      "reason": "scheduled_appointment",
      "appointmentId": "APPT-123456",
      "status": "CONFIRMED"
    },
    {
      "timeSlot": "16:00-17:00",
      "reason": "pending_appointment",
      "appointmentId": "APPT-789012",
      "status": "PENDING"
    }
  ]
}
```

### 2. Check Specific Timeslot Availability

#### Request
```
GET /unavailable-slots?date=2024-03-15&checkSlot=10:00-11:00
```

#### Response
```json
{
  "success": true,
  "availabilityCheck": {
    "date": "2024-03-15",
    "requestedSlot": "10:00-11:00",
    "appointmentsCount": 1,
    "blocked": false
  },
  "fullUnavailableSlots": {
    "date": "2024-03-15",
    "unavailableSlots": [
      // ... full unavailable slots data
    ],
    "manuallyUnavailableSlots": [
      // ... manually blocked slots
    ],
    "scheduledSlots": [
      // ... appointment slots
    ]
  }
}
```

### 3. Get Unavailable Slots for Date Range

#### Request
```
GET /unavailable-slots?startDate=2024-03-15&endDate=2024-03-17
```

#### Response
```json
{
  "success": true,
  "dateRange": {
    "startDate": "2024-03-15",
    "endDate": "2024-03-17"
  },
  "unavailableSlotsByDate": {
    "2024-03-15": {
      "date": "2024-03-15",
      "unavailableSlots": [
        // ... slots for March 15
      ],
      "manuallyUnavailableSlots": [
        // ... manually blocked slots for March 15
      ],
      "scheduledSlots": [
        // ... appointment slots for March 15
      ]
    },
    "2024-03-16": {
      "date": "2024-03-16",
      "unavailableSlots": [
        // ... slots for March 16
      ],
      "manuallyUnavailableSlots": [
        // ... manually blocked slots for March 16
      ],
      "scheduledSlots": [
        // ... appointment slots for March 16
      ]
    },
    "2024-03-17": {
      "date": "2024-03-17",
      "unavailableSlots": [
        // ... slots for March 17
      ],
      "manuallyUnavailableSlots": [
        // ... manually blocked slots for March 17
      ],
      "scheduledSlots": [
        // ... appointment slots for March 17
      ]
    }
  }
}
```

## Response Fields

### Unavailable Slot Object

| Field | Type | Description |
|-------|------|-------------|
| `timeSlot` | string | Time slot in HH:MM-HH:MM format |
| `reason` | string | Reason for unavailability: "manually_set", "scheduled_appointment", or "pending_appointment" |
| `appointmentId` | string | (Optional) ID of the appointment occupying this slot |
| `status` | string | (Optional) Status of the appointment: "CONFIRMED", "PENDING", etc. |

### Availability Check Object

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | The requested date |
| `requestedSlot` | string | The timeslot that was checked |
| `appointmentsCount` | number | Number of appointments overlapping with the requested slot |
| `blocked` | boolean | Whether the slot is manually blocked |

## Slot Reasoning

The API categorizes unavailable slots by their source:

### 1. Manually Set Slots
- **Reason**: `manually_set`
- **Source**: Administratively blocked time slots
- **Description**: Time slots that have been manually marked as unavailable by staff

### 2. Scheduled Appointments
- **Reason**: `scheduled_appointment`
- **Source**: Confirmed appointments with scheduled time slots
- **Description**: Time slots occupied by appointments with status other than "CANCELLED" or "COMPLETED"
- **Additional Fields**: `appointmentId`, `status`

### 3. Pending Appointments
- **Reason**: `pending_appointment`
- **Source**: Paid pending appointments with priority 1 selected slots
- **Description**: Time slots reserved by pending appointments that have been paid for
- **Additional Fields**: `appointmentId`, `status`

## Slot Merging Logic

The API automatically merges overlapping or adjacent time slots to provide a consolidated view:

- Overlapping slots are combined into single slots
- Adjacent slots (touching) are merged together
- The response includes both the merged view (`unavailableSlots`) and the raw source data (`manuallyUnavailableSlots`, `scheduledSlots`)

## Error Responses

### 400 Bad Request

**Missing Parameters**
```json
{
  "success": false,
  "message": "Either 'date' or both 'startDate' and 'endDate' parameters are required"
}
```

**Conflicting Parameters**
```json
{
  "success": false,
  "message": "Cannot specify both single 'date' and date range ('startDate'/'endDate'). Use one or the other."
}
```

**Invalid checkSlot Usage**
```json
{
  "success": false,
  "message": "Parameter 'checkSlot' can only be used with single 'date' parameter, not with date ranges"
}
```

**Invalid Date Format**
```json
{
  "success": false,
  "message": "Invalid date format for 'date'. Expected YYYY-MM-DD format."
}
```

**Invalid Timeslot Format**
```json
{
  "success": false,
  "message": "Invalid timeslot format: Invalid time slot format: 25:00-26:00"
}
```

### 500 Internal Server Error

```json
{
  "success": false,
  "message": "Internal server error occurred while processing request"
}
```

## Business Logic

### Appointment Status Filtering

The API only considers appointments with the following statuses as "unavailable":
- **CONFIRMED**: Fully confirmed appointments
- **PENDING**: Pending appointments (only if payment status is "paid" and slot priority is 1)

Excluded statuses:
- **CANCELLED**: Cancelled appointments free up their time slots
- **COMPLETED**: Completed appointments no longer occupy time slots

### Time Zone Handling

All times are processed in the Australia/Perth timezone. The API expects time inputs in local time format (HH:MM) and handles timezone conversion internally.

### Slot Overlap Detection

The API uses sophisticated overlap detection that considers:
- True time overlaps (slots that share any time period)
- Adjacent slots (slots that touch at boundaries)
- Partial overlaps (slots that only partially intersect)

## Rate Limiting

This endpoint does not have explicit rate limiting, but normal AWS API Gateway limits apply.

## Caching

Responses are not cached by default. Consider implementing client-side caching for frequently requested dates, especially when checking availability for date ranges.

## Example Implementation

### JavaScript/TypeScript Client

```typescript
interface UnavailableSlot {
  timeSlot: string;
  reason: 'manually_set' | 'scheduled_appointment' | 'pending_appointment';
  appointmentId?: string;
  status?: string;
}

interface AvailabilityCheck {
  date: string;
  requestedSlot: string;
  appointmentsCount: number;
  blocked: boolean;
}

class UnavailableSlotsAPI {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  async getUnavailableSlots(date: string): Promise<{
    date: string;
    unavailableSlots: UnavailableSlot[];
    manuallyUnavailableSlots: string[];
    scheduledSlots: UnavailableSlot[];
  }> {
    const response = await fetch(`${this.baseUrl}/unavailable-slots?date=${date}`);
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.message);
    }
    
    return data;
  }

  async checkSlotAvailability(date: string, slot: string): Promise<{
    availabilityCheck: AvailabilityCheck;
    fullUnavailableSlots: any;
  }> {
    const response = await fetch(
      `${this.baseUrl}/unavailable-slots?date=${date}&checkSlot=${slot}`
    );
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.message);
    }
    
    return data;
  }

  async getUnavailableSlotsRange(startDate: string, endDate: string): Promise<{
    dateRange: { startDate: string; endDate: string };
    unavailableSlotsByDate: Record<string, any>;
  }> {
    const response = await fetch(
      `${this.baseUrl}/unavailable-slots?startDate=${startDate}&endDate=${endDate}`
    );
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.message);
    }
    
    return data;
  }
}
```

### Python Client

```python
import requests
from typing import List, Dict, Optional
from datetime import datetime

class UnavailableSlotsAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def get_unavailable_slots(self, date: str) -> Dict:
        """Get unavailable slots for a single date."""
        response = requests.get(f"{self.base_url}/unavailable-slots", 
                              params={"date": date})
        response.raise_for_status()
        
        data = response.json()
        if not data.get('success'):
            raise Exception(data.get('message', 'Unknown error'))
        
        return data

    def check_slot_availability(self, date: str, slot: str) -> Dict:
        """Check availability of a specific timeslot."""
        response = requests.get(f"{self.base_url}/unavailable-slots", 
                              params={"date": date, "checkSlot": slot})
        response.raise_for_status()
        
        data = response.json()
        if not data.get('success'):
            raise Exception(data.get('message', 'Unknown error'))
        
        return data

    def get_unavailable_slots_range(self, start_date: str, end_date: str) -> Dict:
        """Get unavailable slots for a date range."""
        response = requests.get(f"{self.base_url}/unavailable-slots", 
                              params={"startDate": start_date, "endDate": end_date})
        response.raise_for_status()
        
        data = response.json()
        if not data.get('success'):
            raise Exception(data.get('message', 'Unknown error'))
        
        return data
```

## Related Endpoints

- **POST /unavailable-slots**: Update unavailable slots (requires admin authentication)
- **GET /appointments**: Get appointment information
- **GET /staff-roles**: Get staff role information

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Current | Initial API implementation with single date, date range, and availability check functionality |

---

*This documentation covers the Get Unavailable Timeslots API as implemented in the Web-Backend system. For questions or support, please contact the development team.*