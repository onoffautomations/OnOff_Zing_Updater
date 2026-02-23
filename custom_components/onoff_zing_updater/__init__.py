from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    SERVICE_CHECK_UPDATES,
    MODE_ZIPBALL,
    TYPE_INTEGRATION,
    TYPE_LOVELACE,
    TYPE_BLUEPRINTS,
)
from .gitea import GiteaClient
from .installer import download_and_install

_LOGGER = logging.getLogger(__name__)


def _get_datetime_timestamp() -> str:
    """Get current date and time as a timestamp string."""
    now = datetime.now()
    return now.strftime("%Y%m%d%H%M%S")


def _scan_custom_components_versions(hass: HomeAssistant) -> dict[str, str]:
    """Return installed custom_components domains mapped to their manifest versions."""
    cc_root = Path(hass.config.path("custom_components"))
    versions: dict[str, str] = {}
    if not cc_root.exists():
        return versions

    for domain_dir in cc_root.iterdir():
        if not domain_dir.is_dir():
            continue
        domain = domain_dir.name
        if domain.startswith("."):
            continue
        version = "unknown"
        manifest_path = domain_dir / "manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                version = data.get("version") or version
                manifest_domain = (data.get("domain") or "").strip()
                if manifest_domain and manifest_domain.lower() != domain.lower():
                    versions.setdefault(manifest_domain.lower(), version)
            except Exception as e:
                _LOGGER.debug("Failed to read manifest for %s: %s", domain, e)
        versions[domain.lower()] = version

    return versions


def _load_hacs_integrations(hass: HomeAssistant) -> set[str]:
    """Return a set of installed HACS integration domains."""
    hacs_path = Path(hass.config.path(".storage", "hacs"))
    if not hacs_path.exists():
        return set()

    try:
        raw = json.loads(hacs_path.read_text(encoding="utf-8"))
    except Exception as e:
        _LOGGER.debug("Failed to read HACS storage: %s", e)
        return set()

    data = raw.get("data", raw)
    repos = data.get("repositories", [])
    domains: set[str] = set()

    for repo in repos:
        try:
            category = repo.get("category") or repo.get("data", {}).get("category")
            installed = repo.get("installed")
            if installed is None:
                installed = repo.get("data", {}).get("installed")
            if category != "integration" or not installed:
                continue
            domain = repo.get("domain") or repo.get("data", {}).get("domain")
            if isinstance(domain, str) and domain:
                domains.add(domain.lower())
            else:
                domains_list = repo.get("domains") or repo.get("data", {}).get("domains") or []
                for d in domains_list:
                    if isinstance(d, str) and d:
                        domains.add(d.lower())
        except Exception:
            continue

    return domains


