"""Config flow for OnOff - Zing Updater.

This integration intentionally has NO token support and NO side panel.
The only repos exposed are:
  - everything in the Zing org on the internal Gitea, except names that
    start with "x-" (case-insensitive)
  - OnOffPublic/OnOff-Licenser

At install time the user picks which of these to install. The same
package picker is reachable later via the integration's Configure /
Reconfigure button so more packages can be installed without removing
and re-adding the integration.
"""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    LICENSER_OWNER,
    LICENSER_REPO,
    TYPE_BLUEPRINTS,
    TYPE_INTEGRATION,
    TYPE_LOVELACE,
    ZING_ORG,
)
from .gitea import GiteaClient
from ._utils import get_primary_endpoint

_LOGGER = logging.getLogger(__name__)


def load_store_list(hass: HomeAssistant) -> list[dict]:
    """Compatibility shim for code that imports load_store_list.

    The yidstore lineage uses a YAML store list; for Zing Updater the
    real list is fetched live from Gitea (see _fetch_available_packages),
    so this returns an empty list. The install service and
    _sync_preinstalled_integrations still call it but tolerate an empty
    response.
    """
    return []


async def _detect_repo_type(client: GiteaClient, owner: str, repo: str, branch: str = "main") -> str:
    """Inspect a repo's root layout to decide what kind of package it is.

    custom_components/ → integration
    blueprints/        → blueprints
    .js at root        → lovelace (card)
    anything else      → integration (default)
    """
    try:
        entries = await client.list_dir(owner, repo, path="", branch=branch)
    except Exception:
        entries = None

    if not isinstance(entries, list):
        return TYPE_INTEGRATION

    has_custom_components = False
    has_blueprints = False
    has_root_js = False
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").lower()
        kind = e.get("type")
        if kind == "dir" and name == "custom_components":
            has_custom_components = True
        elif kind == "dir" and name == "blueprints":
            has_blueprints = True
        elif kind == "file" and name.endswith(".js"):
            has_root_js = True

    if has_custom_components:
        return TYPE_INTEGRATION
    if has_blueprints:
        return TYPE_BLUEPRINTS
    if has_root_js:
        return TYPE_LOVELACE
    return TYPE_INTEGRATION


async def _fetch_available_packages(hass: HomeAssistant) -> list[dict]:
    """Return the list of installable packages from Gitea, with type detected.

    Zing org (excluding repos whose name starts with "x-") + OnOff-Licenser.
    Anonymous Gitea access — no token.
    """
    base_url = get_primary_endpoint()
    client = GiteaClient(hass, base_url=base_url, token=None)

    # First gather raw repo metadata.
    raw: list[dict] = []

    try:
        zing_repos = await client.get_org_repos(ZING_ORG)
    except Exception as e:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to fetch Zing repos: %s", e)
        zing_repos = []

    for repo in zing_repos or []:
        if not isinstance(repo, dict):
            continue
        name = (repo.get("name") or "").strip()
        if not name:
            continue
        if name.lower().startswith("x-"):
            continue
        if repo.get("archived"):
            continue
        owner = (repo.get("owner") or {}).get("login") or ZING_ORG
        raw.append({
            "owner": owner,
            "repo": name,
            "description": repo.get("description") or "",
            "default_branch": repo.get("default_branch") or "main",
        })

    # OnOff-Licenser — always include, fetched individually so it's
    # robust to API changes that affect org listings.
    try:
        licenser = await client.get_repo(LICENSER_OWNER, LICENSER_REPO)
    except Exception as e:
        _LOGGER.debug("Could not fetch licenser repo metadata: %s", e)
        licenser = None

    if isinstance(licenser, dict) and not licenser.get("archived"):
        raw.append({
            "owner": (licenser.get("owner") or {}).get("login") or LICENSER_OWNER,
            "repo": licenser.get("name") or LICENSER_REPO,
            "description": licenser.get("description") or "",
            "default_branch": licenser.get("default_branch") or "main",
        })
    else:
        raw.append({
            "owner": LICENSER_OWNER,
            "repo": LICENSER_REPO,
            "description": "",
            "default_branch": "main",
        })

    # Detect each repo's actual type in parallel — without this the
    # Lovelace cards in the Zing org install to the wrong place (and
    # appear to "not install").
    type_results = await asyncio.gather(
        *[_detect_repo_type(client, p["owner"], p["repo"], p["default_branch"]) for p in raw],
        return_exceptions=True,
    )

    packages: list[dict] = []
    for pkg, tpe in zip(raw, type_results):
        resolved_type = tpe if isinstance(tpe, str) else TYPE_INTEGRATION
        packages.append({
            "owner": pkg["owner"],
            "repo": pkg["repo"],
            "type": resolved_type,
            "description": pkg["description"],
            "default_branch": pkg["default_branch"],
        })

    # Stable sort: owner, then repo name.
    packages.sort(key=lambda p: (p["owner"].lower(), p["repo"].lower()))
    return packages


