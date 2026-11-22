from django.db import migrations

CREATE = """
CREATE FUNCTION accounts_auditlog_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'accounts_auditlog is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_auditlog_no_change
  BEFORE UPDATE OR DELETE ON accounts_auditlog
  FOR EACH ROW EXECUTE FUNCTION accounts_auditlog_append_only();
"""
DROP = """
DROP TRIGGER accounts_auditlog_no_change ON accounts_auditlog;
DROP FUNCTION accounts_auditlog_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunSQL(CREATE, DROP)]
