import base64
import json
import os
import tempfile
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from errbot.backends.base import Message, Identifier
from errForward import ErrForward


class DummyBackendConfig:
    BOT_PREFIX = '!'
    BOT_ADMINS = ('@admin:test.org',)
    BACKEND = 'TestBackend'


class DummyBot:
    def __init__(self):
        self.bot_config = DummyBackendConfig()
        self.all_commands = {}
        self.repo_manager = MagicMock()
        self.repo_manager.plugin_dir = '/tmp'

    def build_identifier(self, id_str):
        mock_id = MagicMock(spec=Identifier)
        mock_id.__str__.return_value = id_str
        return mock_id


class TestErrForward(unittest.TestCase):
    def setUp(self):
        self.bot = DummyBot()
        self.plugin = ErrForward(self.bot)
        self.plugin.user_name = 'testuser'
        self.plugin.user_host = 'testhost'
        self.plugin.channel = 'test-channel'
        self.plugin.sc = MagicMock()
        self.plugin.sc.getChannel.return_value = 'test-channel'
        self.plugin.config = {'channel': 'test-channel'}

    def test_get_my_ip(self):
        ip = self.plugin.getMyIP()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip) > 0)

    def test_prepare_message(self):
        msg_json = self.plugin.prepareMessage(
            typ='Cmd',
            cmd='!status',
            args='arg1 arg2'
        )
        data = json.loads(msg_json)
        self.assertEqual(data['userName'], 'testuser')
        self.assertEqual(data['userHost'], 'testhost')
        self.assertEqual(data['typ'], 'Cmd')
        self.assertEqual(data['cmd'], '!status')
        self.assertEqual(data['args'], 'arg1%20arg2')

    def test_signed_message_keeps_command_fields_top_level(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = os.path.join(directory, 'bot1_key.pem')
            self.plugin.config.update({'bot_id': 'bot1', 'priv_key_path': key_path})
            private_key = self.plugin._load_private_key()
            public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )

            signed = json.loads(self.plugin._sign_envelope({
                'typ': 'Cmd',
                'cmd': ',list',
                'args': 'c0',
                'frm': '@alice:test.org',
            }))

            self.assertEqual(signed['typ'], 'Cmd')
            self.assertEqual(signed['cmd'], ',list')
            self.assertNotIn('payload', signed)
            self.assertIn('sig', signed)
            self.plugin._load_peer_keys = MagicMock(return_value={
                'bot1': base64.b64encode(public_key).decode('ascii'),
            })

            payload, verified, is_signed = self.plugin._try_verify_envelope(
                json.dumps(signed)
            )

            self.assertTrue(is_signed)
            self.assertTrue(verified)
            self.assertEqual(payload['args'], 'c0')
            self.assertEqual(self.plugin.extractArgs({'text': json.dumps(signed)})['cmd'], ',list')

    def test_slack_mangled_sender_in_bot_id_still_verifies(self):
        """Slack may auto-link the host in sender e.g. ftricas::<http://host|host>.
        Verification must still succeed after normalizing sender back to ftricas::host.
        """
        with tempfile.TemporaryDirectory() as directory:
            key_path = os.path.join(directory, 'alice_key.pem')
            self.plugin.config.update({'bot_id': 'alice::example.org', 'priv_key_path': key_path})
            private_key = self.plugin._load_private_key()
            public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            self.plugin._load_peer_keys = MagicMock(return_value={
                'alice::example.org': base64.b64encode(public_key).decode('ascii'),
            })

            # Sign a message normally (sender = 'alice::example.org')
            signed = json.loads(self.plugin._sign_envelope({
                'typ': 'Cmd',
                'cmd': ',list',
                'args': '',
                'frm': 'user',
            }))
            self.assertEqual(signed['sender'], 'alice::example.org')

            # Simulate Slack mangling the host portion of sender
            signed['sender'] = 'alice::<http://example.org|example.org>'
            mangled_str = json.dumps(signed)

            payload, verified, is_signed = self.plugin._try_verify_envelope(mangled_str)

            self.assertTrue(is_signed)
            self.assertTrue(verified)

    def test_key_announce_verifies_with_announced_key_even_if_stale_key_in_peer_keys(self):
        # Stale key in peer_keys for sender 'bot1'
        stale_priv = serialization.load_pem_private_key(
            self.plugin._load_private_key().private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            password=None,
        )
        stale_pub = base64.b64encode(stale_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode('ascii')
        self.plugin._load_peer_keys = MagicMock(return_value={'bot1': stale_pub})

        # Sender bot1 rotated its key and sends a KeyAnnounce signed with its new key
        new_priv = serialization.load_pem_private_key(
            serialization.load_pem_private_key(
                stale_priv.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ),
                password=None,
            ).private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            password=None,
        )
        from cryptography.hazmat.primitives.asymmetric import ed25519
        rotated_priv = ed25519.Ed25519PrivateKey.generate()
        rotated_pub = base64.b64encode(rotated_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode('ascii')

        key_announce_payload = {
            'typ': 'KeyAnnounce',
            'sender': 'bot1',
            'pubkey': rotated_pub,
            'ver': 1,
            'ts': 1234,
        }
        msg_bytes = json.dumps(key_announce_payload, sort_keys=True).encode('utf-8')
        sig = base64.b64encode(rotated_priv.sign(msg_bytes)).decode('ascii')
        signed_announce = dict(key_announce_payload)
        signed_announce['sig'] = sig

        payload, verified, is_signed = self.plugin._try_verify_envelope(
            json.dumps(signed_announce)
        )
        self.assertTrue(is_signed)
        self.assertTrue(verified)
        self.assertEqual(payload['pubkey'], rotated_pub)

    def test_top_level_message_with_payload_field_not_confused_with_nested_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = os.path.join(directory, 'bot1_key.pem')
            self.plugin.config.update({'bot_id': 'bot1', 'priv_key_path': key_path})
            private_key = self.plugin._load_private_key()
            public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            self.plugin._load_peer_keys = MagicMock(return_value={
                'bot1': base64.b64encode(public_key).decode('ascii'),
            })

            # Top-level message with an argument/key named 'payload' that is a string
            signed = json.loads(self.plugin._sign_envelope({
                'typ': 'Cmd',
                'cmd': '!custom',
                'payload': 'some_argument_data',
                'args': 'extra',
            }))

            payload, verified, is_signed = self.plugin._try_verify_envelope(
                json.dumps(signed)
            )
            self.assertTrue(is_signed)
            self.assertTrue(verified)
            self.assertEqual(payload['payload'], 'some_argument_data')

    def test_extract_args_valid_and_unquotes(self):
        raw_payload = json.dumps({
            'typ': 'Cmd',
            'cmd': '!status',
            'args': 'arg1%20arg2'
        })
        msg = {'text': raw_payload}
        extracted = self.plugin.extractArgs(msg)
        self.assertIsInstance(extracted, dict)
        self.assertEqual(extracted['args'], 'arg1 arg2')

    def test_extract_args_invalid_json(self):
        msg = {'text': 'not a json string'}
        self.assertIsNone(self.plugin.extractArgs(msg))

        msg_no_text = {'other': 123}
        self.assertIsNone(self.plugin.extractArgs(msg_no_text))

    def test_manage_command_with_args_passes_message_object(self):
        """
        Critical test: verify that when forwarded command has args,
        method receives a Message instance (fixing the double-forward crash).
        """
        received_msg = []
        received_args = []

        def dummy_cmd(mess, args):
            received_msg.append(mess)
            received_args.append(args)
            # Verify accessing mess.frm works without AttributeError
            return f"Hello from {mess.frm}: {args}"

        self.bot.all_commands['testcmd'] = dummy_cmd

        msg_e = {
            'typ': 'Cmd',
            'cmd': '!testcmd',
            'args': 'hello%20world',
            'frm': '@sender:test.org',
            'userName': 'otheruser',
            'userHost': 'otherhost'
        }
        raw_msg = {'ts': '1234.5678'}

        self.plugin.manageCommand('test-channel', msg_e, raw_msg)

        # Ensure deletePostId was called
        self.plugin.sc.deletePostId.assert_called_with('1234.5678')

        # Ensure dummy_cmd was invoked
        self.assertEqual(len(received_msg), 1)
        self.assertIsInstance(received_msg[0], Message)
        self.assertEqual(str(received_msg[0].frm), '@sender:test.org')
        self.assertEqual(received_msg[0].body, '!testcmd hello world')
        self.assertEqual(received_args[0], 'hello world')

        # Ensure a reply post was published
        self.plugin.sc.publishPost.assert_called()
        published_args = self.plugin.sc.publishPost.call_args[0]
        reply_data = json.loads(published_args[0])
        self.assertEqual(reply_data['typ'], 'Rep')
        self.assertEqual(reply_data['cmd'], 'testcmd')
        unquoted_reply = urllib.parse.unquote(reply_data['args'])
        self.assertIn('Hello from @sender:test.org: hello world', unquoted_reply)

    def test_chained_forward_execution(self):
        """
        Test that forwardCommand can be invoked via manageCommand without crashing
        (Double forward: !fw !fw *status).
        """
        self.bot.all_commands['fw'] = self.plugin.forwardCommand

        msg_e = {
            'typ': 'Cmd',
            'cmd': '!fw',
            'args': '!status%20extra',
            'frm': '@origin:test.org',
            'userName': 'peerbot',
            'userHost': 'peerhost'
        }
        raw_msg = {'ts': '1111.2222'}

        # Calling manageCommand for !fw should execute forwardCommand and not crash with AttributeError
        self.plugin.manageCommand('test-channel', msg_e, raw_msg)

        # publishPost should have been called for forwarding
        self.plugin.sc.publishPost.assert_called()

    def test_manage_reply_sends_to_original_requester(self):
        sent_messages = []
        self.plugin.send = lambda to, text: sent_messages.append((to, text))

        msg_e = {
            'typ': 'Rep',
            'cmd': 'status',
            'userName': 'testuser',
            'userHost': 'testhost',
            'frm': '@requester:test.org',
            'args': 'Bot%20is%20healthy_and_running'
        }
        raw_msg = {'ts': '9999.8888'}

        self.plugin.manageReply('test-channel', msg_e, raw_msg)

        self.assertEqual(len(sent_messages), 1)
        dest, content = sent_messages[0]
        self.assertEqual(str(dest), '@requester:test.org')
        # Check underscore escaped properly
        self.assertIn(r'healthy\_and\_running', content)

    def test_manage_reply_accepts_legacy_bot_id_target(self):
        sent_messages = []
        self.plugin.send = lambda to, text: sent_messages.append((to, text))
        self.plugin.config['bot_id'] = 'legacy-bot'

        msg_e = {
            'typ': 'Rep',
            'cmd': 'status',
            'userName': 'legacy-bot',
            'userHost': 'err-forward',
            'frm': '@requester:test.org',
            'args': 'Legacy%20reply',
        }

        self.plugin.manageReply('test-channel', msg_e, {'ts': '9999.8888'})

        self.assertEqual(len(sent_messages), 1)
        dest, content = sent_messages[0]
        self.assertEqual(str(dest), '@requester:test.org')
        self.assertEqual(content, 'Legacy reply')

    def test_forward_command_validation_and_feedback(self):
        msg = Message(frm=self.bot.build_identifier('@alice:test.org'))

        # Empty args returns usage
        res = self.plugin.forwardCommand(msg, '')
        self.assertIn('Usage: forward', res)

        # Forward with args returns confirmation
        res = self.plugin.forwardCommand(msg, '!status')
        self.assertIn("Forwarded '!status'", res)
        self.plugin.sc.publishPost.assert_called()
        forwarded = json.loads(self.plugin.sc.publishPost.call_args.args[0])
        self.assertEqual(forwarded['userName'], 'testuser')
        self.assertEqual(forwarded['userHost'], 'testhost')

        # Broadcast with *
        self.plugin.sc.getBots.return_value = ['2026-11-13 [!] 127.0.0.1 bot1']
        res = self.plugin.forwardCommand(msg, '*status')
        self.assertIn("Broadcasted 'status'", res)

    def test_errforward_listb_without_end_artifact(self):
        self.plugin.sc.getBots.return_value = ['bot1', 'bot2']
        res = self.plugin.errforward_listb(None, None)
        self.assertEqual(res, {'text': ['bot1', 'bot2']})

    def test_manage_posts_safely_handles_exceptions(self):
        # Force setPosts to raise an exception
        self.plugin.sc.setPosts.side_effect = RuntimeError("Slack API timeout")
        # Should not raise exception
        self.plugin.managePosts()

    def test_manage_posts_skips_when_unconfigured(self):
        self.plugin.channel = None
        self.plugin.config = None
        self.plugin.managePosts()
        self.plugin.sc.setPosts.assert_not_called()

    def test_manage_posts_drops_unverifiable_signed_message_when_authentication_is_available(self):
        self.plugin.sc.getPosts.return_value = [{'text': 'signed'}]
        self.plugin._try_verify_envelope = MagicMock(return_value=(
            {'typ': 'Cmd', 'cmd': '!status', 'args': ''},
            False,
            True,
        ))
        self.plugin._has_signing_capability = MagicMock(return_value=True)
        self.plugin.manage_command = MagicMock()
        self.plugin.managePosts()

        self.plugin.manage_command.assert_not_called()

    def test_manage_posts_interprets_signed_message_when_authentication_is_unavailable(self):
        self.plugin.sc.getPosts.return_value = [{'text': 'signed'}]
        self.plugin._try_verify_envelope = MagicMock(return_value=(
            {'typ': 'Cmd', 'cmd': '!status', 'args': ''},
            False,
            True,
        ))
        self.plugin._has_signing_capability = MagicMock(return_value=False)
        self.plugin.manage_command = MagicMock()
        self.plugin.managePosts()

        self.plugin.manage_command.assert_called_once()

    def test_check_configuration_validates(self):
        full_cfg = self.plugin.get_configuration_template()
        full_cfg['channel'] = 'custom-channel'
        self.plugin.check_configuration(full_cfg)
        from errbot import ValidationException
        with self.assertRaises(ValidationException):
            bad_cfg = dict(full_cfg)
            bad_cfg['channel'] = ''
            self.plugin.check_configuration(bad_cfg)

    def test_check_configuration_accepts_optional_keys(self):
        cfg = {
            'channel': 'general',
            'bot_id': 'bot1',
            'priv_key_path': '/tmp/test_key.pem',
            'require_signature': True
        }
        # Should not raise ValidationException
        self.plugin.check_configuration(cfg)

    def test_default_key_path_and_loading(self):
        default_path = self.plugin._get_default_key_path()
        self.assertTrue(len(default_path) > 0)
        self.assertTrue(default_path.endswith('.pem'))
        key = self.plugin._load_private_key()
        self.assertIsNotNone(key)



    def test_manage_command_split_args_with_space(self):
        """
        When the target command is decorated with split_args_with=' ',
        manage_command must pass a split list to the method (mirroring errbot core).
        This was the root cause of .fw ,list c0 returning 0 results.
        """
        received_args = []

        def dummy_list(mess, args):
            received_args.append(args)
            return f"list received: {args!r}"

        # Mimic @botcmd(split_args_with=' ')
        dummy_list._err_command_split_args_with = ' '
        dummy_list._err_command_template = None

        self.bot.all_commands['list'] = dummy_list

        msg_e = {
            'typ': 'Cmd',
            'cmd': '!list',
            'args': urllib.parse.quote('c0'),
            'frm': '@sender:test.org',
            'userName': 'peer',
            'userHost': 'peerhost',
        }
        self.plugin.manageCommand('test-channel', msg_e, {'ts': '1111.0001'})

        self.assertEqual(len(received_args), 1)
        # Must be a list, not the raw string
        self.assertIsInstance(received_args[0], list)
        self.assertEqual(received_args[0], ['c0'])

    def test_manage_command_split_args_with_none(self):
        """
        When the target command is decorated with split_args_with=None,
        manage_command must split on whitespace (same as str.split()).
        """
        received_args = []

        def dummy_search(mess, args):
            received_args.append(args)
            return f"search: {args!r}"

        dummy_search._err_command_split_args_with = None
        dummy_search._err_command_template = None

        self.bot.all_commands['search'] = dummy_search

        msg_e = {
            'typ': 'Cmd',
            'cmd': '!search',
            'args': urllib.parse.quote('foo bar baz'),
            'frm': '@sender:test.org',
            'userName': 'peer',
            'userHost': 'peerhost',
        }
        self.plugin.manageCommand('test-channel', msg_e, {'ts': '1111.0002'})

        self.assertEqual(len(received_args), 1)
        self.assertIsInstance(received_args[0], list)
        self.assertEqual(received_args[0], ['foo', 'bar', 'baz'])

    def test_manage_command_no_split_args_with_keeps_string(self):
        """
        When the target command has the default split_args_with="" (no splitting),
        manage_command must pass the raw string unchanged.
        """
        received_args = []

        def dummy_echo(mess, args):
            received_args.append(args)
            return f"echo: {args}"

        dummy_echo._err_command_split_args_with = ""   # default: no splitting
        dummy_echo._err_command_template = None

        self.bot.all_commands['echo'] = dummy_echo

        msg_e = {
            'typ': 'Cmd',
            'cmd': '!echo',
            'args': urllib.parse.quote('hello world'),
            'frm': '@sender:test.org',
            'userName': 'peer',
            'userHost': 'peerhost',
        }
        self.plugin.manageCommand('test-channel', msg_e, {'ts': '1111.0003'})

        self.assertEqual(len(received_args), 1)
        self.assertIsInstance(received_args[0], str)
        self.assertEqual(received_args[0], 'hello world')

    def test_get_bot_id(self):
        # 1. Config override
        self.plugin.config = {'bot_id': 'custom_bot'}
        self.assertEqual(self.plugin._get_bot_id(), 'custom_bot')

        # 2. user_name and user_host fallback
        self.plugin.config = {}
        self.plugin.user_name = 'alice'
        self.plugin.user_host = 'example.org'
        self.assertEqual(self.plugin._get_bot_id(), 'alice::example.org')

        # 3. user_name only
        self.plugin.user_host = None
        self.assertEqual(self.plugin._get_bot_id(), 'alice')

        # 4. Default fallback
        self.plugin.user_name = None
        self.assertEqual(self.plugin._get_bot_id(), 'bot1')

    def test_normalize_sender(self):
        normalize = self.plugin._normalize_sender
        # Plain sender unchanged
        self.assertEqual(normalize('ftricas::raspberrypi'), 'ftricas::raspberrypi')
        # Slack-mangled host portion in bot_id
        self.assertEqual(
            normalize('ftricas::<http://elmundoesimperfecto.com|elmundoesimperfecto.com>'),
            'ftricas::elmundoesimperfecto.com'
        )
        # No :: separator – returned as-is
        self.assertEqual(normalize('ftricas'), 'ftricas')
        # Empty string
        self.assertEqual(normalize(''), '')


if __name__ == '__main__':
    unittest.main()
