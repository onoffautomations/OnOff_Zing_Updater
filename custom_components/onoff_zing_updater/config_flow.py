from __future__ import annotations

import logging
import os
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.util.yaml import load_yaml

from .const import DOMAIN, TYPE_INTEGRATION
from ._utils import get_primary_endpoint

_LOGGER = logging.getLogger(__name__)


def load_store_list(hass: HomeAssistant) -> list[dict]:
    """Load store list from YAML file."""
    try:
        integration_dir = os.path.dirname(__file__)
        store_list_path = os.path.join(integration_dir, "store_list.yaml")

        if not os.path.exists(store_list_path):
            _LOGGER.warning("Store list file not found: %s", store_list_path)
            return []

        data = load_yaml(store_list_path)
        packages = data.get('packages', []) if data else []
        packages = [p for p in packages if p and isinstance(p, dict)]

        _LOGGER.info("Loaded %d packages from store list", len(packages))
        return packages

    except Exception as e:
        _LOGGER.error("Failed to load store list: %s", e, exc_info=True)
        return []


class OnOffGiteaStoreConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self.config_data = {}

    async def async_step_user(self, user_input=None):
        """Handle initial configuration."""
        _LOGGER.debug("async_step_user called with input: %s", user_input)
        errors = {}

        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            base_url = get_primary_endpoint()

            try:
                _LOGGER.debug("Testing endpoint... %s", base_url)
            except Exception as e:
                _LOGGER.error("Cannot connect to endpoint %s: %s", base_url, e, exc_info=True)
                errors["base"] = "cannot_connect"

            if not errors:
                self.config_data = {
                    "base_url": base_url,
                    "owner": "",
                }
                return await self.async_step_store_selection()

        # Simple confirmation to proceed
        schema = vol.Schema({})

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_store_selection(self, user_input=None):
        """Show store list for package selection."""
        errors = {}

        if user_input is not None:
            selected = user_input.get("packages", [])
            self.config_data["pending_installs"] = selected
            return self.async_create_entry(
                title="OnOff Zing Updater",
                data=self.config_data,
            )

        return await self._show_store_form(errors)

    async def _show_store_form(self, errors=None):
        """Show the store selection form."""
        if errors is None:
            errors = {}

        try:
            packages = await self.hass.async_add_executor_job(load_store_list, self.hass)
        except Exception as e:
            _LOGGER.error("Failed to load store list: %s", e, exc_info=True)
            packages = []

        if not packages:
            _LOGGER.info("Store list is empty, finishing setup")
            return self.async_abort(reason="no_packages")

        package_options = {}
        for pkg in packages:
            try:
                name = pkg.get("name", "Unknown")
                pkg_type = pkg.get("type", "unknown")
                desc = pkg.get("description", "")
                label = f"{name} ({pkg_type})"
                if desc:
                    label = f"{label} - {desc}"
                key = f"{pkg.get('owner', '')}_{pkg.get('repo', '')}"
                package_options[key] = label
            except Exception as e:
                _LOGGER.warning("Skipping invalid package: %s", e)
                continue

        schema = vol.Schema(
            {
                vol.Optional("packages", default=[]): cv.multi_select(package_options),
            }
        )

        return self.async_show_form(
            step_id="store_selection",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration - show package selection and uninstall options."""
        _LOGGER.debug("async_step_reconfigure called with input: %s", user_input)

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if not entry:
            return self.async_abort(reason="cannot_reconfigure")

        # Get coordinator and installed packages
        coordinator = None
        if DOMAIN in self.hass.data and entry.entry_id in self.hass.data[DOMAIN]:
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")

        # Build installed packages map: key -> package_data
        installed_map = {}
        if coordinator:
            for pkg_id, pkg_data in coordinator.packages.items():
                key = f"{pkg_data.get('owner', '')}_{pkg_data.get('repo_name', '')}"
                installed_map[key] = pkg_data

        if user_input is not None:
            selected_install = user_input.get("packages_to_install", [])
            selected_uninstall = user_input.get("packages_to_uninstall", [])

            needs_reload = False
            config_data = dict(entry.data)

            # Handle uninstalls
            if selected_uninstall and coordinator:
                from .installer import uninstall_package

                for key in selected_uninstall:
                    pkg_data = installed_map.get(key)
                    if pkg_data:
                        repo_name = pkg_data.get("repo_name", "")
                        owner = pkg_data.get("owner", "")
                        pkg_type = pkg_data.get("package_type", "integration")

                        _LOGGER.info("Uninstalling package: %s/%s", owner, repo_name)

                        try:
                            # Uninstall files from disk
                            await self.hass.async_add_executor_job(
                                uninstall_package, self.hass, pkg_type, repo_name
                            )
                            # Remove from coordinator tracking
                            await coordinator.async_remove_package(owner, repo_name)
                            _LOGGER.info("Uninstalled: %s/%s", owner, repo_name)
                            needs_reload = True
                        except Exception as e:
                            _LOGGER.error("Failed to uninstall %s/%s: %s", owner, repo_name, e)

            # Handle installs - only packages that aren't already installed
            new_packages = [p for p in selected_install if p not in installed_map]
            if new_packages:
                config_data["pending_installs"] = new_packages
                self.hass.config_entries.async_update_entry(entry, data=config_data)
                needs_reload = True

            # Reload the integration if needed
            if needs_reload:
                await self.hass.config_entries.async_reload(entry.entry_id)

            return self.async_abort(reason="reconfigure_successful")

        # Show package selection form
        try:
            packages = await self.hass.async_add_executor_job(load_store_list, self.hass)
        except Exception as e:
            _LOGGER.error("Failed to load store list: %s", e, exc_info=True)
            packages = []

        if not packages and not installed_map:
            return self.async_abort(reason="no_packages")

        # Build options for packages to install (not yet installed)
        install_options = {}
        for pkg in packages:
            try:
                name = pkg.get("name", "Unknown")
                pkg_type = pkg.get("type", "unknown")
                desc = pkg.get("description", "")
                key = f"{pkg.get('owner', '')}_{pkg.get('repo', '')}"

                # Only show packages that aren't installed
                if key not in installed_map:
                    label = f"{name} ({pkg_type})"
                    if desc:
                        label = f"{label} - {desc}"
                    install_options[key] = label
            except Exception as e:
                _LOGGER.warning("Skipping invalid package: %s", e)
                continue

        # Build options for packages to uninstall (already installed)
        uninstall_options = {}
        for key, pkg_data in installed_map.items():
            repo_name = pkg_data.get("repo_name", "Unknown")
            pkg_type = pkg_data.get("package_type", "unknown")
            version = pkg_data.get("installed_version", "")
            label = f"{repo_name} ({pkg_type})"
            if version:
                label = f"{label} - v{version}"
            uninstall_options[key] = label

        # Build schema with both install and uninstall options
        schema_dict = {}
        if install_options:
            schema_dict[vol.Optional("packages_to_install", default=[])] = cv.multi_select(install_options)
        if uninstall_options:
            schema_dict[vol.Optional("packages_to_uninstall", default=[])] = cv.multi_select(uninstall_options)

        if not schema_dict:
            return self.async_abort(reason="no_packages")

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
        )
