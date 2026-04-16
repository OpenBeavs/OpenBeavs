"""Peewee migrations -- 023_add_agent_deployment_fields.py.

Add deployment-related fields to agent table for the Agent Deploy View feature.

Note: `model` is added via raw SQL because `migrator.add_fields('agent', model=...)`
collides with the `model` positional arg of `add_fields`.
"""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator


with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""

    migrator.add_fields(
        'agent',
        system_prompt=pw.TextField(null=True),
        provider=pw.TextField(null=True),
        deployment_mode=pw.TextField(null=True),
        deployment_status=pw.TextField(null=True),
    )
    migrator.sql('ALTER TABLE agent ADD COLUMN model TEXT')


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""

    migrator.remove_fields(
        'agent',
        'system_prompt',
        'provider',
        'deployment_mode',
        'deployment_status',
    )
    migrator.sql('ALTER TABLE agent DROP COLUMN model')
