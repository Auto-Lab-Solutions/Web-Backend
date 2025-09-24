# Auto Lab Solutions - Database Tables Documentation

This document provides a comprehensive overview of all DynamoDB tables used in the Auto Lab Solutions system, their structures, fields, valid values, and important implementation details.

## Table Overview

The system uses 14 main DynamoDB tables plus 2 additional tables for email management:

### Core Business Tables
1. [Staff](#1-staff-table)
2. [Users](#2-users-table)
3. [Connections](#3-connections-table)
4. [Messages](#4-messages-table)
5. [UnavailableSlots](#5-unavailableslots-table)
6. [Appointments](#6-appointments-table)
7. [ServicePrices](#7-serviceprices-table)
8. [Orders](#8-orders-table)
9. [ItemPrices](#9-itemprices-table)
10. [Inquiries](#10-inquiries-table)
11. [Payments](#11-payments-table)
12. [Invoices](#12-invoices-table)

### Email Management Tables
13. [EmailSuppression](#13-emailsuppression-table)
14. [EmailAnalytics](#14-emailanalytics-table)
15. [EmailMetadata](#15-emailmetadata-table)

---

## 1. Staff Table

**Purpose**: Manages staff members, their roles, and permissions within the system.

### Table Structure
- **Table Name**: `Staff-{Environment}`
- **Primary Key**: `userEmail` (String, HASH)
- **Global Secondary Indexes**:
  - `userId-index`: `userId` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `userEmail` | String | Yes | Staff member's email address (Primary Key) | Valid email format |
| `userId` | String | Yes | Unique user identifier | UUID format |
| `userName` | String | Yes | Display name of the staff member | Any string |
| `contactNumber` | String | Yes | Phone number | Phone number format |
| `roles` | List | Yes | List of assigned roles | ADMIN, MECHANIC, CUSTOMER_SUPPORT, CLERK |

### Sample Data
```json
{
  "userEmail": "janithadharmasuriya@gmail.com",
  "userId": "c712121f-c47f-47cb-a115-7e3ce1cf3877",
  "userName": "Jani",
  "contactNumber": "0451237048",
  "roles": ["ADMIN", "MECHANIC", "CUSTOMER_SUPPORT"]
}
```

### Important Notes
- Staff can have multiple roles
- Email addresses are used as primary identifiers
- Role-based permissions are enforced throughout the system
- Stream enabled for real-time updates

---

## 2. Users Table

**Purpose**: Stores customer user information and session data.

### Table Structure
- **Table Name**: `Users-{Environment}`
- **Primary Key**: `userId` (String, HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `userId` | String | Yes | Unique user identifier (Primary Key) | UUID format |
| `userEmail` | String | No | User's email address | Valid email format |
| `contactNumber` | String | No | User's phone number | Valid phone number format |
| `userName` | String | No | Display name | Any string |
| `userDevice` | String | No | Device information | Any string |
| `userLocation` | String | No | Location information | Any string |
| `assignedTo` | String | No | Assigned staff member's userId | Staff userId |
| `lastSeen` | Number | No | Last activity timestamp | Unix timestamp |

### Sample Data
```json
{
  "userId": "user-uuid-123",
  "userEmail": "customer@example.com",
  "contactNumber": "+61412345678",
  "userName": "John Doe",
  "userDevice": "iPhone 14",
  "userLocation": "Sydney, Australia",
  "assignedTo": "staff-uuid-456",
  "lastSeen": 1693478400
}
```

### Important Notes
- Not all users may have complete profile information
- `assignedTo` links users to specific staff members
- Stream enabled for real-time updates
- Used for WebSocket connection management

---

## 3. Connections Table

**Purpose**: Manages WebSocket connections for real-time communication.

### Table Structure
- **Table Name**: `Connections-{Environment}`
- **Primary Key**: `connectionId` (String, HASH)
- **Global Secondary Indexes**:
  - `userId-index`: `userId` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `connectionId` | String | Yes | WebSocket connection ID (Primary Key) | AWS API Gateway connection ID |
| `userId` | String | Yes | Associated user ID | UUID format |
| `staff` | Boolean | No | Whether the connection belongs to staff | true, false |
| `ttl` | Number | No | Time-to-live for automatic cleanup | Unix timestamp |

### Sample Data
```json
{
  "connectionId": "abc123def456",
  "userId": "user-uuid-123",
  "staff": false,
  "ttl": 1693564800
}
```

### Important Notes
- TTL (Time To Live) is enabled for automatic cleanup of stale connections
- Used for real-time notifications and messaging
- Staff connections are marked separately for targeted messaging

---

## 4. Messages Table

**Purpose**: Stores chat messages between users and staff.

### Table Structure
- **Table Name**: `Messages-{Environment}`
- **Primary Key**: `messageId` (String, HASH)
- **Global Secondary Indexes**:
  - `senderId-index`: `senderId` (HASH)
  - `receiverId-index`: `receiverId` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `messageId` | String | Yes | Unique message identifier (Primary Key) | UUID format |
| `message` | String | Yes | Message content | Any string |
| `senderId` | String | Yes | Sender's user ID | UUID format |
| `receiverId` | String | Yes | Receiver's user ID | UUID format or "ALL" |
| `sent` | Boolean | Yes | Message sent status | true, false |
| `received` | Boolean | Yes | Message received status | true, false |
| `viewed` | Boolean | Yes | Message viewed status | true, false |
| `createdAt` | Number | Yes | Message timestamp | Unix timestamp |

### Sample Data
```json
{
  "messageId": "msg-uuid-123",
  "message": "Hello, I need help with my appointment",
  "senderId": "user-uuid-123",
  "receiverId": "staff-uuid-456",
  "sent": true,
  "received": true,
  "viewed": false,
  "createdAt": 1693478400
}
```

### Important Notes
- `receiverId` can be "ALL" for broadcast messages to all staff
- Message status tracking supports delivery confirmations
- Used for customer support chat functionality

---

## 5. UnavailableSlots Table

**Purpose**: Manages time slots that are unavailable for bookings.

### Table Structure
- **Table Name**: `UnavailableSlots-{Environment}`
- **Primary Key**: `date` (String, HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `date` | String | Yes | Date for unavailable slots (Primary Key) | YYYY-MM-DD format |
| `timeSlots` | List | Yes | List of unavailable time slot objects | Array of time slot objects |
| `updatedBy` | String | No | Staff member who created the slots | UUID format |

### Time Slot Object Structure
```json
{
  "startTime": "09:00",
  "endTime": "10:00"
}
```

### Sample Data
```json
{
  "date": "2024-01-15",
  "timeSlots": [
    {
      "startTime": "09:00",
      "endTime": "10:00"
    },
    {
      "startTime": "14:00",
      "endTime": "15:00"
    }
  ],
  "updatedBy": "staff-uuid-123"
}
```

### Important Notes
- Used for blocking specific time slots from being available for appointments
- Staff can manage availability for specific dates
- Time slots are in HH:MM format (24-hour)

---

## 6. Appointments Table

**Purpose**: Manages service appointments and their details.

### Table Structure
- **Table Name**: `Appointments-{Environment}`
- **Primary Key**: `appointmentId` (String, HASH)
- **Global Secondary Indexes**:
  - `assignedMechanicId-index`: `assignedMechanicId` (HASH)
  - `createdUserId-index`: `createdUserId` (HASH)
  - `scheduledDate-index`: `scheduledDate` (HASH)
  - `status-index`: `status` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `appointmentId` | String | Yes | Unique appointment identifier (Primary Key) | UUID format |
| `serviceId` | Number | Yes | Service type identifier | Positive integer |
| `planId` | Number | Yes | Service plan identifier | Positive integer |
| `isBuyer` | Boolean | Yes | Whether the customer is buying or selling | true, false |
| `buyerName` | String | Conditional | Buyer's name (required if isBuyer=true) | Any string |
| `buyerEmail` | String | Conditional | Buyer's email (required if isBuyer=true) | Valid email format |
| `buyerPhone` | String | Conditional | Buyer's phone (required if isBuyer=true) | Phone number format |
| `sellerName` | String | Conditional | Seller's name (required if isBuyer=false) | Any string |
| `sellerEmail` | String | Conditional | Seller's email (required if isBuyer=false) | Valid email format |
| `sellerPhone` | String | Conditional | Seller's phone (required if isBuyer=false) | Phone number format |
| `carMake` | String | Yes | Vehicle make | Any string |
| `carModel` | String | Yes | Vehicle model | Any string |
| `carYear` | String | Yes | Vehicle year | Year format |
| `carLocation` | String | Yes | Vehicle location | Any string |
| `notes` | String | No | Additional notes | Any string |
| `selectedSlots` | List | No | Preferred time slots | Array of slot objects |
| `scheduledDate` | String | No | Confirmed appointment date | YYYY-MM-DD format |
| `scheduledTimeSlot` | Object | No | Confirmed time slot | Time slot object |
| `assignedMechanicId` | String | No | Assigned mechanic's user ID | UUID format |
| `createdUserId` | String | Yes | User who created the appointment | UUID format |
| `status` | String | Yes | Appointment status | PENDING, SCHEDULED, ONGOING, COMPLETED, CANCELLED |
| `price` | Number | Yes | Service price | Positive number |
| `paymentStatus` | String | Yes | Payment status | pending, paid, failed |
| `paymentMethod` | String | No | Payment method used | cash, card, bank_transfer, stripe |
| `paymentConfirmedBy` | String | No | Staff who confirmed payment | UUID format |
| `paymentConfirmedAt` | Number | No | Payment confirmation timestamp | Unix timestamp |
| `postNotes` | String | No | Notes added after service completion | Any string |
| `reports` | List | No | Service reports | Array of report objects |
| `createdAt` | Number | Yes | Creation timestamp | Unix timestamp |
| `createdDate` | String | Yes | Creation date | YYYY-MM-DD format |
| `updatedAt` | Number | Yes | Last update timestamp | Unix timestamp |

### Selected Slots Object Structure
```json
{
  "date": "2024-01-15",
  "start": "09:00",
  "end": "10:00",
  "priority": 1
}
```

### Sample Data
```json
{
  "appointmentId": "appt-uuid-123",
  "serviceId": 1,
  "planId": 2,
  "isBuyer": true,
  "buyerName": "John Doe",
  "buyerEmail": "john@example.com",
  "buyerPhone": "0412345678",
  "carMake": "Toyota",
  "carModel": "Camry",
  "carYear": "2020",
  "carLocation": "Sydney",
  "notes": "Please check the engine",
  "status": "PENDING",
  "price": 280,
  "paymentStatus": "pending",
  "createdUserId": "user-uuid-123",
  "createdAt": 1693478400,
  "createdDate": "2024-01-15",
  "updatedAt": 1693478400
}
```

### Important Notes
- Either buyer or seller information is required based on `isBuyer` field
- Multiple GSIs support various query patterns
- Status workflow: PENDING → SCHEDULED → ONGOING → COMPLETED
- Stream enabled for real-time updates

---

## 7. ServicePrices Table

**Purpose**: Manages service pricing information.

### Table Structure
- **Table Name**: `ServicePrices-{Environment}`
- **Primary Key**: 
  - `serviceId` (Number, HASH)
  - `planId` (Number, RANGE)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `serviceId` | Number | Yes | Service identifier (Partition Key) | Positive integer |
| `planId` | Number | Yes | Plan identifier (Sort Key) | Positive integer |
| `serviceName` | String | Yes | Name of the service | Any string |
| `planName` | String | Yes | Name of the plan | Any string |
| `price` | Number | Yes | Price for the service plan | Positive number |
| `active` | Boolean | Yes | Whether the plan is active | true, false |

### Sample Data
```json
{
  "serviceId": 1,
  "planId": 1,
  "serviceName": "Pre Purchase Inspection",
  "planName": "Standard Pre Purchase Inspection",
  "price": 220,
  "active": true
}
```

### Important Notes
- Composite primary key allows multiple plans per service
- Only active plans should be displayed to customers
- Pricing is referenced by appointments logics for calculating service costs

---

## 8. Orders Table

**Purpose**: Manages orders for automotive parts and services.

### Table Structure
- **Table Name**: `Orders-{Environment}`
- **Primary Key**: `orderId` (String, HASH)
- **Global Secondary Indexes**:
  - `assignedMechanicId-index`: `assignedMechanicId` (HASH)
  - `createdUserId-index`: `createdUserId` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `orderId` | String | Yes | Unique order identifier (Primary Key) | UUID format |
| `items` | List | Yes | List of ordered items | Array of item objects |
| `customerName` | String | Yes | Customer's name | Any string |
| `customerEmail` | String | Yes | Customer's email | Valid email format |
| `customerPhone` | String | Yes | Customer's phone | Phone number format |
| `carMake` | String | Yes | Vehicle make | Any string |
| `carModel` | String | Yes | Vehicle model | Any string |
| `carYear` | String | Yes | Vehicle year | Year format |
| `notes` | String | No | Additional notes | Any string |
| `deliveryLocation` | String | Yes | Delivery address | Any string |
| `assignedMechanicId` | String | No | Assigned mechanic's user ID | UUID format |
| `createdUserId` | String | Yes | User who created the order | UUID format |
| `status` | String | Yes | Order status | PENDING, SCHEDULED, DELIVERED, CANCELLED |
| `totalPrice` | Number | Yes | Total order price | Positive number |
| `paymentStatus` | String | Yes | Payment status | pending, paid, failed |
| `paymentMethod` | String | No | Payment method used | cash, card, bank_transfer, stripe |
| `paymentConfirmedBy` | String | No | Staff who confirmed payment | UUID format |
| `paymentConfirmedAt` | Number | No | Payment confirmation timestamp | Unix timestamp |
| `postNotes` | String | No | Notes added after completion | Any string |
| `createdAt` | Number | Yes | Creation timestamp | Unix timestamp |
| `createdDate` | String | Yes | Creation date | YYYY-MM-DD format |
| `updatedAt` | Number | Yes | Last update timestamp | Unix timestamp |

### Item Object Structure
```json
{
  "categoryId": 1,
  "itemId": 2,
  "quantity": 2,
  "unitPrice": 100,
  "totalPrice": 200
}
```

### Sample Data
```json
{
  "orderId": "order-uuid-123",
  "items": [
    {
      "categoryId": 1,
      "itemId": 2,
      "quantity": 2,
      "unitPrice": 100,
      "totalPrice": 200
    }
  ],
  "customerName": "Jane Smith",
  "customerEmail": "jane@example.com",
  "customerPhone": "0412345678",
  "carMake": "Honda",
  "carModel": "Civic",
  "carYear": "2019",
  "deliveryLocation": "123 Main St, Sydney",
  "status": "PENDING",
  "totalPrice": 200,
  "paymentStatus": "pending",
  "createdUserId": "user-uuid-123",
  "createdAt": 1693478400,
  "createdDate": "2024-01-15",
  "updatedAt": 1693478400
}
```

### Important Notes
- Orders can contain multiple items
- Each item references ItemPrices table via categoryId and itemId
- Status workflow: PENDING → SCHEDULED → DELIVERED

---

## 9. ItemPrices Table

**Purpose**: Manages pricing for automotive parts and items.

### Table Structure
- **Table Name**: `ItemPrices-{Environment}`
- **Primary Key**: 
  - `categoryId` (Number, HASH)
  - `itemId` (Number, RANGE)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `categoryId` | Number | Yes | Category identifier (Partition Key) | Positive integer |
| `itemId` | Number | Yes | Item identifier (Sort Key) | Positive integer |
| `categoryName` | String | Yes | Name of the category | Any string |
| `itemName` | String | Yes | Name of the item | Any string |
| `price` | Number | Yes | Price for the item | Positive number |
| `active` | Boolean | Yes | Whether the item is active | true, false |

### Sample Data
```json
{
  "categoryId": 1,
  "itemId": 1,
  "categoryName": "Engines & Parts",
  "itemName": "V8 Engine",
  "price": 150,
  "active": true
}
```

### Important Notes
- Composite primary key allows multiple items per category
- Categories group related items (e.g., "Engines & Parts", "Tyres & Wheels")
- Only active items should be available for ordering

---

## 10. Inquiries Table

**Purpose**: Manages customer inquiries and support requests.

### Table Structure
- **Table Name**: `Inquiries-{Environment}`
- **Primary Key**: `inquiryId` (String, HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `inquiryId` | String | Yes | Unique inquiry identifier (Primary Key) | UUID format |
| `firstName` | String | Yes | Customer's first name | Any string |
| `lastName` | String | Yes | Customer's last name | Any string |
| `email` | String | Yes | Customer's email | Valid email format |
| `message` | String | Yes | Inquiry message | Any string |
| `userId` | String | Yes | Associated user ID | UUID format |
| `status` | String | No | Inquiry status | OPEN, IN_PROGRESS, RESOLVED, CLOSED |
| `createdAt` | Number | Yes | Creation timestamp | Unix timestamp |
| `createdDate` | String | Yes | Creation date | YYYY-MM-DD format |

### Sample Data
```json
{
  "inquiryId": "inq-uuid-123",
  "firstName": "John",
  "lastName": "Doe",
  "email": "john@example.com",
  "message": "I have a question about my car service",
  "userId": "user-uuid-123",
  "createdAt": 1693478400,
  "createdDate": "2024-01-15"
}
```

### Important Notes
- Used for general customer support inquiries
- Can be linked to specific users

---

## 11. Payments Table

**Purpose**: Manages payment records, related to stripe payments.
### Table Structure
- **Table Name**: `Payments-{Environment}`
- **Primary Key**: `paymentIntentId` (String, HASH)
- **Global Secondary Indexes**:
  - `userId-index`: `userId` (HASH), `createdAt` (RANGE)
  - `referenceNumber-index`: `referenceNumber` (HASH)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `paymentIntentId` | String | Yes | Unique payment identifier (Primary Key) | Stripe payment intent ID or UUID |
| `referenceNumber` | String | Yes | Reference to appointment/order | UUID format |
| `type` | String | Yes | Type of payment | appointment, order |
| `userId` | String | Yes | User who made the payment | UUID format |
| `amount` | Number | Yes | Payment amount | Positive number |
| `status` | String | Yes | Payment status | pending, completed, failed, cancelled |
| `stripePaymentMethodId` | String | No | Stripe payment method ID | Stripe PM ID |
| `metadata` | String | No | Additional payment metadata | JSON string |
| `createdAt` | Number | Yes | Creation timestamp | Unix timestamp |
| `updatedAt` | Number | Yes | Last update timestamp | Unix timestamp |

### Sample Data
```json
{
  "paymentIntentId": "pi_stripe_123456",
  "referenceNumber": "appt-uuid-123",
  "type": "appointment",
  "userId": "user-uuid-123",
  "amount": 280,
  "status": "completed",
  "createdAt": 1693478400,
  "updatedAt": 1693478400
}
```

### Important Notes
- Links payments to appointments or orders via referenceNumber
- GSI allows querying by user and reference number

---

## 12. Invoices Table

**Purpose**: Manages invoice records and generation history.

### Table Structure
- **Table Name**: `Invoices-{Environment}`
- **Primary Key**: `invoiceId` (String, HASH)
- **Global Secondary Indexes**:
  - `createdAt-index`: `createdAt` (HASH), `invoiceId` (RANGE)

### Fields

| Field | Type | Required | Description | Valid Values |
|-------|------|----------|-------------|--------------|
| `invoiceId` | String | Yes | Unique invoice identifier (Primary Key) | UUID format |
| `paymentIntentId` | String | Yes | Associated payment ID | Payment intent ID |
| `referenceNumber` | String | Yes | Reference to appointment/order | UUID format |
| `referenceType` | String | Yes | Invoice type | appointment, order, admin_set, invoice_id |
| `status` | String | Yes | Invoice status | generated, cancelled. **Note: metadata.paymentStatus is automatically synchronized with this field** |
| `fileUrl` | String | No | Invoice PDF URL | Valid URL |
| `format` | String | Yes | Invoice format | pdf, html |
| `metadata` | Object | No | Invoice metadata | Object with invoice details |
| `analyticsData` | Object | No | **CRITICAL BUSINESS INTELLIGENCE DATA** - Contains comprehensive transaction analytics | Complex nested object with operation details |

### AnalyticsData Structure

The `analyticsData` field is **THE MOST IMPORTANT** field in the Invoices table as it contains complete business intelligence information for every transaction. This field has the following structure:

```json
{
  "operation_type": "transaction",
  "operation_data": {
    "services": [
      {
        "service_name": "Standard Pre Purchase Inspection",
        "price": "220"
      }
    ],
    "orders": [
      {
        "item_name": "V8 Engine",
        "unit_price": "150",
        "quantity": "2",
        "total_price": "300"
      }
    ],
    "customerId": "customer@example.com",
    "vehicleDetails": {
      "make": "Toyota",
      "model": "Camry",
      "year": "2020"
    },
    "paymentDetails": {
      "payment_method": "stripe",
      "amount": "280",
      "date": "15/01/2024",
      "paid_before_operation": 1
    },
    "bookingDetails": {
      "bookedBy": "user-uuid-123",
      "bookedDate": "2024-01-15",
      "bookedAt": "1693478400"
    }
  }
}
```

#### AnalyticsData Field Definitions

**Root Level:**
- `operation_type`: Always "transaction"
- `operation_data`: Contains all detailed transaction information

**Operation Data Structure:**

| Field | Type | Description | Valid Values |
|-------|------|-------------|--------------|
| `services` | Array | List of services provided | Array of service objects |
| `orders` | Array | List of items/parts ordered | Array of order item objects |
| `customerId` | String | Customer's email address | Valid email format |
| `vehicleDetails` | Object | Vehicle information | Vehicle details object |
| `paymentDetails` | Object | Payment transaction details | Payment information object |
| `bookingDetails` | Object | Booking/creation details | Booking information object |

**Service Object Structure:**
- `service_name`: String - Name of the service (uses plan name, not service name)
- `price`: String - Service price as string

**Order Item Object Structure:**
- `item_name`: String - Name of the item/part
- `unit_price`: String - Price per unit as string
- `quantity`: String - Quantity ordered as string
- `total_price`: String - Total price for this item as string

**Vehicle Details Object:**
- `make`: String - Vehicle manufacturer
- `model`: String - Vehicle model
- `year`: String - Vehicle year

**Payment Details Object:**
- `payment_method`: String - Payment method used (stripe, cash, bank_transfer, card, unknown)
- `amount`: String - Total payment amount as string
- `date`: String - Payment date in DD/MM/YYYY format
- `paid_before_operation`: Number - 1 if paid before operation, 0 if not

**Booking Details Logic:**
   - If `createdUserId` matches a staff member: `bookedBy = "STAFF"`
   - If `createdUserId` matches a regular user: `bookedBy = userId`
   - If no valid user found: `bookedBy = "NONE"` (for non-booked services/orders)

### Sample Data
```json
{
  "invoiceId": "inv-uuid-123",
  "paymentIntentId": "pi_stripe_123456",
  "referenceNumber": "appt-uuid-123",
  "referenceType": "appointment",
  "status": "generated",
  "fileUrl": "https://s3.amazonaws.com/invoices/inv-uuid-123.pdf",
  "format": "pdf",
  "analyticsData": {
    "operation_type": "transaction",
    "operation_data": {
      "services": [
        {
          "service_name": "Comprehensive Pre Purchase Inspection",
          "price": "280"
        }
      ],
      "orders": [],
      "customerId": "john@example.com",
      "vehicleDetails": {
        "make": "Toyota",
        "model": "Camry",
        "year": "2020"
      },
      "paymentDetails": {
        "payment_method": "stripe",
        "amount": "280",
        "date": "15/01/2024",
        "paid_before_operation": 1
      },
      "bookingDetails": {
        "bookedBy": "user-uuid-123",
        "bookedDate": "2024-01-15",
        "bookedAt": "1693478400"
      }
    }
  },
  "createdAt": 1693478400
}
```

### Important Notes
- **CRITICAL**: The `analyticsData` field is the primary source for business intelligence and reporting
- Links to payments, appointments, and orders for complete transaction tracking
- All numeric values stored as strings within analytics data for consistency
- Analytics data supports business reporting, customer behavior analysis, and operational insights
- This field is essential for understanding revenue streams, popular services, customer patterns, and business performance metrics
| `createdAt` | Number | Yes | Creation timestamp | Unix timestamp |



### Sample Data
```json
{
  "invoiceId": "inv-uuid-123",
  "paymentIntentId": "pi_stripe_123456",
  "referenceNumber": "appt-uuid-123",
  "referenceType": "appointment",
  "status": "generated",
  "fileUrl": "https://s3.amazonaws.com/invoices/inv-uuid-123.pdf",
  "format": "pdf",
  "createdAt": 1693478400
}
```

### Important Notes
- Generated automatically after successful payments
- Links to payments, appointments, and orders
- Analytics data supports business reporting

---
