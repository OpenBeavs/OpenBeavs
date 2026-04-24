"""Peewee migrations -- 024_add_registry_card_url.py.

Store the original well-known card URL on registry entries so the hub can
re-fetch the card for install regardless of its path.
"""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator


with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""

    migrator.add_fields(
        'registry_agent',
        card_url=pw.TextField(null=True)
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""

    migrator.remove_fields('registry_agent', 'card_url')
