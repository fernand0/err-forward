import base64
import importlib
import inspect
import json
import os
import pwd
import socket
import urllib.parse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from errbot import BotPlugin, botcmd
from errbot.backends.base import Message
try:
    from errbot.templating import tenv
except ImportError:
    tenv = None


# Path to store peer public keys
PEER_KEYS_FILE = os.path.join(os.path.dirname(__file__), 'peer_keys.json')

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

    def _get_default_key_path(self):
        """Determine a sensible default path for the bot's private key.
        Prefers Errbot's BOT_DATA_DIR, then ~/.errbot, and falls back to the plugin dir.
        """
        bot_id = self.config.get('bot_id') if self.config else None
        key_name = f"{bot_id}_key.pem" if bot_id else "bot_key.pem"

        data_dir = getattr(getattr(self, '_bot', None), 'bot_config', None)
        bot_data_dir = getattr(data_dir, 'BOT_DATA_DIR', None)
        user_errbot = os.path.expanduser('~/.errbot')

        target_path = os.path.join(os.path.dirname(__file__), key_name)
        if bot_data_dir and os.path.isdir(bot_data_dir):
            target_path = os.path.join(bot_data_dir, key_name)
        elif os.path.isdir(user_errbot):
            target_path = os.path.join(user_errbot, key_name)
        return target_path

    def _load_private_key(self):
        """Load or generate an Ed25519 private key for this bot.
        Returns the private key object.
        """
        priv_key_path = self.config.get('priv_key_path') if self.config else None
        if not priv_key_path:
            priv_key_path = self._get_default_key_path()

        private_key = None
        if priv_key_path and os.path.exists(priv_key_path):
            with open(priv_key_path, 'rb') as f:
                priv_bytes = f.read()
                private_key = serialization.load_pem_private_key(priv_bytes, password=None)
        else:
            private_key = ed25519.Ed25519PrivateKey.generate()
            if priv_key_path:
                try:
                    pem = private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    )
                    with open(priv_key_path, 'wb') as f:
                        f.write(pem)
                    os.chmod(priv_key_path, 0o600)
                except Exception as e:
                    self.log.error(f"Failed to save private key to {priv_key_path}: {e}")
        return private_key

    def _load_peer_keys(self):
        """Load known peer public keys from JSON file.
        Returns a dict mapping bot_id to base64-encoded public key.
        """
        peer_keys = {}
        if os.path.exists(PEER_KEYS_FILE):
            try:
                with open(PEER_KEYS_FILE, 'r') as f:
                    peer_keys = json.load(f)
            except Exception:
                self.log.warning("Failed to load peer_keys.json, starting fresh.")
        return peer_keys

    def _save_peer_keys(self, keys_dict):
        """Persist peer public keys dict to JSON file."""
        try:
            with open(PEER_KEYS_FILE, 'w') as f:
                json.dump(keys_dict, f, indent=2)
        except Exception as e:
            self.log.error(f"Failed to save peer keys: {e}")
        return None

    def _sign_envelope(self, payload_dict):
        """Sign a JSON payload dict and return an envelope string.
        The envelope format includes version, timestamp, type, sender, payload, and signature.
        """
        private_key = self._load_private_key()
        payload_json = json.dumps(payload_dict, sort_keys=True).encode('utf-8')
        signature = private_key.sign(payload_json)
        bot_id = (self.config.get('bot_id') if self.config else None) or self.user_name or 'bot1'
        uptime = int(self._bot.get_uptime()) if hasattr(self._bot, 'get_uptime') else 0
        envelope = {
            "ver": 1,
            "ts": uptime,
            "type": payload_dict.get('typ') or payload_dict.get('type'),
            "sender": bot_id,
            "payload": payload_dict,
            "sig": base64.b64encode(signature).decode('utf-8'),
        }
        return json.dumps(envelope)

    def _verify_envelope(self, envelope_str):
        """Verify a signed envelope string.
        Returns the inner payload dict if verification succeeds, else None.
        """
        result = None
        try:
            envelope = json.loads(envelope_str) if isinstance(envelope_str, str) else envelope_str
            if isinstance(envelope, dict):
                payload = envelope.get('payload')
                sig_b64 = envelope.get('sig')
                sender = envelope.get('sender')
                if payload and sig_b64 and sender:
                    peer_keys = self._load_peer_keys()
                    pub_b64 = peer_keys.get(sender)
                    if pub_b64:
                        pub_bytes = base64.b64decode(pub_b64)
                        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
                        payload_json = json.dumps(payload, sort_keys=True).encode('utf-8')
                        signature = base64.b64decode(sig_b64)
                        public_key.verify(signature, payload_json)
                        result = payload
        except Exception as e:
            self.log.debug(f"Envelope verification failed: {e}")
        return result

    def activate(self):
        """
        Triggers on plugin activation
        """
        self.log.info("Super activation")
        super().activate()

        if not self.config:
            self.log.info("ErrForward is not configured. Forbid activation")
        else:
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

            loaded = False
            try:
                mod = importlib.import_module(my_soc_module)
                cls = getattr(mod, my_module)
                site = cls()
                site.setUrl(my_module)
                site.setClient(my_module)
                self.sc = site
                loaded = True
            except (ImportError, AttributeError, Exception) as e:
                self.log.error(f"Failed to load module {my_module}: {e}")

            if loaded:
                chan = str(self.config.get('channel', 'general'))
                self.channel = chan
                # self['chan'] = chan
                self.sc.setChannel(chan)
                self.log.info(f"chanAct {self.sc.getChannel()}")

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

                self.log.debug(f"Chan: {self.sc.getChannel()}")
                try:
                    self.sc.publishPost(msg_j, '', self.sc.getChannel())
                except Exception as e:
                    self.log.error(f"Failed to publish activation message: {e}")

                # Load or generate private key
                private_key = self._load_private_key()
                # Publish a signed activation message
                activation_payload = {
                    'typ': 'Msg',
                    'userName': self.user_name,
                    'userHost': self.user_host,
                    'frm': '',
                    'cmd': '',
                    'args': ''
                }
                signed_msg = self._sign_envelope(activation_payload)
                try:
                    self.sc.publishPost(signed_msg, '', self.sc.getChannel())
                except Exception as e:
                    self.log.error(f"Failed to publish signed activation message: {e}")

                # Announce our public key to peers
                pub_key = private_key.public_key()
                pub_bytes = pub_key.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
                pub_b64 = base64.b64encode(pub_bytes).decode('utf-8')
                key_payload = {
                    'typ': 'KeyAnnounce',
                    'sender': (self.config.get('bot_id') if self.config else None) or self.user_name or 'bot1',
                    'pubkey': pub_b64
                }
                signed_key_announce = self._sign_envelope(key_payload)
                try:
                    self.sc.publishPost(signed_key_announce, '', self.sc.getChannel())
                except Exception as e:
                    self.log.error(f"Failed to publish key announcement: {e}")

                self.start_poller(60, self.manage_posts)
                self.log.info("ErrForward has been activated")
                self.log.info(f"chanAct {self.sc.getChannel()}")
        return None

    def get_configuration_template(self):
        return {
            'channel': "general",
        }

    def check_configuration(self, configuration):
        if hasattr(super(), 'check_configuration'):
            # Only delegate to super if keys strictly match the template,
            # allowing optional extra keys without triggering Errbot's strict mismatch error.
            template = self.get_configuration_template()
            if isinstance(configuration, dict) and set(configuration.keys()) == set(template.keys()):
                super().check_configuration(configuration)
        if not isinstance(configuration, dict) or not configuration.get('channel'):
            from errbot import ValidationException
            raise ValidationException("The 'channel' configuration key must not be empty.")
        return None

    def _check_config(self, option):
        """
        Safely check if an option exists in plugin configuration
        """
        res = None
        if self.config is not None and option in self.config:
            res = self.config[option]
        return res

    def get_my_ip(self):
        """
        Get the outbound IP of the host safely with fallback
        """
        ip = "127.0.0.1"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2.0)
                s.connect(('1.1.1.1', 53))
                ip = s.getsockname()[0]
        except Exception:
            pass
        return ip

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
        chunks = []
        if len(text) <= limit:
            chunks = [text]
        else:
            remaining = text
            while remaining:
                if len(remaining) <= limit:
                    chunks.append(remaining)
                    break

                split_at = remaining.rfind('\n', 0, limit)
                if split_at == -1:
                    split_at = limit

                chunks.append(remaining[:split_at])
                remaining = remaining[split_at:].lstrip('\n')
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

        msg_e = None
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
        if hasattr(self, 'sc') and self.sc:
            chan = self.sc.getChannel()
            try:
                list_bots = self.sc.getBots(chan) or []
            except Exception as e:
                self.log.error(f"Failed to get bots for broadcast: {e}")
                list_bots = []

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
        else:
            self.log.error("Plugin not configured for broadcast")
        self.log.info("End Broadcast")
        return None

    def manage_command(self, *args):
        if len(args) == 3:
            chan, msg_e, msg = args
        elif len(args) == 2:
            msg_e, msg = args
            chan = self.sc.getChannel() if hasattr(self, 'sc') and self.sc else None
        else:
            return None

        cmd = msg_e.get('cmd', '') if isinstance(msg_e, dict) else ''
        self.log.info(f"Start manage command ({cmd})")
        bot_prefix = getattr(self._bot.bot_config, 'BOT_PREFIX', '!')
        len_prefix = len(bot_prefix)
        prefix = cmd[:len_prefix]
        cmd_name = cmd[len_prefix:]

        if prefix == bot_prefix:
            self.log.info(f"{cmd_name} it's for me")
            try:
                if isinstance(msg, dict) and self.id_post in msg:
                    self.sc.deletePostId(msg[self.id_post])
            except Exception as e:
                self.log.error(f"Failed to delete command post: {e}")

            list_commands = self._bot.all_commands

            # Determine the effective command and arguments (support longer compound commands)
            effective_cmd = cmd_name
            raw_args = msg_e.get('args', '')
            unquoted_args = urllib.parse.unquote(raw_args) if (isinstance(raw_args, str) and raw_args) else (raw_args or "")

            potential_parts = unquoted_args.split() if isinstance(unquoted_args, str) else []
            args_remaining = unquoted_args
            for i in range(len(potential_parts), 0, -1):
                test_long_cmd = f"{cmd_name}_{'_'.join(potential_parts[:i])}"
                if test_long_cmd in list_commands:
                    effective_cmd = test_long_cmd
                    args_remaining = ' '.join(potential_parts[i:])
                    break

            if effective_cmd in list_commands:
                method = list_commands[effective_cmd]
                txt_r = ''
                new_args = args_remaining

                # Parse/split args according to the command's expected split settings
                split_args_with = getattr(
                    method,
                    '_err_command_split_args_with',
                    getattr(getattr(method, '__func__', None), '_err_command_split_args_with', "")
                )
                parsed_args = new_args
                if split_args_with != "":
                    try:
                        if hasattr(split_args_with, "parse_args"):
                            import shlex
                            parsed_args = split_args_with.parse_args(shlex.split(new_args))
                        elif callable(split_args_with):
                            parsed_args = split_args_with(new_args)
                        elif split_args_with is None:
                            parsed_args = new_args.split() if new_args else []
                        else:
                            parsed_args = new_args.split(split_args_with) if new_args else []
                    except Exception as e:
                        self.log.warning(f"Error splitting command args with {split_args_with}: {e}")
                        parsed_args = new_args.split() if new_args else []

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

                body_text = f"{bot_prefix}{effective_cmd} {new_args}".strip() if new_args else f"{bot_prefix}{effective_cmd}"
                new_msg = Message(frm=sender, body=body_text)
                if hasattr(new_msg, '__dict__'):
                    new_msg.text = body_text

                try:
                    try:
                        replies = method(new_msg, parsed_args)
                    except TypeError as te:
                        if parsed_args != new_args:
                            replies = method(new_msg, new_args)
                        else:
                            raise te

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
                    publish_chan = chan or self.sc.getChannel()
                    for chunk in txt_chunks:
                        reply_msg = self.prepare_message(
                            typ='Rep',
                            usr=msg_e.get('userName', ''),
                            host=msg_e.get('userHost', ''),
                            frm=msg_e.get('frm', ''),
                            cmd=effective_cmd,
                            args=chunk,
                        )
                        self.sc.publishPost(reply_msg, '', publish_chan)
                except Exception as e:
                    self.log.error(f"Error executing or replying to command {cmd_name}: {e}")
            else:
                self.log.info(f"Command not available: {effective_cmd}")
        self.log.info("End manage command")
        return None

    def manage_reply(self, *args):
        if len(args) == 3:
            chan, msg_e, msg = args
        elif len(args) == 2:
            msg_e, msg = args
            chan = self.sc.getChannel() if hasattr(self, 'sc') and self.sc else None
        else:
            return None

        self.log.info(f"Start manage reply ({msg})")
        if isinstance(msg_e, dict):
            user_host = msg_e.get('userHost', '')
            if '|' in user_host:
                user_host = user_host.split('|')[1]
                if user_host.endswith('>'):
                    user_host = user_host[:-1]
                msg_e['userHost'] = user_host

            target_name = msg_e.get('userName')
            target_host = msg_e.get('userHost')
            legacy_bot_id = (self.config.get('bot_id') if self.config else None) or self.user_name or 'bot1'
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
                    if isinstance(msg, dict) and self.id_post in msg:
                        self.sc.deletePostId(msg[self.id_post])
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
        return None

    def manage_posts(self):
        self.log.info("Start manage posts")
        if not hasattr(self, 'sc') or not self.sc:
            return None
        if not self.config and not self.channel:
            return None

        posts = []
        try:
            self.sc.setPosts()
            posts = self.sc.getPosts() or []
        except Exception as e:
            self.log.error(f"Failed to fetch posts: {e}")
            posts = []

        require_sig = self.config.get('require_signature', False) if self.config else False

        for msg in posts:
            raw_text = msg.get('text') if isinstance(msg, dict) else None
            verified = None
            if raw_text:
                verified = self._verify_envelope(raw_text)

            msg_e = None
            if verified is not None:
                # Envelope signature verified
                if verified.get('typ') == 'KeyAnnounce':
                    sender = verified.get('sender')
                    pubkey = verified.get('pubkey')
                    if sender and pubkey:
                        keys = self._load_peer_keys()
                        keys[sender] = pubkey
                        self._save_peer_keys(keys)
                        self.log.info(f"Stored peer public key for {sender}")
                    continue  # Key announcement handled
                msg_e = verified
            else:
                # Unverified message
                if require_sig:
                    self.log.warning("Dropping unverifiable message (require_signature is True)")
                    continue
                msg_e = self.extract_args(msg)

            if isinstance(msg_e, dict):
                msg_type = msg_e.get('typ') or msg_e.get('type')
                if msg_type == 'Cmd':
                    try:
                        self.manage_command(msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Cmd post: {e}")
                elif msg_type == 'Rep':
                    try:
                        self.manage_reply(msg_e, msg)
                    except Exception as e:
                        self.log.exception(f"Error handling Rep post: {e}")
        return None

    def forward_command(self, mess, args):
        sender = getattr(mess, 'frm', 'unknown')
        self.log.info(f"Begin forward {mess} from {sender}")

        result = ""
        if not hasattr(self, 'sc') or not self.sc:
            result = "ErrForward is not configured. Please configure the plugin first."
        else:
            args_str = args.strip() if args else ""
            if not args_str:
                result = "Usage: forward <command> [args]"
            else:
                if ' ' in args_str:
                    cmd, _, new_args = args_str.partition(' ')
                else:
                    cmd = args_str
                    new_args = ""

                chan = self.sc.getChannel()
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
                    result = f"Broadcasted '{new_cmd}' to all bots on channel {chan}."
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
                        result = f"Forwarded '{cmd}' to channel {chan}."
                    except Exception as e:
                        self.log.error(f"Failed to forward command: {e}")
                        result = f"Failed to forward command: {e}"
        return result

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
        res = None
        chan = self.sc.getChannel() if hasattr(self, 'sc') and self.sc else None
        if not hasattr(self, 'sc') or not self.sc:
            res = {'text': ['ErrForward is not configured.']}
        else:
            try:
                bots = self.sc.getBots(chan) or []
                res = {'text': bots}
            except Exception as e:
                res = {'text': [f"Error listing bots: {e}"]}
        return res

    # Legacy CamelCase aliases for backwards compatibility
    prepareMessage = prepare_message
    extractArgs = extract_args
    broadcastCommand = broadcast_command
    manageCommand = manage_command
    manageReply = manage_reply
    managePosts = manage_posts
    forwardCommand = forward_command
    getMyIP = get_my_ip
    listB = list_bots_cmd
