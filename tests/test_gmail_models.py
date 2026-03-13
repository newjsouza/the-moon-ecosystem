"""
test_gmail_models.py - Unit tests for Gmail models
"""

import unittest
from datetime import datetime
from skills.gmail.models import EmailMessage, EmailProvider, EmailAttachment

class TestGmailModels(unittest.TestCase):
    
    def test_email_message_to_dict(self):
        msg = EmailMessage(
            id="123",
            account_id="acc_1",
            provider=EmailProvider.GMAIL,
            subject="Test Subject",
            from_address="sender@example.com",
            from_name="Sender",
            to_addresses=["receiver@example.com"]
        )
        
        d = msg.to_dict()
        self.assertEqual(d["id"], "123")
        self.assertEqual(d["provider"], "gmail")
        self.assertEqual(d["subject"], "Test Subject")
        self.assertEqual(d["from_address"], "sender@example.com")
        
    def test_attachment(self):
        att = EmailAttachment(
            filename="test.txt",
            content_type="text/plain",
            size=10,
            data=b"hello world"
        )
        self.assertEqual(att.filename, "test.txt")
        self.assertEqual(att.size, 10)

if __name__ == "__main__":
    unittest.main()
