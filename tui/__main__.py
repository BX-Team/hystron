"""Allow  python -m tui  to launch the admin TUI directly."""

from app.database import init_db
from tui.admin import AdminApp

init_db()
AdminApp().run()
