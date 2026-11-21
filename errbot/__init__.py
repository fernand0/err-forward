class ValidationException(Exception):
    pass

class BotPlugin:
    """Minimal stub for errbot BotPlugin"""
    def __init__(self, bot=None):
        self._bot = bot
        self.log = type('log', (), {'info': print, 'debug': print, 'error': print, 'warning': print})
        self.config = {}
        # allow attribute dict storage
        self.__dict__.update({})

    def activate(self):
        pass

    def check_configuration(self, configuration):
        pass

    def start_poller(self, interval, func):
        pass

    def send(self, to, content):
        # placeholder send method used in tests
        pass

def botcmd(func=None, *, name=None, template=None, split_args_with=""):
    """Decorator stub that mirrors the real errbot botcmd signature."""
    def decorator(f):
        f._err_command_split_args_with = split_args_with
        f._err_command_template = template
        f._err_command_name = name or f.__name__
        f._err_command_flow_only = False
        return f

    result = decorator(func) if func is not None else decorator
    return result
