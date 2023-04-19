from .const import (
    DOMAIN, SERVENTS_CONFIG_SENSORS, SERVENTS_CONFIG_ENTS, SERVENT_DEVICE_ID, SERVENT_DEVICE_NAME, SERVENTS_CONFIG_BINARY_SENSORS,
    SERVENT_DEVICE_MANUFACTURER, SERVENT_DEVICE_VERSION, SERVENT_DEVICE_MODEL, SERVENT_DEVICE, SERVENTS_CONFIG_NUMBERS, SERVENTS_CONFIG_SWITCHES, SERVENTS_CONFIG_SELECTS
)
from homeassistant.util import yaml
from homeassistant.helpers.entity import DeviceInfo
import logging

_LOGGER = logging.getLogger(__name__)

servent_current_config = {}

default_config = {
    SERVENTS_CONFIG_ENTS: {
        SERVENTS_CONFIG_SENSORS: {},
        SERVENTS_CONFIG_BINARY_SENSORS: {},
        SERVENTS_CONFIG_NUMBERS: {},
        SERVENTS_CONFIG_SWITCHES: {},
        SERVENTS_CONFIG_SELECTS: {}
    }
}


def stripNone(data):
    if isinstance(data, dict):
        return {k: stripNone(v) for k, v in data.items() if k is not None and v is not None}
    elif isinstance(data, list):
        return [stripNone(item) for item in data if item is not None]
    elif isinstance(data, tuple):
        return tuple(stripNone(item) for item in data if item is not None)
    elif isinstance(data, set):
        return {stripNone(item) for item in data if item is not None}
    else:
        return data


def get_ent_config(type):
    global servent_current_config
    config = servent_current_config[SERVENTS_CONFIG_ENTS].get(type)
    if config is None:
        servent_current_config[SERVENTS_CONFIG_ENTS][type] = {}
        config = servent_current_config[SERVENTS_CONFIG_ENTS][type]

    return config


def get_all_device_ids():
    all_ids = []
    for value in servent_current_config[SERVENTS_CONFIG_ENTS].values():
        for conf in value.values():
            if SERVENT_DEVICE in conf:
                all_ids.append(
                    f"device-{conf[SERVENT_DEVICE][SERVENT_DEVICE_ID]}")
    return [*set(all_ids)]


def save_config_to_file():
    global servent_current_config
    yaml.save_yaml("servents.yaml", default_config | servent_current_config)


def load_config_from_file():
    global servent_current_config
    config_from_file = {}
    try:
        config_from_file = yaml.load_yaml(
            "servents.yaml")
    except FileNotFoundError:
        save_config_to_file()

    servent_current_config = default_config | stripNone(
        (config_from_file or {}))


servent_hass_obj = None


def store_hass_object(hass):
    global servent_hass_obj
    servent_hass_obj = hass


def get_hass_object():
    global servent_hass_obj
    return servent_hass_obj


servent_live_entities = {}
servent_ids_with_platform = {}


def add_entity_to_cache(platform, servent_id, entity):
    global servent_live_entities
    global servent_ids_with_platform
    if platform not in servent_live_entities:
        servent_live_entities[platform] = {}

    servent_ids_with_platform[servent_id] = platform
    servent_live_entities[platform][servent_id] = entity


def get_platform_for_servent_id(servent_id):
    global servent_ids_with_platform
    return servent_ids_with_platform.get(servent_id)


def get_live_entities_from_cache(platform, servent_id):
    global servent_live_entities
    if platform not in servent_live_entities:
        servent_live_entities[platform] = {}

    return servent_live_entities[platform][servent_id] if servent_id in servent_live_entities[platform] else None


def create_device_info(device_config):
    return DeviceInfo(
        identifiers={
            (DOMAIN,
             f"device-{device_config[SERVENT_DEVICE_ID]}")
        },
        name=device_config[SERVENT_DEVICE_NAME],
        manufacturer=device_config.get(
            SERVENT_DEVICE_MANUFACTURER, "ServEnts"),
        model=device_config.get(SERVENT_DEVICE_MODEL, "Virtual Device"),
        sw_version=device_config.get(SERVENT_DEVICE_VERSION)
    ) if device_config is not None else None


def toEnum(type, value):
    if value is None:
        return None

    return type(value)
