"""
Enhanced Email Threading Manager for proper email thread handling
This module ensures that sent emails maintain proper threading relationships
that are compatible with all major email clients.
"""

import os
import re
import uuid
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple
import hashlib

class EmailThreadingManager:
    """
    Manages email threading using standard email protocols.
    Ensures compatibility with all major email clients (Gmail, Outlook, Apple Mail, etc.)
    """
    
    def __init__(self):
        self.dynamodb = boto3.client('dynamodb')
        self.threads_table = os.environ.get('EMAIL_THREADS_TABLE')
        self.emails_table = os.environ.get('EMAIL_METADATA_TABLE')
        self.mail_domain = self._extract_domain_from_mail_address()
    
    def _extract_domain_from_mail_address(self) -> str:
        """Extract domain from MAIL_FROM_ADDRESS for Message-ID generation"""
        mail_from = os.environ.get('MAIL_FROM_ADDRESS', '')
        if '@' in mail_from:
            return mail_from.split('@')[1]
        return 'autolabsolutions.com'  # fallback
    
    def generate_message_id(self, thread_id: Optional[str] = None) -> str:
        """
        Generate a proper Message-ID for outgoing emails.
        Format: <unique-id@domain>
        """
        # Create a unique identifier
        timestamp = str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() * 1000))
        random_part = str(uuid.uuid4()).replace('-', '')[:8]
        
        # Include thread_id in the message ID for better tracking
        if thread_id:
            thread_part = hashlib.md5(thread_id.encode()).hexdigest()[:8]
            unique_id = f"{timestamp}-{random_part}-{thread_part}"
        else:
            unique_id = f"{timestamp}-{random_part}"
        
        return f"<{unique_id}@{self.mail_domain}>"
    
    def normalize_message_id(self, message_id: str) -> str:
        """Normalize Message-ID by removing angle brackets and ensuring consistency"""
        if not message_id:
            return ""
        
        # Remove angle brackets
        normalized = message_id.strip('<>')
        
        # Remove AWS SES suffix if present for consistency
        if normalized.endswith('@email.amazonses.com'):
            normalized = normalized[:-len('@email.amazonses.com')]
        
        return normalized
    
    def get_thread_info_for_reply(self, in_reply_to_message_id: str) -> Optional[Dict]:
        """
        Get thread information for composing a reply email.
        Returns thread info including Message-ID history for proper References header.
        """
        if not in_reply_to_message_id or not self.emails_table:
            return None
        
        normalized_id = self.normalize_message_id(in_reply_to_message_id)
        
        try:
            # Get the original email metadata
            response = self.dynamodb.get_item(
                TableName=self.emails_table,
                Key={'messageId': {'S': normalized_id}}
            )
            
            if 'Item' not in response:
                print(f"Threading - Original message not found: {normalized_id}")
                return None
            
            original_email = response['Item']
            thread_id = original_email.get('threadId', {}).get('S')
            
            if not thread_id:
                print(f"Threading - No thread ID found for message: {normalized_id}")
                return None
            
            # Get all messages in this thread to build References header
            thread_messages = self._get_thread_message_history(thread_id)
            
            # Build References header (should include all previous Message-IDs in chronological order)
            references = []
            for msg in thread_messages:
                msg_id = msg.get('messageId', {}).get('S')
                if msg_id and msg_id != normalized_id:
                    references.append(f"<{msg_id}>")
            
            # Add the immediate parent message
            if normalized_id not in [ref.strip('<>') for ref in references]:
                references.append(f"<{normalized_id}>")
            
            return {
                'thread_id': thread_id,
                'in_reply_to': f"<{normalized_id}>",
                'references': ' '.join(references),
                'subject': original_email.get('subject', {}).get('S', ''),
                'original_from': original_email.get('fromEmail', {}).get('S', ''),
                'participants': self._get_thread_participants(thread_id)
            }
            
        except Exception as e:
            print(f"Threading - Error getting thread info for reply: {str(e)}")
            return None
    
    def _get_thread_message_history(self, thread_id: str) -> List[Dict]:
        """Get all messages in a thread sorted by date for building References header"""
        if not self.emails_table:
            return []
        
        try:
            # Query emails by thread_id (assuming there's a GSI on threadId)
            response = self.dynamodb.query(
                TableName=self.emails_table,
                IndexName='threadId-receivedDate-index',  # Assuming this GSI exists
                KeyConditionExpression='threadId = :threadId',
                ExpressionAttributeValues={
                    ':threadId': {'S': thread_id}
                },
                ScanIndexForward=True  # Sort by receivedDate ascending
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            print(f"Threading - Error getting thread history: {str(e)}")
            # Fallback to scan if GSI doesn't exist
            try:
                response = self.dynamodb.scan(
                    TableName=self.emails_table,
                    FilterExpression='threadId = :threadId',
                    ExpressionAttributeValues={
                        ':threadId': {'S': thread_id}
                    }
                )
                
                # Sort by receivedDate manually
                items = response.get('Items', [])
                items.sort(key=lambda x: x.get('receivedDate', {}).get('S', ''))
                return items
                
            except Exception as scan_error:
                print(f"Threading - Error in fallback scan: {str(scan_error)}")
                return []
    
    def _get_thread_participants(self, thread_id: str) -> List[str]:
        """Get all participants in a thread"""
        if not self.threads_table:
            return []
        
        try:
            response = self.dynamodb.get_item(
                TableName=self.threads_table,
                Key={'threadId': {'S': thread_id}}
            )
            
            if 'Item' in response:
                return response['Item'].get('participants', {}).get('SS', [])
            
        except Exception as e:
            print(f"Threading - Error getting thread participants: {str(e)}")
        
        return []
    
    def create_reply_headers(self, in_reply_to_message_id: str) -> Dict[str, str]:
        """
        Create proper email headers for a reply.
        Returns headers that ensure proper threading in email clients.
        """
        headers = {}
        
        if not in_reply_to_message_id:
            return headers
        
        # Get thread information
        thread_info = self.get_thread_info_for_reply(in_reply_to_message_id)
        
        if thread_info:
            headers['In-Reply-To'] = thread_info['in_reply_to']
            headers['References'] = thread_info['references']
            
            # Ensure subject has proper Re: prefix for replies
            original_subject = thread_info['subject']
            if original_subject and not original_subject.lower().startswith('re:'):
                headers['Subject-Prefix'] = 'Re: '
        
        return headers
    
    def find_or_create_thread_for_outbound(self, 
                                         to_emails: List[str], 
                                         cc_emails: List[str], 
                                         subject: str,
                                         in_reply_to_message_id: Optional[str] = None,
                                         sender_email: str = None) -> Optional[str]:
        """
        Find existing thread or create new one for outbound email.
        Prioritizes proper email threading standards.
        """
        all_participants = []
        if sender_email:
            all_participants.append(sender_email.lower())
        all_participants.extend([email.lower() for email in to_emails if email])
        all_participants.extend([email.lower() for email in cc_emails if email])
        all_participants = list(set(all_participants))  # Remove duplicates
        
        print(f"Threading - Finding thread for outbound email")
        print(f"Threading - Subject: '{subject}'")
        print(f"Threading - Participants: {all_participants}")
        print(f"Threading - In-Reply-To: {in_reply_to_message_id}")
        
        # Step 1: If replying to a specific message, find its thread
        if in_reply_to_message_id:
            thread_info = self.get_thread_info_for_reply(in_reply_to_message_id)
            if thread_info:
                thread_id = thread_info['thread_id']
                print(f"Threading - Found existing thread by In-Reply-To: {thread_id}")
                return thread_id
        
        # Step 2: Try to find thread by subject and participants
        thread_id = self._find_thread_by_subject_and_participants(subject, all_participants)
        if thread_id:
            print(f"Threading - Found existing thread by subject/participants: {thread_id}")
            return thread_id
        
        # Step 3: Create new thread if none found
        thread_id = self._create_new_thread(
            participants=all_participants,
            subject=subject,
            created_by=sender_email or os.environ.get('MAIL_FROM_ADDRESS', ''),
            primary_customer_email=to_emails[0] if to_emails else None
        )
        
        if thread_id:
            print(f"Threading - Created new thread: {thread_id}")
        else:
            print(f"Threading - Failed to create new thread")
        
        return thread_id
    
    def _normalize_subject(self, subject: str) -> str:
        """Normalize subject for thread matching"""
        if not subject:
            return ""
        
        normalized = subject.lower().strip()
        
        # Remove reply/forward prefixes (loop until no more prefixes found)
        while True:
            old_normalized = normalized
            # Remove common prefixes
            for prefix in [r'^re:\s*', r'^fwd?:\s*', r'^fw:\s*', r'^forward:\s*']:
                normalized = re.sub(prefix, '', normalized)
            
            # If no change was made, we're done
            if normalized == old_normalized:
                break
        
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _find_thread_by_subject_and_participants(self, subject: str, participants: List[str]) -> Optional[str]:
        """Find existing thread by subject and participants"""
        if not self.threads_table or not subject:
            return None
        
        normalized_subject = self._normalize_subject(subject)
        if not normalized_subject:
            return None
        
        try:
            # Search for threads with matching normalized subject
            response = self.dynamodb.scan(
                TableName=self.threads_table,
                FilterExpression='normalizedSubject = :subject AND isActive = :active',
                ExpressionAttributeValues={
                    ':subject': {'S': normalized_subject},
                    ':active': {'BOOL': True}
                }
            )
            
            # Check for participant overlap
            normalized_participants = set(p.lower().strip() for p in participants if p)
            
            for item in response.get('Items', []):
                thread_participants = set(item.get('participants', {}).get('SS', []))
                
                # Check if there's significant overlap (at least one common participant)
                common_participants = normalized_participants & thread_participants
                if common_participants:
                    thread_id = item['threadId']['S']
                    print(f"Threading - Found thread {thread_id} with common participants: {list(common_participants)}")
                    return thread_id
            
        except Exception as e:
            print(f"Threading - Error finding thread by subject/participants: {str(e)}")
        
        return None
    
    def _create_new_thread(self, participants: List[str], subject: str, 
                          created_by: str, primary_customer_email: Optional[str]) -> Optional[str]:
        """Create a new email thread"""
        if not self.threads_table:
            print("Threading - EMAIL_THREADS_TABLE not configured")
            return None
        
        thread_id = str(uuid.uuid4())
        normalized_subject = self._normalize_subject(subject)
        
        try:
            # Filter out our own email for customer identification
            our_email = os.environ.get('MAIL_FROM_ADDRESS', '').lower()
            customer_email = primary_customer_email
            if not customer_email:
                external_participants = [p for p in participants if p.lower() != our_email]
                customer_email = external_participants[0] if external_participants else None
            
            # Create TTL (2 years from now)
            ttl = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() + (2 * 365 * 24 * 60 * 60))
            created_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() * 1000)
            
            item = {
                'threadId': {'S': thread_id},
                'normalizedSubject': {'S': normalized_subject},
                'originalSubject': {'S': subject},
                'participants': {'SS': list(set(participants))},
                'createdBy': {'S': created_by.lower()},
                'primaryCustomerEmail': {'S': customer_email.lower() if customer_email else ''},
                'messageCount': {'N': '0'},
                'lastMessageId': {'S': ''},
                'lastActivityDate': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
                'isActive': {'BOOL': True},
                'ttl': {'N': str(ttl)},
                'createdAt': {'N': str(created_timestamp)},
                'updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
            }
            
            self.dynamodb.put_item(TableName=self.threads_table, Item=item)
            print(f"Threading - Created new thread: {thread_id}")
            return thread_id
            
        except Exception as e:
            print(f"Threading - Error creating new thread: {str(e)}")
            return None
    
    def update_thread_after_send(self, thread_id: str, message_id: str) -> bool:
        """Update thread metadata after sending an email"""
        if not thread_id or not self.threads_table:
            return False
        
        normalized_message_id = self.normalize_message_id(message_id)
        
        try:
            self.dynamodb.update_item(
                TableName=self.threads_table,
                Key={'threadId': {'S': thread_id}},
                UpdateExpression='SET lastMessageId = :messageId, lastActivityDate = :date, messageCount = messageCount + :inc, updatedAt = :date',
                ExpressionAttributeValues={
                    ':messageId': {'S': normalized_message_id},
                    ':date': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
                    ':inc': {'N': '1'}
                }
            )
            
            print(f"Threading - Updated thread {thread_id} with message {normalized_message_id}")
            return True
            
        except Exception as e:
            print(f"Threading - Error updating thread: {str(e)}")
            return False
    
    def prepare_outbound_email_headers(self, 
                                     to_emails: List[str],
                                     cc_emails: List[str],
                                     subject: str,
                                     sender_email: str,
                                     in_reply_to_message_id: Optional[str] = None) -> Dict[str, str]:
        """
        Prepare all headers needed for proper email threading in outbound emails.
        This is the main function to call when sending emails.
        """
        headers = {}
        
        # Generate a unique Message-ID for this outbound email
        thread_id = self.find_or_create_thread_for_outbound(
            to_emails=to_emails,
            cc_emails=cc_emails, 
            subject=subject,
            in_reply_to_message_id=in_reply_to_message_id,
            sender_email=sender_email
        )
        
        # Generate Message-ID
        message_id = self.generate_message_id(thread_id)
        headers['Message-ID'] = message_id
        
        # Add threading headers if this is a reply
        if in_reply_to_message_id:
            reply_headers = self.create_reply_headers(in_reply_to_message_id)
            headers.update(reply_headers)
            
            # Ensure subject has Re: prefix if replying
            if 'Subject-Prefix' in reply_headers and not subject.lower().startswith('re:'):
                headers['Subject'] = f"Re: {subject}"
        
        # Store thread_id for later use
        headers['X-Thread-ID'] = thread_id or ''
        
        print(f"Threading - Prepared headers for outbound email:")
        print(f"Threading - Message-ID: {message_id}")
        print(f"Threading - Thread-ID: {thread_id}")
        print(f"Threading - In-Reply-To: {headers.get('In-Reply-To', 'None')}")
        print(f"Threading - References: {headers.get('References', 'None')}")
        
        return headers
