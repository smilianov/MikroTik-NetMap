#!/usr/bin/env python3
"""
Ansible lookup plugin for Infisical secrets management.

Retrieves secrets from Infisical with proper timeout handling and error management.
Compatible with MikroTik-NetMap network discovery application.

Usage:
  {{ lookup('infisical', 'SECRET_NAME') }}
  {{ lookup('infisical', 'SECRET_NAME', environment='staging') }}
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import subprocess
import json
from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

DOCUMENTATION = """
    lookup: infisical
    author: MikroTik-NetMap Integration
    version_added: "1.0"
    short_description: Retrieve secrets from Infisical
    description:
        - This lookup returns secrets from Infisical secrets management platform
        - Uses infisical CLI with proper timeout and error handling
        - Supports environment-specific secret retrieval
    options:
        secret_name:
            description: Name of the secret to retrieve
            required: True
            type: str
        environment:
            description: Infisical environment (default: production)
            required: False
            type: str
            default: production
        project:
            description: Infisical project name (default: mikrotik-netmap)
            required: False
            type: str
            default: mikrotik-netmap
    notes:
        - Requires infisical CLI to be installed
        - Requires INFISICAL_TOKEN environment variable to be set
        - Uses 30-second timeout to prevent hanging operations
"""

EXAMPLES = """
# Retrieve a secret from default environment (production)
- name: Get router password
  debug:
    msg: "{{ lookup('infisical', 'ROUTER_PASS') }}"

# Retrieve a secret from specific environment
- name: Get staging credentials
  debug:
    msg: "{{ lookup('infisical', 'CORE_ROUTER_PASS', environment='staging') }}"

# Use in task with error handling
- name: Connect to RouterOS
  community.routeros.api_info:
    hostname: "{{ ansible_host }}"
    username: "{{ mt_api_user }}"
    password: "{{ lookup('infisical', 'MT_API_PASSWORD') }}"
    path: system identity
"""

RETURN = """
_raw:
    description: The secret value from Infisical
    type: str
    returned: success
"""


class LookupModule(LookupBase):
    """Infisical secrets lookup plugin."""

    def run(self, terms, variables=None, **kwargs):
        """Execute the lookup."""

        # Set default options
        self.set_options(var_options=variables, direct=kwargs)
        environment = self.get_option('environment', 'production')
        project = self.get_option('project', 'mikrotik-netmap')

        # Check prerequisites
        if not self._check_infisical_cli():
            raise AnsibleError("Infisical CLI not found. Install: curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | sudo -E bash && sudo apt-get install infisical")

        # Check for token
        infisical_token = os.getenv('INFISICAL_TOKEN')
        if not infisical_token:
            raise AnsibleError("INFISICAL_TOKEN environment variable not set")

        results = []

        for term in terms:
            secret_name = term.strip()
            if not secret_name:
                raise AnsibleError("Secret name cannot be empty")

            try:
                # Retrieve secret with timeout
                secret_value = self._get_secret(secret_name, environment, infisical_token)
                results.append(secret_value)

            except subprocess.TimeoutExpired:
                raise AnsibleError(f"Timeout retrieving secret '{secret_name}' from Infisical (30s limit)")
            except subprocess.CalledProcessError as e:
                raise AnsibleError(f"Failed to retrieve secret '{secret_name}': {e.stderr.decode()}")
            except Exception as e:
                raise AnsibleError(f"Unexpected error retrieving secret '{secret_name}': {str(e)}")

        return results

    def _check_infisical_cli(self):
        """Check if infisical CLI is available."""
        try:
            subprocess.run(['infisical', '--version'],
                          capture_output=True,
                          check=True,
                          timeout=10)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_secret(self, secret_name, environment, token):
        """Retrieve secret from Infisical with timeout."""

        # Build command
        cmd = [
            'infisical', 'secrets', 'get',
            secret_name,
            '--env', environment,
            '--plain'
        ]

        # Set up environment
        env = os.environ.copy()
        env['INFISICAL_TOKEN'] = token

        # Execute with 30-second timeout (required by Codex review)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True,
                env=env,
                timeout=30  # Critical: 30-second timeout to prevent hanging
            )

            # Return the secret value
            return result.stdout.strip()

        except subprocess.TimeoutExpired as e:
            # Re-raise timeout with context
            raise subprocess.TimeoutExpired(cmd, 30, output=e.output, stderr=e.stderr)
        except subprocess.CalledProcessError as e:
            # Enhanced error context
            error_msg = e.stderr.strip() if e.stderr else "Unknown error"
            if "not found" in error_msg.lower():
                raise AnsibleError(f"Secret '{secret_name}' not found in environment '{environment}'")
            elif "unauthorized" in error_msg.lower():
                raise AnsibleError(f"Unauthorized access to secret '{secret_name}' - check INFISICAL_TOKEN")
            else:
                raise e