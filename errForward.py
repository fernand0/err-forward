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
    """
    An Err plugin for forwarding instructions
    """

    channel = None
    sc = None
    id_post = 'ts'
    idPost = 'ts'
    user_name = None
    user_host = None

    def activate(self):
        """
        Triggers on plugin activation
        """
        self.log.info("Super activation")
        super().activate()

        if not self.config:
            self.log.info("ErrForward is not configured. Forbid activation")
            return

        my_module = self.config.get('module', 'moduleSlack')
        my_soc_module = f"socialModules.{my_module}"

        # Use override if provided, otherwise use mapping, default to 'id'
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
        except (ImportError, AttributeError, Exception) as e:
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

        self.log.debug(f"Chan: {chan}")
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

    def check_configuration(self, configuration):
        super().check_configuration(configuration)
        if not configuration.get('channel'):
            from errbot import ValidationException
            raise ValidationException("The 'channel' configuration key must not be empty.")

    def _check_config(self, option):
        """
        Safely check if an option exists in plugin configuration
        """
        if self.config is not None and option in self.config:
            return self.config[option]
        return None

    def _get_channel(self):
        """
        Get configured channel with safe fallback
        """
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
        """
        Get the outbound IP of the host safely with fallback
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2.0)
                s.connect(('1.1.1.1', 53))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @botcmd
    def myip(self, mess, args):
        """
        IP of the bot
        """
        yield self.get_my_ip()

    @botcmd
    def myIP(self, mess, args):
        """
        IP of the bot (legacy alias)
        """
        yield self.get_my_ip()

    def _split_message(self, text, limit=MAX_MESSAGE_LENGTH):
        """
        Splits a message into chunks within the limit,
        preferring newline boundaries.
        """
        if len(text) <= limit:
            return [text]

        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break

            # Find the last newline within the limit
            split_at = text.rfind('\n', 0, limit)
            if split_at == -1:
                # No newline, split at the limit
                split_at = limit

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip('\n')

        return chunks

    def prepare_message(
        self,
        usr="",
        host="",
        frm="",
        mess=None,
        typ="",
        cmd="",
        args="",
    ):
        self.log.info("Start prepare_message")

        if not frm and mess:
            frm = getattr(mess, 'frm', str(mess))

        if args and typ != 'Msg':
            self.log.debug(f"prepare_message args: {args}")
            args = urllib.parse.quote(str(args))

        msg = {
            'userName': usr or self.user_name or pwd.getpwuid(os.getuid())[0],
            'userHost': host or self.user_host or os.uname()[1],
            'frm': str(frm) if frm else '',
            'typ': typ,
            'cmd': cmd,
            'args': args,
        }
        msg_j = json.dumps(msg)

        self.log.info("End prepare_message")
        return msg_j

    def extract_args(self, msg):
        self.log.debug(f"Msg: {msg}")

        if isinstance(msg, dict) and 'text' in msg:
            try:
                msg_e = json.loads(msg['text'])
            except (json.JSONDecodeError, TypeError, ValueError):
                self.log.debug(f"Error converting json: {msg.get('text')}")
                msg_e = None
        else:
            self.log.info("No valid text in message")
            msg_e = None

        # Support both 'typ' and 'type' for maximum compatibility
        if isinstance(msg_e, dict) and 'args' in msg_e:
            msg_type = msg_e.get('typ') or msg_e.get('type')
            if msg_type and msg_type != 'Msg':
                if isinstance(msg_e['args'], str):
                    msg_e['args'] = urllib.parse.unquote(msg_e['args'])
                # Ensure 'typ' exists even if the sender used 'type'
                if 'typ' not in msg_e:
                    msg_e['typ'] = msg_type

        return msg_e

    def broadcast_command(self, msg, cmd):
        self.log.info("Starting Broadcast")
        #chan = self._get_channel()
        chan = self.sc.getChannel()
        if not hasattr(self, 'sc') or not self.sc:
            self.log.error("Plugin not configured for broadcast")
            return

        try:
            list_bots = self.sc.getBots(chan) or []
        except Exception as e:
            self.log.error(f"Failed to get bots for broadcast: {e}")
            return

        for bot in list_bots:
            try:
                bracket_open = bot.find('[')
                bracket_close = bot.find(']')
                if bracket_open >= 0 and bracket_close > bracket_open:
                    start = bot[bracket_open + 1:bracket_close]
                else:
                    continue

                new_cmd = start + cmd
                msg_j = self.prepare_message(
                    mess=msg.get('mess'),
                    typ='Cmd',
                    cmd=new_cmd,
                    args=msg.get('args', ''),
                )
                self.sc.publishPost(msg_j, '', chan)
            except Exception as e:
                self.log.error(f"Failed to broadcast to bot {bot}: {e}")

        self.log.info("End Broadcast")

    def manage_command(self, chan, msg_e, msg):
        cmd = msg_e.get('cmd', '')
        self.log.info(f"Start manage command ({cmd})")
        bot_prefix = getattr(self._bot.bot_config, 'BOT_PREFIX', '!')
        len_prefix = len(bot_prefix)
        prefix = cmd[:len_prefix]
        cmd_name = cmd[len_prefix:]

        if prefix == bot_prefix:
            self.log.info(f"{cmd_name} it's for me")
            try:
                old_chan = self.sc.getChannel()
                self.sc.setChannel(chan)
                if self.id_post in msg:
                    self.log.info(f"Chann: {chan} Id: {self.id_post} MsgId: {msg[self.id_post]}")
                    self.sc.deletePostId(msg[self.id_post])
                self.sc.setChannel(old_chan)
            except Exception as e:
                self.log.error(f"Failed to delete command post: {e}")

            list_commands = self._bot.all_commands

            # Determine the effective command and arguments (support longer compound commands)
            effective_cmd = cmd_name
            raw_args = msg_e.get('args', '')
            unquoted_args = urllib.parse.unquote(raw_args) if raw_args else ""

            potential_long_cmd_parts = unquoted_args.split(' ', 1)
            if potential_long_cmd_parts and potential_long_cmd_parts[0]:
                test_long_cmd = f"{cmd_name}_{potential_long_cmd_parts[0]}"
                if test_long_cmd in list_commands:
                    effective_cmd = test_long_cmd
                    if len(potential_long_cmd_parts) > 1:
                        unquoted_args = potential_long_cmd_parts[1]
                    else:
                        unquoted_args = ""

            if effective_cmd in list_commands:
                method = list_commands[effective_cmd]
                txt_r = ''
                new_args = unquoted_args

                # Build proper sender identifier and Message object
                sender_str = msg_e.get('frm')
                if sender_str and sender_str != '-':
                    try:
                        sender = self._bot.build_identifier(sender_str)
                    except Exception:
                        sender = None
                elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
                    sender = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
                else:
                    sender = None

                # CRITICAL: Always construct a valid Message object whether args exist or not
                new_msg = Message(frm=sender, body=f"{effective_cmd} {new_args}".strip())

                try:
                    replies = method(new_msg, new_args)
                    if (not inspect.isgeneratorfunction(method)
                            and not isinstance(replies, (tuple, list))):
                        replies = [replies]

                    for reply in replies:
                        if reply is None:
                            continue
                        if isinstance(reply, str):
                            txt_r = f"{txt_r}\n{reply}" if txt_r else reply
                        else:
                            template = getattr(method, '_err_command_template', None)
                            if not template:
                                txt_r = (f"{txt_r} {reply}").strip()
                            else:
                                txt_r = txt_r + tenv().get_template(
                                    f"{template}.md"
                                ).render(reply)

                    # Split long replies into chunks
                    txt_chunks = self._split_message(txt_r)
                    # chan_p = self._get_channel()
                    old_chan = self.sc.getChannel()
                    self.sc.setChannel(chan)
                    for chunk in txt_chunks:
                        reply_msg = self.prepare_message(
                            typ='Rep',
                            usr=msg_e.get('userName', ''),
                            host=msg_e.get('userHost', ''),
                            frm=msg_e.get('frm', ''),
                            cmd=effective_cmd,
                            args=chunk,
                        )
                        self.sc.publishPost(reply_msg, '', chan)
                        self.sc.setChannel(old_chan)
                except Exception as e:
                    self.log.error(f"Error executing or replying to command {cmd_name}: {e}")
            else:
                self.log.info(f"Command not available: {effective_cmd}")
        self.log.info("End manage command")

    def manage_reply(self, chan, msg_e, msg):
        self.log.info(f"Start manage reply ({msg})")
        user_host = msg_e.get('userHost', '')
        if '|' in user_host:
            user_host = user_host.split('|')[1]
            if user_host.endswith('>'):
                user_host = user_host[:-1]
            msg_e['userHost'] = user_host

        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current_target = (
            target_name == self.user_name and target_host == self.user_host
        )
        is_legacy_target = (
            target_name == legacy_bot_id and target_host == 'err-forward'
        )
        self.log.info(f"Username: {self.user_name} Userhost: {self.user_host}"
                      f" Target: {target_name} Target host: {target_host}"
                      f" Legacy: {legacy_bot_id}")

        # Versions using bot_id addressed replies as <bot_id>@err-forward.
        if is_current_target or is_legacy_target:
            self.log.info(f"It's for me ({self.user_name}@{self.user_host})")
            try:
                old_chan = self.sc.getChannel()
                self.sc.setChannel(chan)
                self.log.info(f"Chann: {chan} Id: {self.id_post}")
                if self.id_post in msg:
                    self.sc.deletePostId(msg[self.id_post])
                self.sc.channel = old_chan
            except Exception as e:
                self.log.error(f"Failed to delete reply post: {e}")

            raw_args = msg_e.get('args', '')
            replies = urllib.parse.unquote(raw_args) if raw_args else ""

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

            # Safe markdown escaping without Python 3.12 syntax warning
            replies = replies.replace('_', r'\_')

            if msg_to and replies:
                self.send(msg_to, replies)
            elif not msg_to:
                self.log.warning(f"No recipient found for reply: {replies}")

    def manage_posts(self):
        # chan = self._get_channel()
        self.log.info(f"Start manage posts in ({chan})")
        if not hasattr(self, 'sc') or not self.sc or not chan:
            return
        chan = self.sc.getChannel()

        try:
            self.sc.setPosts()
            posts = self.sc.getPosts() or []
        except Exception as e:
            self.log.error(f"Failed to fetch posts: {e}")
            return

        for msg in posts:
            msg_e = self.extract_args(msg)
            # Safe check for dictionary and type key
            if isinstance(msg_e, dict):
                msg_type = msg_e.get('typ') or msg_e.get('type')
                if msg_type == 'Cmd':
                    try:
                        self.manage_command(chan, msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Cmd post: {e}")
                elif msg_type == 'Rep':
                    try:
                        self.manage_reply(chan, msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Rep post: {e}")

    def forward_command(self, mess, args):
        sender = getattr(mess, 'frm', 'unknown')
        self.log.info(f"Begin forward {mess} from {sender}")
        # chan = self._get_channel()
        chan = self.sc.getChannel()
        if not hasattr(self, 'sc') or not self.sc:
            return "ErrForward is not configured. Please configure the plugin first."

        args_str = args.strip() if args else ""
        if not args_str:
            return "Usage: forward <command> [args]"

        if ' ' in args_str:
            cmd, _, new_args = args_str.partition(' ')
        else:
            cmd = args_str
            new_args = ""

        if cmd.startswith('*'):
            new_cmd = cmd[1:]
            msg = {
                'mess': mess,
                'typ': 'Cmd',
                'cmd': new_cmd,
                'args': new_args,
            }
            self.broadcast_command(msg, new_cmd)
            self.log.info(f"End forward broadcast for {mess}")
            return f"Broadcasted '{new_cmd}' to all bots on channel {chan}."
        else:
            msg_e = self.prepare_message(
                mess=mess,
                typ='Cmd',
                cmd=cmd,
                args=new_args,
            )
            try:
                self.sc.publishPost(msg_e, '', chan)
                self.log.info(f"End forward {mess}")
                return f"Forwarded '{cmd}' to channel {chan}."
            except Exception as e:
                self.log.error(f"Failed to forward command: {e}")
                return f"Failed to forward command: {e}"

    @botcmd
    def forward(self, mess, args):
        """
        Command forwarding to another bot
        """
        return self.forward_command(mess, args)

    @botcmd
    def fw(self, mess, args):
        """
        Command forwarding to another bot (abrv)
        """
        return self.forward_command(mess, args)

    @botcmd(name='listB', template='monospace')
    def list_bots_cmd(self, mess, args):
        """
        List bots connected to the Slack channel
        """
        #chan = self._get_channel()
        chan = self.sc.getChannel()
        if not hasattr(self, 'sc') or not self.sc:
            return {'text': ['ErrForward is not configured.']}
        try:
            bots = self.sc.getBots(chan) or []
            return {'text': bots}
        except Exception as e:
            return {'text': [f"Error listing bots: {e}"]}

    # Legacy CamelCase aliases for backwards compatibility
    prepareMessage = prepare_message
    extractArgs = extract_args
    broadcastCommand = broadcast_command
    manageCommand = manage_command
    manageReply = manage_reply
    managePosts = manage_posts
    forwardCommand = forward_command
    getMyIP = get_my_ip
    #listB = list_bots_cmd
