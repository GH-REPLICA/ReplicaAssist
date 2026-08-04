from azure.communication.email import EmailClient
from django.conf import settings

def send_email_acs(to_email, subject, body):

    try:
        client = EmailClient.from_connection_string(
            settings.ACS_CONNECTION_STRING
        )

        message = {
            "senderAddress": settings.ACS_SENDER_EMAIL,
            "recipients": {
                "to": [{"address": to_email}]
            },
            "content": {
                "subject": subject,
                "plainText": body
            }
        }

        poller = client.begin_send(message)
        result = poller.result()

        return result

    except Exception as e:
        print("Error enviando correo:", e)
        return None