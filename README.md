# ServEnts - Service Defined Entities

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

A Home Assistant custom integration that enables dynamic creation and management of entities via service calls. ServEnts allows external services and applications to programmatically create, update, and manage Home Assistant entities without modifying YAML files or the Home Assistant configuration directly.

## About

ServEnts is designed to work with [Domovoy](https://github.com/carlos-sarmiento/domovoy), a Python-based automation framework for Home Assistant. When paired together, you can create Home Assistant devices and entities directly from Python code, eliminating the need for manually configuring helpers in the HA UI.

### Supported Entity Types

- **Sensors** - Numeric or string values with optional units and device classes
- **Binary Sensors** - On/off state entities for monitoring conditions
- **Threshold Sensors** - Binary sensors that monitor other entities and trigger based on upper/lower bounds with hysteresis
- **Switches** - Controllable on/off entities with callbacks
- **Numbers** - Numeric inputs with min/max values and step sizes
- **Buttons** - Trigger custom events when pressed
- **Select** - Dropdown selection with predefined options

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Go to **HACS** in the sidebar
3. Click on **Integrations**
4. Click the three dots menu in the top right corner and select **Custom repositories**
5. Add the following repository URL:
   ```
   https://github.com/carlos-sarmiento/servents
   ```
6. Select **Integration** as the category
7. Click **Add**
8. Search for "ServEnts" in HACS and click **Download**
9. Restart Home Assistant
10. Go to **Settings** > **Devices & Services** > **Add Integration**
11. Search for "ServEnts" and add it

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/carlos-sarmiento/servents)
2. Copy the `custom_components/servents` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Go to **Settings** > **Devices & Services** > **Add Integration**
5. Search for "ServEnts" and add it

## Usage

ServEnts is designed to be used with Domovoy. For complete documentation on how to create and manage entities, please refer to the **[Domovoy Documentation](https://domovoy.readthedocs.io/)**.

Key resources:
- [Getting Started with Domovoy](https://domovoy.readthedocs.io/en/latest/getting-started/)
- [ServEnts Guide](https://domovoy.readthedocs.io/en/latest/guides/)
- [API Reference](https://domovoy.readthedocs.io/en/latest/api/)

## Requirements

- Home Assistant 2025.11.0 or newer

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](https://www.gnu.org/licenses/agpl-3.0.html).