def _package_options(packages: list[dict]) -> dict[str, str]:
    """Build the multi-select options map used by the form."""
    type_label = {
        TYPE_INTEGRATION: "Integration",
        TYPE_LOVELACE: "Card",
        TYPE_BLUEPRINTS: "Blueprint",
    }
    out: dict[str, str] = {}
    for pkg in packages:
        key = f"{pkg.get('owner', '')}_{pkg.get('repo', '')}"
        tag = type_label.get(pkg.get("type"), pkg.get("type") or "")
        label = f"[{tag}] {pkg.get('owner')}/{pkg.get('repo')}" if tag else f"{pkg.get('owner')}/{pkg.get('repo')}"
        desc = pkg.get("description")
        if desc:
            label = f"{label} — {desc}"
        out[key] = label
    return out


def _already_tracked_keys(hass, entry) -> set[str]:
    """Return selection keys for packages already tracked by this entry."""
    keys: set[str] = set()
    try:
        runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        coordinator = runtime.get("coordinator") if runtime else None
        if coordinator:
            for pkg in coordinator.packages.values():
                key = f"{pkg.get('owner', '')}_{pkg.get('repo_name', '')}"
                keys.add(key)
    except Exception:
        pass
    return keys


class OnOffZingUpdaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for OnOff - Zing Updater."""

    VERSION = 1

    def __init__(self) -> None:
        self.config_data: dict = {}
        self._packages: list[dict] = []

    async def async_step_user(self, user_input=None):
        """Show the package picker as the very first screen.

        We used to have an empty intro step before this one — that made
        it look like nothing was happening since there were no fields.
        Now the user lands directly on the picker.
        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if not self._packages:
            self._packages = await _fetch_available_packages(self.hass)

        if user_input is not None:
            selected = user_input.get("packages", []) or []
            keymap = {f"{p['owner']}_{p['repo']}": p for p in self._packages}
            pending = [key for key in selected if key in keymap]

            return self.async_create_entry(
                title="OnOff - Zing Updater",
                data={
                    "base_url": get_primary_endpoint(),
                    "token": "",
                    "owner": "",
                    "pending_installs": pending,
                    "available_packages": self._packages,
                },
            )

        options = _package_options(self._packages)
        if not options:
            return self.async_abort(reason="no_packages")

        schema = vol.Schema(
            {
                vol.Optional("packages", default=[]): cv.multi_select(options),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure entry — re-open the package picker.

        For this integration "reconfigure" just means: pick more packages
        to install. There are no other settings.
        """
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if not entry:
            return self.async_abort(reason="cannot_reconfigure")

        if not self._packages:
            self._packages = await _fetch_available_packages(self.hass)

        if user_input is not None:
            selected = user_input.get("packages", []) or []
            new_data = dict(entry.data)
            new_data["pending_installs"] = selected
            new_data["available_packages"] = self._packages
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        options = _package_options(self._packages)
        if not options:
            return self.async_abort(reason="no_packages")

        already_tracked = _already_tracked_keys(self.hass, entry)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional("packages", default=list(already_tracked)): cv.multi_select(options),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow — install more packages later."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        packages = await _fetch_available_packages(self.hass)

        if user_input is not None:
            selected = user_input.get("packages", []) or []
            new_data = dict(entry.data)
            new_data["pending_installs"] = selected
            new_data["available_packages"] = packages
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_create_entry(title="", data={})

        options = _package_options(packages)
        if not options:
            return self.async_abort(reason="no_packages_in_store")

        already_tracked = _already_tracked_keys(self.hass, entry)
        schema = vol.Schema(
            {
                vol.Optional("packages", default=list(already_tracked)): cv.multi_select(options),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