async def _sync_preinstalled_integrations(
    hass: HomeAssistant,
    coordinator,
    entry: ConfigEntry,
) -> None:
    """Track custom_components integrations as installed when they already exist on disk."""
    installed = await hass.async_add_executor_job(_scan_custom_components_versions, hass)
    if not installed:
        return

    hacs_domains = await hass.async_add_executor_job(_load_hacs_integrations, hass)
    from .config_flow import load_store_list

    default_owner: str | None = (entry.data.get("owner") or "").strip() or None
    store_packages = await hass.async_add_executor_job(load_store_list, hass)

    to_track: list[tuple[str, str, str, str | None, str | None, str]] = []

    def _match_installed_domain(repo: str, pkg_domain: str | None = None) -> str | None:
        candidates = []
        if pkg_domain:
            candidates.append(pkg_domain)
        candidates.append(repo)
        candidates.append(repo.replace("-", "_"))
        for cand in candidates:
            key = (cand or "").strip().lower()
            if key and key in installed:
                return key
        return None

    for pkg in store_packages:
        repo = (pkg.get("repo") or "").strip()
        if not repo:
            continue
        if pkg.get("type", TYPE_INTEGRATION) != TYPE_INTEGRATION:
            continue
        match_domain = _match_installed_domain(repo, pkg.get("domain"))
        if not match_domain:
            continue
        owner = (pkg.get("owner") or default_owner or "").strip()
        if not owner:
            continue
        if coordinator.get_package_by_repo(owner, repo) is not None:
            continue
        source = "hacs" if match_domain in hacs_domains else pkg.get("source", "gitea")
        to_track.append(
            (
                owner,
                repo,
                installed.get(match_domain, "unknown"),
                pkg.get("mode"),
                pkg.get("asset_name"),
                source,
            )
        )

    if not to_track:
        return

    _LOGGER.info("Tracking %d pre-installed custom_components integrations", len(to_track))
    for owner, repo, version, mode, asset_name, source in to_track:
        await coordinator.async_add_or_update_package(
            repo_name=repo,
            owner=owner,
            package_type=TYPE_INTEGRATION,
            installed_version=version,
            mode=mode,
            asset_name=asset_name,
            source=source,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    base_url: str = entry.data["base_url"].rstrip("/")
    default_owner: str = (entry.data.get("owner") or "").strip() or None

    # Store HA start time (for tracking restart requirements)
    if 'homeassistant_start_time' not in hass.data:
        hass.data['homeassistant_start_time'] = datetime.now()
        _LOGGER.info("Recorded HA start time: %s", hass.data['homeassistant_start_time'])

    client = GiteaClient(hass, base_url=base_url)

    # Import coordinator
    from .coordinator import OnOffGiteaStoreCoordinator

    # Create coordinator for package tracking
    coordinator = OnOffGiteaStoreCoordinator(hass, entry.entry_id, client)
    await coordinator.async_load_packages()

    # Build headers
    headers = {"Accept": "application/json"}

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "default_owner": default_owner,
        "headers": headers,
        "coordinator": coordinator,
    }

    # Track already-installed custom_components integrations as if installed by the store
    await _sync_preinstalled_integrations(hass, coordinator, entry)

    # Check for updates on startup
    await coordinator.async_check_updates()

    # Load sensor, button, and update platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button", "update"])

    # Handle pending installations from initial setup or reconfigure
    pending_installs = entry.data.get("pending_installs", [])
    if pending_installs:
        _LOGGER.info("Found %d pending packages to install", len(pending_installs))

        async def _install_pending_packages():
            """Install packages that were selected during setup/reconfigure."""
            try:
                from .config_flow import load_store_list

                packages = await hass.async_add_executor_job(load_store_list, hass)
                installed_integrations = []

                for key in pending_installs:
                    pkg = None
                    for p in packages:
                        pkg_key = f"{p.get('owner', '')}_{p.get('repo', '')}"
                        if pkg_key == key:
                            pkg = p
                            break

                    if not pkg:
                        _LOGGER.error("Package not found for key: %s", key)
                        continue

                    repo = pkg.get("repo")
                    owner = pkg.get("owner", default_owner)
                    pkg_type = pkg.get("type", "integration")
                    mode = pkg.get("mode") or MODE_ZIPBALL
                    asset_name = pkg.get("asset_name")

                    if not repo or not owner:
                        _LOGGER.error("Invalid package data: %s", pkg)
                        continue

                    _LOGGER.info("Installing package: %s/%s (type: %s)", owner, repo, pkg_type)

                    try:
                        # Resolve download URL
                        url, version = await _resolve_download_url(client, owner, repo, mode, None, asset_name, None)

                        result = await download_and_install(
                            hass,
                            url=url,
                            headers={},
                            package_type=pkg_type,
                            repo_name=repo,
                        )

                        # Register package with coordinator
                        await coordinator.async_add_or_update_package(
                            repo_name=repo,
                            owner=owner,
                            package_type=pkg_type,
                            installed_version=version,
                            mode=mode,
                            asset_name=asset_name,
                            source=pkg.get("source", "gitea"),
                        )

                        _LOGGER.info("Installed: %s/%s", owner, repo)

                        # Track installed integrations for restart notification
                        if pkg_type == "integration":
                            installed_integrations.append(repo)

                    except Exception as e:
                        _LOGGER.error("Failed to install %s/%s: %s", owner, repo, e, exc_info=True)

                # Create fixable restart repair issue for each installed integration
                if installed_integrations:
                    try:
                        from homeassistant.helpers import issue_registry as ir
                        for repo in installed_integrations:
                            ir.async_create_issue(
                                hass,
                                domain=DOMAIN,
                                issue_id=f"onoff_restart_{repo}_{_get_datetime_timestamp()}",
                                is_fixable=True,
                                severity=ir.IssueSeverity.WARNING,
                                translation_key="integration_restart_required",
                                translation_placeholders={"integration_name": repo},
                                data={"integration_name": repo},
                            )
                        _LOGGER.info("Created restart repair issues for %d integrations", len(installed_integrations))
                    except Exception as e:
                        _LOGGER.warning("Could not create restart notification: %s", e)

                # Clear pending installs from entry data
                new_data = dict(entry.data)
                new_data.pop("pending_installs", None)
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info("Cleared pending installations from entry data")

            except Exception as e:
                _LOGGER.error("Failed to install pending packages: %s", e, exc_info=True)

        hass.async_create_task(_install_pending_packages())

    async def _handle_check_updates(call: ServiceCall) -> None:
        """Handle check_updates service call."""
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        await coordinator.async_check_updates()

    hass.services.async_register(DOMAIN, SERVICE_CHECK_UPDATES, _handle_check_updates)

    return True


