from django.db import migrations


def ensure_ticketmessage_message_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = "tickets_ticketmessage"

    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        if table_name not in table_names:
            return

        description = connection.introspection.get_table_description(cursor, table_name)
        columns = {col.name for col in description}

        if "message" not in columns:
            # Keep this SQL simple and compatible with the current SQLite production setup.
            cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "message" text')
            columns.add("message")

        if "body" in columns:
            cursor.execute(
                f'UPDATE "{table_name}" '
                f'SET "message" = "body" '
                f'WHERE "message" IS NULL OR "message" = ""'
            )


def noop_reverse(apps, schema_editor):
    # Intentionally no reverse, since this migration is a production schema repair.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0009_ticket_sla_pause_started_at"),
    ]

    operations = [
        migrations.RunPython(ensure_ticketmessage_message_column, noop_reverse),
    ]
