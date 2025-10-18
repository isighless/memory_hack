from app.helpers.exceptions import BreakException
class OperationControl:
    def __init__(self):
        self._control_break = False
        self._restart_requested = False

    def control_break(self):
        self._control_break = True

    def clear_control_break(self):
        self._control_break = False

    def is_control_break(self):
        return self._control_break

    def test(self):
        if self.is_control_break():
            self.clear_control_break()
            raise BreakException()

    # Server restart control
    def request_restart(self):
        self._restart_requested = True

    def clear_restart(self):
        self._restart_requested = False

    def is_restart_requested(self):
        return self._restart_requested
