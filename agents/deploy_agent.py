#!/usr/bin/env python3
"""Universal A2A Agent Deployment Script for Cloud Run.

Two entry points:

* ``deploy_agent_to_cloud_run(...)`` — importable helper used by the
  hub backend's ``utils/cloud_run.py`` to provision a per-agent Cloud
  Run service when an admin clicks "Deploy" in the UI.
* ``main()`` — the original CLI for deploying ADK agents from the
  ``agents/`` directory by name.

Both share the same gcloud command construction so the behaviour stays
in one place.

Usage (CLI):
    python deploy_agent.py <agent-name> [options]

Examples:
    python deploy_agent.py oregon-state-expert
    python deploy_agent.py Cyrano-de-Bergerac --project my-project
    python deploy_agent.py oregon-state-expert --region us-central1
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional


class CloudRunDeployError(RuntimeError):
    """Raised when a Cloud Run deployment fails for any reason."""


def _use_shell() -> bool:
    return sys.platform.startswith("win")


def get_gcloud_config(property_name: str) -> Optional[str]:
    """Read a property from ``gcloud config``."""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", property_name],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=_use_shell(),
        )
        value = result.stdout.strip()
        if value and value != "(unset)":
            return value
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def get_project_number(project_id: str) -> Optional[str]:
    """Resolve the numeric project number for ``project_id``."""
    try:
        result = subprocess.run(
            [
                "gcloud",
                "projects",
                "describe",
                project_id,
                "--format=value(projectNumber)",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=_use_shell(),
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def deploy_agent_to_cloud_run(
    service_name: str,
    source_dir: Path,
    env_vars: Mapping[str, str],
    *,
    project: Optional[str] = None,
    region: Optional[str] = None,
    memory: str = "1Gi",
    allow_unauthenticated: bool = True,
    secret_refs: Optional[Mapping[str, str]] = None,
    extra_set_env_vars: Optional[Iterable[str]] = None,
) -> str:
    """Deploy a Cloud Run service from ``source_dir`` and return its URL.

    ``service_name`` is used both as the Cloud Run service name and as
    the basis for the predicted URL. ``env_vars`` are passed to
    ``--set-env-vars`` and must not contain secrets — bind those via
    ``secret_refs`` (mapping of env-var name -> ``secret-id:version``)
    so they're routed through Secret Manager and don't appear in the
    revision metadata.

    Raises ``CloudRunDeployError`` on any failure, including when
    gcloud is not on PATH.
    """
    project = project or get_gcloud_config("project")
    if not project:
        raise CloudRunDeployError(
            "No GCP project specified and could not detect one from gcloud config. "
            "Run `gcloud config set project YOUR-PROJECT-ID` or pass project= explicitly."
        )

    region = region or get_gcloud_config("compute/region") or "us-west1"

    project_number = get_project_number(project)
    if project_number:
        app_url = f"https://{service_name}-{project_number}.{region}.run.app"
    else:
        app_url = f"https://{service_name}.{region}.run.app"

    if not source_dir.exists():
        raise CloudRunDeployError(f"Agent source directory not found: {source_dir}")

    set_env_pairs = [f"{k}={v}" for k, v in env_vars.items()]
    set_env_pairs.append(f"APP_URL={app_url}")
    set_env_pairs.append(f"HOST_OVERRIDE={app_url}")
    if extra_set_env_vars:
        set_env_pairs.extend(extra_set_env_vars)

    deploy_cmd = [
        "gcloud",
        "run",
        "deploy",
        service_name,
        "--port=8080",
        f"--source={source_dir}",
        f"--region={region}",
        f"--project={project}",
        f"--memory={memory}",
        f"--set-env-vars={','.join(set_env_pairs)}",
    ]

    if secret_refs:
        secret_pairs = ",".join(f"{k}={v}" for k, v in secret_refs.items())
        deploy_cmd.append(f"--update-secrets={secret_pairs}")

    if allow_unauthenticated:
        deploy_cmd.append("--allow-unauthenticated")
    else:
        deploy_cmd.append("--no-allow-unauthenticated")

    try:
        result = subprocess.run(
            deploy_cmd,
            shell=_use_shell(),
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise CloudRunDeployError(
            "gcloud is not installed or not on PATH on the hub host."
        ) from exc

    if result.returncode != 0:
        raise CloudRunDeployError(
            f"gcloud run deploy failed for service '{service_name}' (exit {result.returncode})."
        )

    return app_url


def main():
    parser = argparse.ArgumentParser(
        description="Deploy an A2A agent to Google Cloud Run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s oregon-state-expert
  %(prog)s Cyrano-de-Bergerac --project my-project
  %(prog)s oregon-state-expert --region us-central1
        """,
    )

    parser.add_argument("agent_name", help="Name of the agent directory to deploy")
    parser.add_argument("--project", help="GCP project ID (default: from gcloud config)")
    parser.add_argument(
        "--region", help="GCP region (default: from gcloud config or us-west1)"
    )
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Make the service public (default: requires authentication)",
    )
    parser.add_argument("--memory", default="1Gi", help="Memory allocation (default: 1Gi)")

    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()
    agent_dir = script_dir / args.agent_name

    if not agent_dir.exists():
        available = [
            d.name
            for d in script_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        print(f"\n✗ Error: Agent directory not found: {agent_dir}")
        print(f"   Available agents: {', '.join(available)}")
        sys.exit(1)

    project = args.project or get_gcloud_config("project")
    if not project:
        print("\n✗ Error: No GCP project specified and could not detect from gcloud config.")
        print("   Please either:")
        print("   1. Set default project: gcloud config set project YOUR-PROJECT-ID")
        print("   2. Use --project flag: python deploy_agent.py <agent> --project YOUR-PROJECT-ID")
        sys.exit(1)

    region = args.region or get_gcloud_config("compute/region") or "us-west1"

    print(f"\n{'='*70}")
    print("A2A Agent Cloud Run Deployment")
    print(f"{'='*70}")
    print(f"Agent:          {args.agent_name}")
    print(f"Project:        {project}")
    print(f"Region:         {region}")
    print(f"Memory:         {args.memory}")
    print(f"Authentication: {'Public' if args.allow_unauthenticated else 'IAM Required'}")
    print(f"Source:         {agent_dir}")
    print(f"{'='*70}\n")

    env_vars = {
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_CLOUD_PROJECT": project,
        "GOOGLE_CLOUD_LOCATION": region,
    }

    try:
        url = deploy_agent_to_cloud_run(
            args.agent_name,
            agent_dir,
            env_vars,
            project=project,
            region=region,
            memory=args.memory,
            allow_unauthenticated=args.allow_unauthenticated,
        )
    except CloudRunDeployError as exc:
        print(f"\n{'='*70}")
        print("✗ Agent deployment FAILED")
        print(f"{'='*70}")
        print(f"\n{exc}")
        print("\nCommon issues:")
        print("  - Missing Dockerfile or requirements.txt in agent directory")
        print("  - Insufficient permissions")
        print("  - Invalid source code structure")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n✗ Deployment cancelled by user.")
        sys.exit(1)

    print(f"\n{'='*70}")
    print("✓ Agent deployment successful!")
    print(f"{'='*70}")
    print(f"\nYour A2A agent is now deployed to Cloud Run!")
    print(f"\n🌐 Service URL: {url}")
    print(f"\n📋 A2A Agent Card: {url}/.well-known/agent-card.json")
    print("\nTo test your agent:")
    print(f"  curl {url}/.well-known/agent-card.json")
    print("\nTo view logs:")
    print(
        f"  gcloud run services logs read {args.agent_name} --project={project} --region={region}"
    )


if __name__ == "__main__":
    main()
