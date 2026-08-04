import msal
import requests

from django.conf import settings


def get_access_token():

    app = msal.ConfidentialClientApplication(
        settings.GRAPH_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}",
        client_credential=settings.GRAPH_CLIENT_SECRET
    )

    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" not in result:
        raise Exception(result)

    return result["access_token"]


def send_graph_email(
    to_email,
    subject,
    html_content,
    cc_emails=None
):

    token = get_access_token()

    endpoint = (
        f"https://graph.microsoft.com/v1.0/users/"
        f"{settings.GRAPH_SENDER}/sendMail"
    )

    cc_recipients = []
    for cc in (cc_emails or []):
        if cc:
            cc_recipients.append({
                "emailAddress": {
                    "address": cc
                }
            })

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_content
            },
            
        "toRecipients": [
            {
                "emailAddress": {
                    "address": to_email
                }
            }
        ],
        "ccRecipients": cc_recipients

        }
    }

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    print(response.status_code)
    print(response.text)

    response.raise_for_status()