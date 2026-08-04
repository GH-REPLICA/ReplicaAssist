from django.db import migrations, models


def ensure_profile_phone_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = "tickets_profile"

    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        if table_name not in table_names:
            return

        description = connection.introspection.get_table_description(cursor, table_name)
        columns = {col.name for col in description}

        if "phone" not in columns:
            cursor.execute(
                f'ALTER TABLE "{table_name}" '
                f'ADD COLUMN "phone" varchar(20) NOT NULL DEFAULT ""'
            )


def noop_reverse(apps, schema_editor):
    # This is a forward-only schema repair migration.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0010_fix_ticketmessage_message_column"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_profile_phone_column, noop_reverse),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="profile",
                    name="phone",
                    field=models.CharField(blank=True, default="", max_length=20),
                ),
            ],
        ),
    ]