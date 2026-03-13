"""
setup.py - Gmail Skill Setup
Performs the initial OAuth2 flow to get a refresh token.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Add parent dir to path to import models and credential_manager
sys.path.append(str(Path(__file__).parent.parent.parent))

from skills.gmail.credential_manager import CredentialManager, EmailCredential
from skills.gmail.models import EmailProvider

def run_setup():
    print("=== Gmail Skill Setup for The Moon ===")
    
    load_dotenv()
    
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set in .env")
        return

    email_address = input("Enter your Gmail address: ").strip()
    
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    
    # We need to construct a client_config dict because we might not have a json file
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost:8080"]
        }
    }
    
    flow = InstalledAppFlow.from_client_config(client_config, scopes)
    creds = flow.run_local_server(port=8080)
    
    # Save token
    token_dir = Path.home() / ".moon" / "email"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / f"token_gmail_{email_address}.json"
    
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())
        
    # Register in CredentialManager
    manager = CredentialManager()
    new_cred = EmailCredential(
        id=f"gmail_{email_address}",
        provider="gmail",
        email_address=email_address,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
        auth_type="oauth2",
        status="active"
    )
    manager.add_credential(new_cred)
    
    print(f"\nSuccess! Token saved to {token_path}")
    print("Gmail Skill is now ready to use in The Moon.")

if __name__ == "__main__":
    run_setup()