async def _resolve_download_url(client, owner: str, repo: str, mode: str, tag: str | None, asset_name: str | None, source: str | None) -> tuple[str, str]:
    """Resolve download URL for a package."""
    if source == "github":
        ref = tag or "main"
        url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}" if tag else f"https://api.github.com/repos/{owner}/{repo}/zipball"
        return url, ref

    # Try zipball first
    try:
        ref = await _resolve_ref_for_zipball(client, owner, repo, tag)
        return client.archive_zip_url(owner, repo, ref), ref
    except Exception as e:
        _LOGGER.debug("Zipball method failed for %s/%s, trying Release Asset: %s", owner, repo, e)

    # Try asset mode as fallback
    try:
        resolved_tag = await _resolve_tag_for_asset(client, owner, repo, tag)
        release = await client.get_release_by_tag(owner, repo, resolved_tag)
        asset = client.pick_asset(release, asset_name=asset_name)
        return asset["browser_download_url"], resolved_tag
    except Exception as final_err:
        _LOGGER.error("Both installation modes failed for %s/%s.", owner, repo)
        raise final_err


async def _resolve_ref_for_zipball(client, owner: str, repo: str, tag: str | None) -> str:
    if tag:
        return tag
    latest = await client.get_latest_release(owner, repo)
    if latest:
        ref = latest.get("tag_name") or latest.get("name")
        if ref:
            return ref
    repo_info = await client.get_repo(owner, repo)
    branch = repo_info.get("default_branch") or "main"
    return branch


async def _resolve_tag_for_asset(client, owner: str, repo: str, tag: str | None) -> str:
    if tag:
        return tag
    latest = await client.get_latest_release(owner, repo)
    if not latest:
        raise RuntimeError("No releases found.")
    resolved = latest.get("tag_name") or latest.get("name")
    if not resolved:
        raise RuntimeError("Could not determine latest release tag.")
    return resolved


async def async_install_package(
    hass: HomeAssistant,
    entry_id: str,
    owner: str,
    repo: str,
    pkg_type: str,
    mode: str = None,
    asset_name: str = None,
    tag: str = None,
    source: str = None,
) -> None:
    """Install or update a package. Called by buttons and update entities."""
    data = hass.data[DOMAIN].get(entry_id)
    if not data:
        raise ValueError("Integration not loaded")

    client = data["client"]
    coordinator = data["coordinator"]

    mode = mode or MODE_ZIPBALL

    url, version = await _resolve_download_url(client, owner, repo, mode, tag, asset_name, source)

    result = await download_and_install(
        hass,
        url=url,
        headers={},
        package_type=pkg_type,
        repo_name=repo,
    )

    # Create repair issue for integration installs
    if pkg_type == TYPE_INTEGRATION:
        try:
            from homeassistant.helpers import issue_registry as ir
            ir.async_create_issue(
                hass,
                domain=DOMAIN,
                issue_id=f"onoff_restart_{repo}_{_get_datetime_timestamp()}",
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="integration_restart_required",
                translation_placeholders={"integration_name": repo},
                data={"integration_name": repo},
            )
        except Exception as e:
            _LOGGER.debug("Could not create repair issue: %s", e)

    await coordinator.async_add_or_update_package(
        repo_name=repo,
        owner=owner,
        package_type=pkg_type,
        installed_version=version,
        mode=mode,
        asset_name=asset_name,
        source=source or "gitea",
    )

    _LOGGER.info("Package %s/%s installed/updated to %s", owner, repo, version)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button", "update"])

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
