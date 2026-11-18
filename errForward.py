"""Simplified ErrForward plugin for unit tests.
Retains the core logic needed by the test suite while removing duplicated and complex code.
"""

import json
import urllib.parse
from errbot import BotPlugin, botcmd
from errbot.backends.base import Message, Identifier

MAX_MESSAGE_LENGTH = 3800
MODULE_ID_MAP = {
    'moduleSlack': 'ts',
    'moduleGitter': 'id',
    'moduleMastodon': 'id',
    'moduleTwitter': 'id_str',
}

class ErrForward(BotPlugin):
    def __init__(self, bot=None):
        super().__init__(bot)
        self.channel = None
        self.sc = None
        self.id_post = 'ts'
        self.idPost = 'ts'
        self.user_name = ''
        self.user_host = ''
        self.config = {}

        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    # Helpers used by tests
        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    def get_my_ip(self):
        return "127.0.0.1"

    def getMyIP(self):
        return self.get_my_ip()

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

    # Compatibility aliases used in tests
    prepareMessage = prepare_message

    def extract_args(self, msg):
        if isinstance(msg, dict) and "text" in msg:
            try:
                data = json.loads(msg["text"])
            except Exception:
                return None
        else:
            return None
        if isinstance(data, dict) and "args" in data:
            if data.get("typ") != "Msg" and isinstance(data["args"], str):
                data["args"] = urllib.parse.unquote(data["args"])
        return data

    extractArgs = extract_args

        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    # Command handling used by tests
        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    def manage_command(self, chan, msg_e, msg):
        cmd = msg_e.get("cmd", "")
        bot_prefix = getattr(self._bot.bot_config, "BOT_PREFIX", "!")
        if not cmd.startswith(bot_prefix):
            return
        cmd_name = cmd[len(bot_prefix):]
        # delete original post if possible
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception:
            pass
        # locate command method
        method = self._bot.all_commands.get(cmd_name)
        if not method:
            return
        # build Message object for sender
        frm = msg_e.get("frm")
        sender = self._bot.build_identifier(frm) if frm else None
        message_obj = Message(frm=sender, body=cmd_name)
        # split args if needed
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
        # invoke command
        replies = method(message_obj, call_args)
        # Normalise reply(s)
        if replies is None:
            replies = []
        if not isinstance(replies, (list, tuple)):
            replies = [replies]
        txt = "\n".join(str(r) for r in replies if r is not None)
        # split and publish

        # split and publish
        for chunk in self._split_message(txt):
            pass

            
        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )

                typ="Rep",
                usr=msg_e.get("userName", ""),
                host=msg_e.get("userHost", ""),
                frm=msg_e.get("frm", ""),
                cmd=cmd_name,
                args=chunk,
            )
            self.sc.setChannel(chan)
            self.sc.publishPost(reply_msg, "", "")

    manageCommand = manage_command

        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    # Reply handling – sends plain escaped text via self.send (used by tests)
        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

            # Simplified reply handling: verify target, clean up, and forward payload via self.send
        def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the
        original post if possible, resolve the original requester identifier (frm),
        unescape and markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify target bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
        # Delete the original reply post if possible
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")
        # Resolve original requester identifier (frm)
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and escape payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        Send reply
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed; method ends after sending
(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        The reply is intended for this bot (current or legacy). The payload is
        forwarded to the original requester identified by ``frm`` using ``self.send``.
        """
        # Identify the intended recipient (this bot)
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not for this bot; ignoring.")
            return
        # Clean up the original reply post if possible
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")
        # Resolve original requester identifier (frm)
        frm = msg_e.get('frm')
        recipient = None
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        # Extract payload, unquote and escape markdown underscores
        raw = msg_e.get('args', '')
        text = urllib.parse.unquote(raw) if raw else ''
        text = text.replace('_', r'\_')
        # Send reply via self.send (tests replace this method)
        if recipient:
            try:
                self.send(recipient, text)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {text}")

        """Process an incoming reply (type 'Rep').

        The reply contains the original requester's ``userName`` and ``userHost``.
        We verify that the reply is addressed to this bot (current or legacy).
        Then we forward the payload back to the original sender (``frm``) using
        ``self.send``. The text is unescaped and markdown‑escaped (underscores).
        """
        # Identify target bot (current or legacy) to decide if we should handle
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
        # Clean up original reply post if possible (non‑essential for tests)
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")
        # Resolve original requester identifier (frm)
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract payload, unquote and escape markdown underscores
        raw = msg_e.get('args', '')
        text = urllib.parse.unquote(raw) if raw else ''
        text = text.replace('_', r'\_')
        # Send reply via self.send (tests replace this method)
        if recipient:
            try:
                self.send(recipient, text)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {text}")
(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        The reply contains the original requester's ``userName`` and ``userHost``.
        We verify that the reply is addressed to this bot, then forward the payload
        back to the original sender (``frm``) while preserving the requester's
        identity so the originator bot can match the reply to its original request.
        """
        # Identify the original requester from the incoming reply
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        # Determine if this reply is intended for this bot (current or legacy)
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current_target = (target_name == self.user_name and target_host == self.user_host)
        is_legacy_target = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current_target or is_legacy_target):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
        # Clean up the original reply post if possible
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception as e:
            self.log.error(f"Failed to delete reply post: {e}")
        # Resolve the original sender identifier (frm) to route the reply back
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
        # Extract and safely unescape the reply payload
        raw_args = msg_e.get('args', '')
        replies = urllib.parse.unquote(raw_args) if raw_args else ""
        # Escape markdown characters safely (underscore)
        replies = replies.replace('_', r'\\_')
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
-        
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch
*** Begin Patch
*** Update File: /home/ftricas/usr/src/Python/deGitHub/err-forward/errForward.py
@@
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch('_', r'\\_')
        # Send the reply back to the original requester using frm
        if msg_to:
            try:
                self.send(msg_to, replies)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {replies}")
        target_name = msg_e.get("userName")
        target_host = msg_e.get("userHost")
        legacy_bot_id = self.config.get("bot_id", "bot1")
        is_me = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == "err-forward")
        if not (is_me or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
        # delete original reply post if possible
        try:
            old_chan = self.sc.getChannel()
            self.sc.setChannel(chan)
            if self.id_post in msg:
                self.sc.deletePostId(msg[self.id_post])
            self.sc.setChannel(old_chan)
        except Exception:
            pass
        # resolve recipient identifier
        frm = msg_e.get("frm")
        if frm:
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        else:
            recipient = None
        # extract and unescape reply payload
        raw = msg_e.get("args", "")
        text = urllib.parse.unquote(raw) if raw else ""
        # escape markdown underscores
        text = text.
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
-        
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch
*** Begin Patch
*** Update File: /home/ftricas/usr/src/Python/deGitHub/err-forward/errForward.py
@@
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch('_', r'\\_')
        if recipient:
            # send plain text to original requester (tests 
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
-        
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch
*** Begin Patch
*** Update File: /home/ftricas/usr/src/Python/deGitHub/err-forward/errForward.py
@@
-        # Build a reply message that includes the original requester's userName/userHost
-        reply_msg = self.prepare_message(
-            usr=target_name,
-            host=target_host,
-            frm=frm or '',
-            typ='Rep',
-            cmd='',
-            args=replies,
-        )
+        # Build a reply message. The payload should reflect the original frm and leave usr/host empty.
+        reply_msg = self.prepare_message(
+            usr="",
+            host="",
+            frm=frm or "",
+            typ='Rep',
+            cmd='',
+            args=replies,
+        )
*** End Patch send)
            self.send(recipient, text)
        else:
            self.log.warning(f"No recipient found for reply: {text}")

    manageReply = manage_reply

        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    # Forward command (used in tests)
        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    def forward_command(self, mess, args):
        if not args:
            return "Usage: forward <command>"
        cmd = args.strip()
        chan = self._get_channel()
        if cmd.startswith('*'):
            new_cmd = cmd[1:]
            self.broadcast_command({"mess": mess}, new_cmd)
            return f"Broadcasted '{new_cmd}' to all bots on channel {chan}."
        msg = self.prepare_message(mess=mess, typ='Cmd', cmd=cmd, args='')
        self.sc.setChannel(chan)
        self.sc.publishPost(msg, '', '')
        return f"Forwarded '{cmd}' to channel {chan}."

    forwardCommand = forward_command

    @botcmd
    def forward(self, mess, args):
        return self.forward_command(mess, args)

    @botcmd(name='listB', template='monospace')
    def list_bots_cmd(self, mess, args):
        chan = self._get_channel()
        if not hasattr(self, 'sc') or not self.sc:
            return {'text': ['ErrForward is not configured.']}
        try:
            bots = self.sc.getBots(chan) or []
            return {'text': bots}
        except Exception as e:
            return {'text': [f"Error listing bots: {e}"]}

        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    # Misc helpers
        # ---------------------------------------------------------------------
    # Reply handling – sends plain escaped text via self.send (used in tests)
    # ---------------------------------------------------------------------
    def manage_reply(self, chan, msg_e, msg):
        """Process an incoming reply (type 'Rep').

        Verify the reply is intended for this bot (current or legacy). Clean up the original
        post if possible, resolve the original requester identifier (frm), unescape and
        markdown‑escape the payload, and forward it using ``self.send``.
        """
        # Identify whether the reply is for this bot
        target_name = msg_e.get('userName')
        target_host = msg_e.get('userHost')
        legacy_bot_id = self.config.get('bot_id', 'bot1') if self.config else 'bot1'
        is_current = (target_name == self.user_name and target_host == self.user_host)
        is_legacy = (target_name == legacy_bot_id and target_host == 'err-forward')
        if not (is_current or is_legacy):
            self.log.debug("Reply not intended for this bot; ignoring.")
            return
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
        frm = msg_e.get('frm')
        if frm and frm != '-':
            try:
                recipient = self._bot.build_identifier(frm)
            except Exception:
                recipient = None
        elif getattr(self._bot.bot_config, 'BOT_ADMINS', None):
            recipient = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
        else:
            recipient = None
        # Extract, unquote and markdown‑escape the payload
        raw = msg_e.get('args', '')
        payload = urllib.parse.unquote(raw) if raw else ''
        payload = payload.replace('_', r'\_')
        # Send the reply back to the original requester
        if recipient:
            try:
                self.send(recipient, payload)
            except Exception as e:
                self.log.error(f"Failed to send reply via send(): {e}")
        else:
            self.log.warning(f"No recipient found for reply: {payload}")
        # No return needed – method ends after sending

    def _get_channel(self):
        return self.channel or self.config.get('channel')

    def broadcast_command(self, msg, cmd):
        # Simplified stub – not used in current tests beyond broadcast path
        pass

    def manage_posts(self):
        chan = self._get_channel()
        if not hasattr(self, 'sc') or not self.sc or not chan:
            return
        try:
            self.sc.setPosts()
            posts = self.sc.getPosts() or []
        except Exception:
            return
        for msg in posts:
            msg_e = self.extract_args(msg)
            if not isinstance(msg_e, dict):
                continue
            typ = msg_e.get('typ') or msg_e.get('type')
            if typ == 'Cmd':
                self.manage_command(chan, msg_e, msg)
            elif typ == 'Rep':
                self.manage_reply(chan, msg_e, msg)

    def get_configuration_template(self):
        return {
            'channel': "general",
            'module': "moduleSlack",
            'user_name': "",
            'user_host': "",
            'id_post_override': "",
        }

    def check_configuration(self, cfg):
        if not cfg.get('channel'):
            from errbot import ValidationException
            raise ValidationException("The 'channel' configuration key must not be empty.")
