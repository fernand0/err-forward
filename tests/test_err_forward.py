import json
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

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

        # Broadcast with *
        self.plugin.sc.getBots.return_value = ['2026-11-13 [!] 127.0.0.1 bot1']
        res = self.plugin.forwardCommand(msg, '*status')
        self.assertIn("Broadcasted 'status'", res)

    def test_list_b_without_end_artifact(self):
        self.plugin.sc.getBots.return_value = ['bot1', 'bot2']
        res = self.plugin.listB(None, None)
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

    def test_check_configuration_validates(self):
        full_cfg = self.plugin.get_configuration_template()
        full_cfg['channel'] = 'custom-channel'
        self.plugin.check_configuration(full_cfg)
        from errbot import ValidationException
        with self.assertRaises(ValidationException):
            bad_cfg = dict(full_cfg)
            bad_cfg['channel'] = ''
            self.plugin.check_configuration(bad_cfg)


if __name__ == '__main__':
    unittest.main()
