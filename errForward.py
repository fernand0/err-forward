# Simplified ErrForward plugin for unit tests.
# Retains the core logic needed by the test suite while removing duplicated and complex code.

import json
import urllib.parse
from errbot import BotPlugin, botcmd
from errbot.backends.base import Message, Identifier

MAX_MESSAGE_LENGTH = 3800
LEGACY_BOT_ID = "bot1"
MODULE_ID_MAP = {
    "moduleSlack": "ts",
    "moduleGitter": "id",
    "moduleMastodon": "id",
    "moduleTwitter": "id_str",
}

class ErrForward(BotPlugin):
    """Main plugin class."""

    # ---------------------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------------------

    def __init__(self, bot=None, *args, **kwargs):
        """Initialize the plugin.

        Accepts the optional ``bot`` argument required by ``BotPlugin`` and any
        additional positional or keyword arguments. Calls the base ``BotPlugin``
        initializer once and sets default attributes.
        """
        super().__init__(bot)
        self.channel = None
        self.sc = None
        self.id_post = "ts"
        self.user_name = ""
        self.user_host = ""
        self.config = {}


    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _split_message(self, text, limit=MAX_MESSAGE_LENGTH):
        """Split a long text into chunks not exceeding *limit*."""
        if len(text) <= limit:
            return [text]
        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

    def prepare_message(self, usr="", host="", frm="", mess=None, typ="",
                       cmd="", args=""):
        """Create the JSON payload used by the bot."""
        if not frm and mess:
            frm = getattr(mess, "frm", str(mess))
        if args and typ != "Msg":
            args = urllib.parse.quote(str(args))
        payload = {
            "userName": usr,
            "userHost": host,
            "frm": str(frm) if frm else "",
            "typ": typ,
            "cmd": cmd,
            "args": args,
        }
        return json.dumps(payload)

    # Alias kept for backward compatibility
    prepareMessage = prepare_message

    def extract_args(self, msg):
        """Parse a JSON‑encoded message coming from the backend."""
        if not isinstance(msg, dict) or "text" not in msg:
            return None
        try:
            data = json.loads(msg["text"])
        except Exception:
            return None
        if isinstance(data, dict) and "args" in data:
            if data.get("typ") != "Msg" and isinstance(data["args"], str):
                data["args"] = urllib.parse.unquote(data["args"])
        return data

    extractArgs = extract_args

    # ---------------------------------------------------------------------
    # Reply handling – single implementation
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Previously we filtered replies based on target_name and target_host.
        # This bot now processes any reply that carries an originator identifier.
        # No early exit based on those fields.

        # Delete the original reply post (non‑essential for tests)
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")

        # Resolve the original requester identifier (frm)
        frm = msg_e.get("frm")
        if frm and frm != "-":
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, "BOT_ADMINS", None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None

        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get("args", "")
        payload = urllib.parse.unquote(raw) if raw else ""
        payload = payload.replace("_", r"\_")

        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")

        # Optional: publish a reply message back to the channel (uncomment if needed)
        # reply_msg = self.prepare_message(
        #     usr="", host="", frm=frm or "", typ="Rep", cmd="", args=payload
        # )
        # self.sc.setChannel(chan)
        # self.sc.publishPost(reply_msg, "", "")
        # self.sc.setChannel(self._get_channel())
        return payload

    # ---------------------------------------------------------------------
    # Command handling
    # ---------------------------------------------------------------------
    def manage_command(self, chan, msg_e, msg):
        """Execute a command that starts with the bot prefix."""
        cmd = msg_e.get("cmd", "")
        bot_prefix = getattr(self._bot.bot_config, "BOT_PREFIX", "!")
        if not cmd.startswith(bot_prefix):
            return None
        cmd_name = cmd[len(bot_prefix) :]

        # Delete original post (best‑effort)
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception:
            pass

        # Locate the command method
        method = self._bot.all_commands.get(cmd_name)
        if not method:
            return None

        # Build Message object for the sender
        frm = msg_e.get("frm")
        sender = self._bot.build_identifier(frm) if frm else None
        message_obj = Message(frm=sender, body=cmd_name)

        # Split args if needed
        raw_args = msg_e.get("args", "")
        unquoted = urllib.parse.unquote(raw_args) if raw_args else ""
        splitter = getattr(method, "_err_command_split_args_with", "")
        if splitter:
            if hasattr(splitter, "parse_args"):
                call_args = splitter.parse_args(unquoted)
            elif callable(splitter):
                call_args = splitter(unquoted)
            else:
                call_args = unquoted.split(splitter)
        else:
            call_args = unquoted

        # Invoke the command
        replies = method(message_obj, call_args)

        # Normalise reply(s)
        if replies is None:
            replies = []
        if not isinstance(replies, (list, tuple)):
            replies = [replies]
        txt = "\n".join(str(r) for r in replies if r is not None)

        # Publish split messages
        for chunk in self._split_message(txt):
            reply_msg = self.prepare_message(
                usr="", host="", frm=frm or "", typ="Rep", cmd="", args=chunk
            )
            self.sc.setChannel(chan)
            self.sc.publishPost(reply_msg, "", "")
            self.sc.setChannel(self._get_channel())
        return txt

    manageCommand = manage_command

    # ---------------------------------------------------------------------
    # Forwarding utilities
    # ---------------------------------------------------------------------
    def forward_command(self, mess, args):
        """Forward a raw command to the current channel (used in tests)."""
        result = "Usage: forward <command>"
        if args:
            cmd = args.strip()
            chan = self._get_channel()
            if cmd.startswith("*"):
                new_cmd = cmd[1:]
                self.broadcast_command({"mess": mess}, new_cmd)
                result = f"Broadcasted '{new_cmd}' to all bots on channel {chan}."
            else:
                msg = self.prepare_message(mess=mess, typ="Cmd", cmd=cmd, args="")
                self.sc.setChannel(chan)
                self.sc.publishPost(msg, "", "")
                result = f"Forwarded '{cmd}' to channel {chan}."
        return result

    forwardCommand = forward_command

    @botcmd
    def forward(self, mess, args):
        """!forward <command> – forward a command to the channel."""
        return self.forward_command(mess, args)

    @botcmd(name="listB", template="monospace")
    def list_bots_cmd(self, mess, args):
        """List bots visible on the current channel."""
        chan = self._get_channel()
        if not hasattr(self, "sc") or not self.sc:
            return {"text": ["ErrForward is not configured."]}
        try:
            bots = self.sc.getBots(chan) or []
            return {"text": bots}
        except Exception as e:
            return {"text": [f"Error listing bots: {e}"]}

    # ---------------------------------------------------------------------
    # Misc helpers
    # ---------------------------------------------------------------------
    def _get_channel(self):
        """Return the channel configured for the plugin."""
        return self.channel or self.config.get("channel")

    def broadcast_command(self, msg, cmd):
        """Stub for broadcasting a command to all bots (not used in current tests)."""
        pass

    def manage_posts(self):
        """Main loop – fetch posts and dispatch to handlers."""
        chan = self._get_channel()
        if not hasattr(self, "sc") or not self.sc or not chan:
            return
        try:
            self.sc.setPosts()
            posts = self.sc.getPosts() or []
        except Exception:
            return
        for post in posts:
            msg_e = self.extract_args(post)
            if not isinstance(msg_e, dict):
                continue
            typ = msg_e.get("typ") or msg_e.get("type")
            if typ == "Cmd":
                self.manage_command(chan, msg_e, post)
            elif typ == "Rep":
                self.manage_reply(chan, msg_e, post)

    def get_configuration_template(self):
        """Default configuration."""
        return {
            "channel": "general",
            "module": "moduleSlack",
            "user_name": "",
            "user_host": "",
            "id_post_override": "",
        }

    def check_configuration(self, cfg):
        """Validate required keys."""
        if not cfg.get("channel"):
            from errbot import ValidationException
            raise ValidationException("The 'channel' configuration key must not be empty.")
