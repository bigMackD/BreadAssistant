"""Integration constants."""

DOMAIN = "bread_assistant"
DEFAULT_RECIPE = "justyna_basic_wheat_sourdough"
PLATFORMS = ["sensor", "button"]
DEFAULT_OPTIONS = {
    "notify_target": "",
    "notifications_enabled": True,
    "live_activities_enabled": False,
    "live_activity_notify_target": "",
    "reminder_minutes": 30,
    "dashboard_path": "/bread-assistant/overview",
    "time_format": "24h",
}
SERVICES = (
    "start_bake",
    "complete_step",
    "snooze_step",
    "adjust_step",
    "pause_bake",
    "resume_bake",
    "cancel_bake",
)
