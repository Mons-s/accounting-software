"""
App-level configuration: PostgreSQL URL, shop UUID, license key.

Stored in config.json alongside the app / executable.
Call load() once at startup — it configures db_connection automatically.
"""

import os
import sys
import uuid

import db_connection
from database import get_config, save_config

# Keys inside config.json
_K_PG_URL  = "pg_url"
_K_SHOP_ID = "shop_id"
_K_LICENSE = "license_key"


def load() -> dict:
    """
    Load config and wire up db_connection if PostgreSQL credentials exist.
    Returns the full config dict.
    """
    cfg = get_config()
    pg_url  = cfg.get(_K_PG_URL, "").strip()
    shop_id = cfg.get(_K_SHOP_ID, "").strip()

    if pg_url:
        if not shop_id:
            shop_id = str(uuid.uuid4())
            cfg[_K_SHOP_ID] = shop_id
            save_config(cfg)
        db_connection.configure(pg_url, shop_id)

    return cfg


def set_pg_credentials(pg_url: str, shop_id: str = "") -> str:
    """
    Persist the PostgreSQL URL (and optionally a shop UUID).
    Generates a new shop UUID when none is supplied.
    Returns the shop_id used.
    """
    if not shop_id:
        shop_id = str(uuid.uuid4())

    cfg = get_config()
    cfg[_K_PG_URL]  = pg_url.strip()
    cfg[_K_SHOP_ID] = shop_id
    save_config(cfg)

    db_connection.configure(pg_url.strip(), shop_id)
    return shop_id


def get_shop_id() -> str:
    return get_config().get(_K_SHOP_ID, "")


def get_pg_url() -> str:
    return get_config().get(_K_PG_URL, "")


def is_cloud_active() -> bool:
    """True when the app is successfully connected to Supabase."""
    return db_connection.is_cloud()
