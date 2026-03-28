"""Constants used throughout QGarage."""

# File names
APP_META_FILENAME = "app_meta.json"
REQUIREMENTS_FILENAME = "requirements.txt"
VENV_DIR = ".venv"
DEFAULT_ENTRY_POINT = "main.py"
DEFAULT_CLASS_NAME = "App"

# Module naming
APP_MODULE_TEMPLATE = "qgarage.apps.{app_id}.main"

# Theme
DARK_THEME_FILE = "dark.qss"
LIGHT_THEME_FILE = "light.qss"
DARK_THEME_LUMINANCE_THRESHOLD = 128

# Encoding
DEFAULT_ENCODING = "utf-8"

# UI Object Names
OBJECT_NAME_DASHBOARD = "qgarageDashboard"
OBJECT_NAME_TOOLBAR = "qgarageToolbar"
OBJECT_NAME_SEARCH_BAR = "qgarageSearchBar"
OBJECT_NAME_INSTALL_BUTTON = "qgarageInstallButton"
OBJECT_NAME_NEW_APP_BUTTON = "qgarageNewAppButton"
OBJECT_NAME_CARD_AREA = "qgarageCardArea"
OBJECT_NAME_BACK_BUTTON = "qgarageBackButton"

# Card object names
OBJECT_NAME_CARD_TITLE = "appCardTitle"
OBJECT_NAME_CARD_DESC = "appCardDescription"
OBJECT_NAME_STATE_BADGE = "appStateBadge"
OBJECT_NAME_CARD_RUN_BUTTON = "appCardRunButton"

# App host object names
OBJECT_NAME_APP_HEADER = "appHeader"
OBJECT_NAME_APP_DESC = "appDescription"
OBJECT_NAME_APP_RUN_BUTTON = "appRunButton"
OBJECT_NAME_APP_OUTPUT = "appOutputArea"

# UI Margins
TOOLBAR_MARGINS = (8, 8, 8, 8)
CONTENT_MARGINS = (12, 12, 12, 12)
CONTAINER_MARGINS = (0, 0, 0, 0)
CARD_MARGINS = (12, 10, 12, 10)
DEFAULT_SPACING = 8

# Settings keys
SETTING_UV_EXECUTABLE = "uv_executable"
DEFAULT_UV_EXECUTABLE = "uv"
