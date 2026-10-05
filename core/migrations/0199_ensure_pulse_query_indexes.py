from django.db import migrations, models


class RenameIndexIfPresent(migrations.RenameIndex):
    def state_forwards(self, app_label, state):
        model_state = state.models[app_label, self.model_name_lower]
        names = {index.name for index in model_state.options.get("indexes", [])}
        if self.old_name not in names:
            return
        super().state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_model_state = from_state.models[app_label, self.model_name_lower]
        names = {index.name for index in from_model_state.options.get("indexes", [])}
        if self.old_name not in names:
            return
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(
                cursor, model._meta.db_table
            )
        if self.old_name not in constraints or self.new_name in constraints:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class EnsureIndex(migrations.AddIndex):
    """Create a named index when it is missing from state or the database.

    Migration 0198 used to drop these Pulse indexes, and some databases
    applied that drop before the operation was removed. Other databases
    never recorded the index name in migration state. This operation
    leaves an existing index alone and creates it only when needed.
    """

    def state_forwards(self, app_label, state):
        model_state = state.models[app_label, self.model_name_lower]
        names = {index.name for index in model_state.options.get("indexes", [])}
        if self.index.name in names:
            return
        super().state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(
                cursor, model._meta.db_table
            )
        if self.index.name in constraints:
            return
        schema_editor.add_index(model, self.index)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        return


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0198_alter_bankaccount_options_and_more"),
    ]

    operations = [
        RenameIndexIfPresent(
            model_name="insurancepolicy",
            old_name="core_inspol_org_stage_bound_idx",
            new_name="core_pol_org_stg_bound_idx",
        ),
        EnsureIndex(
            model_name="banktransaction",
            index=models.Index(
                fields=["bank_account", "date"],
                name="core_banktx_acct_date_idx",
            ),
        ),
        EnsureIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "stage", "bound_date"],
                name="core_pol_org_stg_bound_idx",
            ),
        ),
        EnsureIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "stage", "status"],
                name="core_inspol_org_stage_stat_idx",
            ),
        ),
        EnsureIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "insurance_company", "stage"],
                name="core_inspol_org_co_stage_idx",
            ),
        ),
        EnsureIndex(
            model_name="servicerecord",
            index=models.Index(
                fields=["organization", "transaction_date"],
                name="core_svcrec_org_txdate_idx",
            ),
        ),
    ]
