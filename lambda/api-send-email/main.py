import json
import response_utils as resp
import request_utils as req
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Send email through admin interface with business logic validation and threading support"""
    
    print(f"Send email request received: {json.dumps(event, default=str)}")
    
    try:
        # Extract request parameters
        staff_user_email = req.get_staff_user_email(event)
        to_emails = req.get_body_param(event, 'to')
        subject = req.get_body_param(event, 'subject')
        text_content = req.get_body_param(event, 'text', '')
        html_content = req.get_body_param(event, 'html', '')
        attachments = req.get_body_param(event, 'attachments', [])
        cc_emails = req.get_body_param(event, 'cc', [])
        bcc_emails = req.get_body_param(event, 'bcc', [])
        reply_to = req.get_body_param(event, 'reply_to')
        
        # Threading parameters
        thread_id = req.get_body_param(event, 'thread_id')
        in_reply_to_message_id = req.get_body_param(event, 'in_reply_to_message_id')
        
        print(f"Extracted parameters:")
        print(f"  staff_user_email: {staff_user_email}")
        print(f"  to_emails: {to_emails}")
        print(f"  subject: {subject}")
        print(f"  text_content length: {len(text_content) if text_content else 0}")
        print(f"  html_content length: {len(html_content) if html_content else 0}")
        print(f"  attachments count: {len(attachments) if attachments else 0}")
        print(f"  cc_emails: {cc_emails}")
        print(f"  bcc_emails: {bcc_emails}")
        print(f"  reply_to: {reply_to}")
        print(f"  thread_id: {thread_id}")
        print(f"  in_reply_to_message_id: {in_reply_to_message_id}")
        
        # Use email manager to handle the complete workflow
        result = biz.EmailManager.send_admin_email(
            staff_user_email=staff_user_email,
            to_emails=to_emails,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            attachments=attachments,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            reply_to=reply_to,
            thread_id=thread_id,
            in_reply_to_message_id=in_reply_to_message_id
        )
        
        print(f"Email sent successfully: {result}")
        return resp.success_response(result)
        
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        raise  # Re-raise to let the decorator handle it