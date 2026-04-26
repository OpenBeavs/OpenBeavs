"""Session-scoped postgres container for the security suite.

The repo's `AbstractPostgresTest` spins a new container *per test class* and
doesn't re-run migrations, so the second class in a run hits
`relation "auth" does not exist`. Here we spin up one container for the whole
suite and attach the resulting TestClient to every class via an autouse fixture.

Test classes in this package inherit from `AbstractIntegrationTest` (the plain
base — no docker lifecycle) and receive `fast_api_client` from the fixture.
"""

import logging
import os
import time

import docker
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

log = logging.getLogger(__name__)

_CONTAINER_NAME = "postgres-test-container-will-get-deleted"


def _spin_up_postgres_and_client():
    env_vars = {
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "example",
        "POSTGRES_DB": "openwebui",
    }
    client = docker.from_env()
    # best-effort cleanup of a stale container from a previous aborted run
    try:
        client.containers.get(_CONTAINER_NAME).remove(force=True)
    except Exception:
        pass
    client.containers.run(
        "postgres:16.2",
        detach=True,
        environment=env_vars,
        name=_CONTAINER_NAME,
        ports={5432: ("0.0.0.0", 8081)},
        command="postgres -c log_statement=all",
    )
    time.sleep(0.5)
    database_url = f"postgresql://user:example@127.0.0.1:8081/openwebui"
    os.environ["DATABASE_URL"] = database_url
    retries = 10
    while retries > 0:
        try:
            engine = create_engine(database_url, pool_pre_ping=True)
            conn = engine.connect()
            conn.close()
            break
        except Exception as e:
            log.warning(e)
            time.sleep(3)
            retries -= 1
    else:
        raise RuntimeError("postgres container never became ready")

    # Import AFTER DATABASE_URL is set so migrations run against the right DB.
    from main import app

    test_client = TestClient(app)
    test_client.__enter__()
    return test_client, client


@pytest.fixture(scope="session")
def _security_suite_context():
    test_client, docker_client = _spin_up_postgres_and_client()
    yield test_client
    try:
        docker_client.containers.get(_CONTAINER_NAME).remove(force=True)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _attach_client_and_truncate(request, _security_suite_context):
    cls = request.cls
    if cls is not None:
        cls.fast_api_client = _security_suite_context

    yield

    # Per-test cleanup: truncate every table the suite touches.
    from open_webui.internal.db import Session

    tables = [
        '"user"',
        "auth",
        "chat",
        "chatidtag",
        "document",
        "memory",
        "model",
        "prompt",
        "tag",
        '"agent"',
        '"registry_agent"',
    ]
    for table in tables:
        try:
            Session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception:
            Session.rollback()
    Session.commit()
