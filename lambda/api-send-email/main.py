import response_utils as resp
import request_utils as req
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Send email through admin interface with business logic validation"""
    
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
        reply_to=reply_to
    )
    
    return resp.success_response(result)