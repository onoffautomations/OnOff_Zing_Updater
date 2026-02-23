# OnOff Zing Updater

A Home Assistant custom integration for managing and updating custom integrations and Lovelace cards from the OnOff store.

## Features

- Install integrations and Lovelace cards from the OnOff store
- Automatic update checking for installed packages
- One-click updates with restart prompts
- Uninstall packages directly from the UI
- Track installed versions and update availability

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on the three dots in the top right corner
3. Select **Custom repositories**
4. Add the repository URL:
   ```
   https://github.com/onoffautomations/OnOff_Zing_Updater
   ```
5. Select **Integration** as the category
6. Click **Add**
7. Search for "OnOff Zing Updater" in HACS
8. Click **Download**
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/onoffautomations/OnOff_Zing_Updater)
2. Copy the `yidstore` folder to your `custom_components` directory
3. Restart Home Assistant

## Setup

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**
3. Search for "OnOff Zing Updater"
4. Select packages to install from the available list
5. Click **Submit**
6. If you installed any integrations, restart Home Assistant when prompted

## Usage

### Installing Packages

1. Go to **Settings** > **Devices & Services**
2. Find **OnOff Zing Updater** and click **Configure**
3. Select packages from the **Install Packages** list
4. Click **Submit**
5. The integration will download and install the selected packages
6. For integrations, a repair issue will prompt you to restart Home Assistant

### Uninstalling Packages

1. Go to **Settings** > **Devices & Services**
2. Find **OnOff Zing Updater** and click **Configure**
3. Select packages from the **Uninstall Packages** list
4. Click **Submit**
5. The selected packages will be removed

### Updating Packages

Updates are checked automatically. When an update is available:

- The package's **Update Available** sensor will show "Yes"
- You can update via:
  - The **Update** entity in Home Assistant's update dashboard
  - The package's **Update** button entity
- After updating an integration, a repair issue will prompt you to restart

### Entities

For each installed package, the following entities are created:

| Entity | Description |
|--------|-------------|
| Version Sensor | Shows the currently installed version |
| Update Available Sensor | Shows "Yes" or "No" for update availability |
| Type Sensor | Shows the package type (Integration/Lovelace) |
| Waiting Restart Sensor | Shows if a restart is needed (integrations only) |
| Update Button | Triggers an update for the package |
| Check for Updates Button | Manually checks for updates |
| Update Entity | Native Home Assistant update entity |

## Available Packages

The integration comes with a pre-configured list of packages from the OnOff store, including:

- **Integrations**: OnOff Support Agent, OnOff Licenser, Zing Music, Kasa Cloud, WTime, CloudFlare DDNS Updater
- **Lovelace Cards**: Zing Card, OnOff Health Report Card, OnOff Create Ticket Card

## Troubleshooting

### Package not installing
- Check the Home Assistant logs for error messages
- Ensure you have internet connectivity
- Verify the package repository is accessible

### Update not showing
- Click the "Check for Updates" button to manually refresh
- Updates are checked automatically every hour

### Integration not loading after install
- Restart Home Assistant
- Check the logs for any dependency issues

## Support

For issues and feature requests, please visit the [GitHub Issues](https://github.com/onoffautomations/OnOff_Zing_Updater/issues) page.

## License

This project is licensed under the MIT License.
