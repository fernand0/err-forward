import importlib
import inspect
import json
import os
import pwd
import socket
import urllib.parse

from errbot import BotPlugin, botcmd
from errbot.backends.base import Message
from errbot.templating import tenv

# Mapping of social modules to their respective message ID fields
MODULE_ID_MAP = {
    'moduleSlack': 'ts',
    'moduleGitter': 'id',
    'moduleMastodon': 'id',
    'moduleTwitter': 'id_str',
}

# Maximum message length for platforms like Slack
MAX_MESSAGE_LENGTH = 3800  # Slightly less than 4000 to allow for JSON overhead


class ErrForward(BotPlugin):
    """An Err plugin for forwarding instructions"""

    channel = None
    sc = None
    id_post = 'ts'
    idPost = 'ts'
    user_name = None
    user_host = None

    # ---------------------------------------------------- activation ----------------------------------------------------
    def activate(self):
        self.log.info("Super activation")
        super().activate()
        if not self.config:
            self.log.info("ErrForward is not configured. Forbid activation")
            return

        my_module = self.config.get('module', 'moduleSlack')
        my_soc_module = f"socialModules.{my_module}"
        self.id_post = self.config.get('id_post_override') or MODULE_ID_MAP.get(my_module, 'id')
        self.idPost = self.id_post

        # Restore compatible identification with system defaults
        self.user_name = self.config.get('user_name') or pwd.getpwuid(os.getuid())[0]
        self['userName'] = self.user_name
        self.user_host = self.config.get('user_host') or os.uname()[1]
        self['userHost'] = self.user_host

        try:
            mod = importlib.import_module(my_soc_module)
            cls = getattr(mod, my_module)
            site = cls()
            site.setUrl(my_module)
            site.setClient(my_module)
            self.sc = site
        except Exception as e:
            self.log.error(f"Failed to load module {my_module}: {e}")
            return

        chan = str(self.config.get('channel', 'general'))
        self.channel = chan
        self['chan'] = chan
        self.sc.setChannel(chan)

        bot_prefix = getattr(self._bot.bot_config, 'BOT_PREFIX', '!')
        backend = getattr(self._bot.bot_config, 'BACKEND', 'Unknown')
        msg_j = self.prepare_message(
            typ='Msg',
            args=(
                f"Hello! IP: {self.get_my_ip()}. "
                f"Commands [{bot_prefix}]. "
                f"Name: {self.user_name}@{self.user_host}. "
                f"Backend: {backend}"
            ),
        )
        try:
            self.sc.publishPost(msg_j, '', chan)
        except Exception as e:
            self.log.error(f"Failed to publish activation message: {e}")

        self.start_poller(60, self.manage_posts)
        self.log.info("ErrForward has been activated")

    def get_configuration_template(self):
        return {
            'channel': "general",
            'module': "moduleSlack",
            'user_name': "",  # Defaults to system user
            'user_host': "",  # Defaults to system host
            'id_post_override': "",
        }

    def _get_channel(self):
        if self.channel:
            return self.channel
        if self.config and isinstance(self.config, dict) and self.config.get('channel'):
            return str(self.config['channel'])
        try:
            if hasattr(self, '_store') and self._store is not None and 'chan' in self:
                return self['chan']
        except Exception:
            pass
        return None

    def get_my_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2.0)
                s.connect(('1.1.1.1', 53))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @botcmd
    def myip(self, mess, args):
        yield self.get_my_ip()

    @botcmd
    def myIP(self, mess, args):
        yield self.get_my_ip()

    # ---------------------------------------------------- helpers ----------------------------------------------------
    def _split_message(self, text, limit=MAX_MESSAGE_LENGTH):
        if len(text) <= limit:
            return [text]
        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            split_at = text.rfind('\n', 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip('\n')
        return chunks

    def prepare_message(self, usr="", host="", frm="", mess=None, typ="", cmd="", args=""):
        """Construct a JSON payload for outgoing messages.

        * ``usr`` and ``host`` are optional – if left empty they will not be
          auto‑filled with the bot's own ``self.user_name`` / ``self.user_host``.
          This prevents leaking the bot's identity in replies.
        * ``frm`` (the original sender identifier) is preserved – it is the
          mechanism used by the originating bot to match the reply to its request.
        """
        self.log.info("Start prepare_message")
        if not frm and mess:
            frm = getattr(mess, "frm", str(mess))
        if args and typ != "Msg":
            self.log.debug(f"prepare_message args: {args}")
            args = urllib.parse.quote(str(args))
        msg = {
            "userName": usr,
            "userHost": host,
            "frm": str(frm) if frm else "",
            "typ": typ,
            "cmd": cmd,
            "args": args,
        }
        msg_j = json.dumps(msg)
        self.log.info("End prepare_message")
        return msg_j

    def extract_args(self, msg):
        self.log.debug(f"Msg: {msg}")
        if isinstance(msg, dict) and 'text' in msg:
            try:
                msg_e = json.loads(msg['text'])
            except Exception:
                self.log.debug(f"Error converting json: {msg.get('text')}")
                msg_e = None
        else:
            self.log.info("No valid text in message")
            msg_e = None
        if isinstance(msg_e, dict) and 'args' in msg_e:
            msg_type = msg_e.get('typ') or msg_e.get('type')
            if msg_type and msg_type != 'Msg' and isinstance(msg_e['args'], str):
                msg_e['args'] = urllib.parse.unquote(msg_e['args'])
                if 'typ' not in msg_e:
                    msg_e['typ'] = msg_type
        return msg_e

    def broadcast_command(self, msg, cmd):
        self.log.info("Starting Broadcast")
        chan = self._get_channel()
        if not getattr(self, 'sc', None):
            self.log.error("Plugin not configured for broadcast")
            return
        try:
            bots = self.sc.getBots(chan) or []
        except Exception as e:
            self.log.error(f"Failed to get bots for broadcast: {e}")
            return
        for bot in bots:
            try:
                open_i = bot.find('[')
                close_i = bot.find(']')
                if open_i >= 0 and close_i > open_i:
                    prefix = bot[open_i + 1:close_i]
                else:
                    continue
                new_cmd = prefix + cmd
                msg_j = self.prepare_message(
                    mess=msg.get('mess'),
                    typ='Cmd',
                    cmd=new_cmd,
                    args=msg.get('args', ''),
                )
                self.sc.setChannel(chan)
                self.sc.publishPost(msg_j, '', '')
            except Exception as e:
                self.log.error(f"Failed to broadcast to bot {bot}: {e}")
        self.log.info("End Broadcast")

    def manage_command(self, chan, msg_e, msg):
        cmd = msg_e.get('cmd', '')
        self.log.info(f"Start manage command ({cmd})")
        bot_prefix = getattr(self._bot.bot_config, 'BOT_PREFIX', '!')
        prefix_len = len(bot_prefix)
        if cmd[:prefix_len] != bot_prefix:
            return
        cmd_name = cmd[prefix_len:]
        # Delete the original command post if possible
        try:
            old = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old)
        except Exception as e:
            self.log.error(f"Failed to delete command post: {e}")
        list_commands = self._bot.all_commands
        effective_cmd = cmd_name
        raw_args = msg_e.get('args', '')
        unquoted_args = urllib.parse.unquote(raw_args) if raw_args else ""
        # Support compound commands (e.g., cmd_subcmd)
        parts = unquoted_args.split(' ', 1)
        if parts and parts[0]:
            test_long = f"{cmd_name}_{parts[0]}"
            if test_long in list_commands:
                effective_cmd = test_long
                unquoted_args = parts[1] if len(parts) > 1 else ""
        if effective_cmd not in list_commands:
            self.log.info(f"Command not available: {effective_cmd}")
            self.log.info("End manage command")
            return
        method = list_commands[effective_cmd]
        sender = None
        sender_str = msg_e.get('frm')
        if sender_str and sender_str != '-':
            try:
                sender = self._bot.build_identifier(sender_str)
            except Exception:
                sender = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            sender = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        new_msg = Message(frm=sender, body=f"{effective_cmd} {unquoted_args}".strip())
        splitter = getattr(method, '_err_command_split_args_with', "")
        if splitter:
            if hasattr(splitter, 'parse_args'):
                call_args = splitter.parse_args(unquoted_args)
            elif callable(splitter):
                call_args = splitter(unquoted_args)
            else:
                call_args = unquoted_args.split(splitter)
        else:
            call_args = unquoted_args
        try:
            replies = method(new_msg, call_args)
            if not inspect.isgeneratorfunction(method) and not isinstance(replies, (tuple, list)):
                replies = [replies]
            txt = ''
            for r in replies:
                if r is None:
                    continue
                if isinstance(r, str):
                    txt = f"{txt}\n{r}" if txt else r
                else:
                    tmpl = getattr(method, '_err_command_template', None)
                    if not tmpl:
                        txt = (f"{txt} {r}").strip()
                    else:
                        txt = txt + tenv().get_template(f"{tmpl}.md").render(r)
            chunks = self._split_message(txt)
            chan_p = self._get_channel()
            for chunk in chunks:
                reply_msg = self.prepare_message(
                    typ='Rep',
                    usr='',
                    host='',
                    frm=msg_e.get('frm', ''),
                    cmd=effective_cmd,
                    args=chunk,
                )
                self.sc.setChannel(chan_p)
                self.sc.publishPost(reply_msg, '', '')
        except Exception as e:
            self.log.error(f"Error executing or replying to command {cmd_name}: {e}")
        self.log.info("End manage command")

    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep')."""
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
        self.log.info(f"It's for me ({self.user_name}@{self.user_host})")
        # Delete the original reply post if possible
        try:
            old = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")
        # Resolve original sender (frm)
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                msg_to = self._bot.build_identifier(frm)
            except Exception:
                msg_to = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            msg_to = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            msg_to = None
        raw = msg_e.get('args', '')
        replies = urllib.parse.unquote(raw) if raw else ""
        replies = replies.replace('_', r'\\_')
        reply_msg = self.prepare_message(
            usr=target_name,
            host=target_host,
            frm=frm or '',
            typ='Rep',
            cmd='',
            args=replies,
        )
        if msg_to:
            try:
                self.sc.setChannel(chan)
                self.sc.publishPost(reply_msg, '', '')
            except Exception as e:
                self.log.error(f"Failed to publish reply post: {e}")
        else:
            self.log.warning(f"No recipient found for reply: {replies}")

    def manage_posts(self):
        chan = self._get_channel()
        if not getattr(self, 'sc', None) or not chan:
            return
        try:
            self.sc.setPosts()
            posts = self.sc.getPosts() or []
        except Exception as e:
            self.log.error(f"Failed to fetch posts: {e}")
            return
        for msg in posts:
            msg_e = self.extract_args(msg)
            if isinstance(msg_e, dict):
                typ = msg_e.get('typ') or msg_e.get('type')
                if typ == 'Cmd':
                    try:
                        self.manage_command(chan, msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Cmd post: {e}")
                elif typ == 'Rep':
                    try:
                        self.manage_reply(chan, msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Rep post: {e}")

    def forward_command(self, mess, args):
        sender = getattr(mess, 'frm', 'unknown')
        self.log.info(f"Begin forward {mess} from {sender}")
        chan = self._get_channel()
        if not getattr(self, 'sc', None):
            return "ErrForward is not configured. Please configure the plugin first."
        args_str = args.strip() if args else ""
        if not args_str:
            return "Usage: forward <command> [args]"
        if ' ' in args_str:
            cmd, _, new_args = args_str.partition(' ')
        else:
            cmd, new_args = args_str, ""
        if cmd.startswith('*'):
            new_cmd = cmd[1:]
            msg = {'mess': mess, 'typ': 'Cmd', 'cmd': new_cmd, 'args': new_args}
            self.broadcast_command(msg, new_cmd)
            return f"Broadcasted '{new_cmd}' to all bots on channel {chan}."
        else:
            msg_e = self.prepare_message(mess=mess, typ='Cmd', cmd=cmd, args=new_args)
            try:
                self.sc.setChannel(chan)
                self.sc.publishPost(msg_e, '', '')
                return f"Forwarded '{cmd}' to channel {chan}."
            except Exception as e:
                self.log.error(f"Failed to forward command: {e}")
                return f"Failed to forward command: {e}"

    @botcmd
    def forward(self, mess, args):
        """Command forwarding to another bot"""
        return self.forward_command(mess, args)

    @botcmd
    def fw(self, mess, args):
        """Command forwarding to another bot (abrv)"""
        return self.forward_command(mess, args)

    @botcmd(name='listB', template='monospace')
    def list_bots_cmd(self, mess, args):
        """List bots connected to the Slack channel"""
        chan = self._get_channel()
        if not getattr(self, 'sc', None):
            return {'text': ['ErrForward is not configured.']}
        try:
            bots = self.sc.getBots(chan) or []
            return {'text': bots}
        except Exception as e:
            return {'text': [f"Error listing bots: {e}"]}

    # Backward‑compatible aliases
    prepareMessage = prepare_message
    extractArgs = extract_args
    broadcastCommand = broadcast_command
    manageCommand = manage_command
    manageReply = manage_reply
    managePosts = manage_posts
    forwardCommand = forward_command
    getMyIP = get_my_ip
