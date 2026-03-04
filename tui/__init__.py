from textual.screen import ModalScreen
from textual.widgets import Input


class BaseModal(ModalScreen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _any_input_focused(self) -> bool:
        return any(inp.has_focus for inp in self.query(Input))

    async def key_left(self) -> None:
        """Move focus left on arrow key press."""
        if not self._any_input_focused():
            self.app.action_focus_previous()

    async def key_right(self) -> None:
        """Move focus right on arrow key press."""
        if not self._any_input_focused():
            self.app.action_focus_next()

    async def key_down(self) -> None:
        """Move focus down on arrow key press."""
        self.app.action_focus_next()

    async def key_up(self) -> None:
        """Move focus up on arrow key press."""
        self.app.action_focus_previous()

    async def key_escape(self) -> None:
        """Close modal when ESC is pressed."""
        self.dismiss()
