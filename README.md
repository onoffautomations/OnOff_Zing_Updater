<p align="center">
  <img src="https://zingmusic.app/icons/Icon-192.png" alt="Zing Music" width="88" />
</p>

<h1 align="center">OnOff – Zing Updater</h1>

<p align="center">
  Installs and updates everything for <b>Zing Music in Home Assistant</b>:<br/>
  the Zing Music integration, the Zing Music card and the OnOff Licenser.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=onoffautomations&repository=OnOff_Zing_Updater&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open this repository in HACS." />
  </a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=onoff_zing_updater">
    <img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up OnOff - Zing Updater." />
  </a>
</p>

---

## What it does

- **One place for every Zing package.** Tick what you want; it downloads and installs each one to the right folder.
- **Automatic updates.** New versions show up in Home Assistant's **Settings → Updates**, with release notes, like any other update.
- **Stable or Beta.** Stay on stable releases, or switch to the beta channel to get new features first. You can switch any time.
- **The card just works.** The Zing card's dashboard resource is registered for you; no manual Lovelace resource step.
- **Restart prompts.** After an integration is installed or updated, a repair card asks you to restart Home Assistant.

> New to Zing Music in Home Assistant? Follow the full **[install guide](https://zing.onoffautomations.com/install/)**:
> it walks you through the license, signing in and adding the card, with screenshots.

## Install

### 1. Add the updater to HACS

Click **Open your Home Assistant instance and open a repository inside HACS** above and then **Download**.

<details>
<summary>Or add it by hand</summary>

1. Open **HACS** from the sidebar.
2. Click the **⋮** menu (top right) → **Custom repositories**.
3. Repository: `https://github.com/onoffautomations/OnOff_Zing_Updater`, type **Integration** → **Add**.
4. Search for **OnOff - Zing Updater**, open it and click **Download**.
</details>

Then **restart Home Assistant** (Settings → System → Restart).

### 2. Set it up

Click **Add integration to my Home Assistant** above, or go to **Settings → Devices & services → + Add integration** and search for **OnOff - Zing Updater**.

The first screen is all there is:

| Setting | What to choose |
|---|---|
| **Release channel** | **Stable** for normal releases (recommended), or **Beta** for the newest features first. |
| **Packages** | Tick **OnOff Licenser**, **Zing Music** and the **Zing card**. |

Click **Submit**. The packages install in the background; when the **Restart required** repair appears (Settings → System → Repairs), click it to restart. After the restart, refresh your browser (**Ctrl+Shift+R** / **Cmd+Shift+R**) so the new card loads.

## Updating

- The updater checks for new versions every 2 hours.
- Updates appear under **Settings → Updates**. Click **Update**, and restart when asked if it's an integration.
- Each package also has an **Update** button and a **Check for updates** button on its device page.

## Changing the channel or adding packages

Go to **Settings → Devices & services → OnOff - Zing Updater → Configure**.

- **Release channel**: switch between Stable and Beta.
  - Stable → Beta: packages update to the newest beta right away (leave them ticked and Submit).
  - Beta → Stable: you keep the version you have and get the next stable release that is newer. Nothing is downgraded.
- **Packages**: tick more packages to install them. Packages you already have are ticked; leaving them ticked fetches the newest version for your channel.

## Entities

For every installed package, on its own device:

| Entity | Shows |
|---|---|
| `update.<package>_update` | Installed / latest version, release notes, Install button |
| `sensor.<package>_version` | The installed version |
| `sensor.<package>_update_available` | Yes / No |
| `sensor.<package>_waiting_restart` | Yes while a restart is still needed (integrations) |
| `button.<package>_update` | Install the newest version for your channel |
| `button.<package>_check_for_updates` | Check now |

## Services

| Service | Use |
|---|---|
| `onoff_zing_updater.check_updates` | Check every package for updates now. |
| `onoff_zing_updater.install` | Install a package: `owner`, `repo`, `type` (`integration` or `lovelace`), optional `tag` for a specific version. |

## Troubleshooting

<details>
<summary><b>A package doesn't install</b></summary>

Check **Settings → System → Logs** for `onoff_zing_updater`. Make sure Home Assistant can reach the internet, then try again with **Configure → Submit**.
</details>

<details>
<summary><b>No update shows up</b></summary>

Press the package's **Check for updates** button, or call `onoff_zing_updater.check_updates`. On the Stable channel, beta versions are never offered.
</details>

<details>
<summary><b>The integration doesn't load after an update</b></summary>

Home Assistant has to restart to load new integration code. Use the **Restart required** repair, or Settings → System → Restart.
</details>

<details>
<summary><b>The card still looks old</b></summary>

Refresh the browser without its cache (**Ctrl+Shift+R** / **Cmd+Shift+R**). On the Home Assistant app: Settings → Companion app → Debugging → Reset frontend cache.
</details>

## Support

Email **integrations@onoffautomations.com** with your name, a callback number and, for speaker problems, the speaker's make and model.

<p align="center"><sub>Made by <a href="https://onoffautomations.com">OnOff Automations</a></sub></p>
