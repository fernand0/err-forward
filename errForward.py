import os
import pwd
import inspect
import json
import urllib.parse
import importlib


from errbot import BotPlugin, botcmd
from errbot.backends.base import Message
from errbot.templating import tenv

from socialModules.configMod import *
# You need to:
# pip install social-modules@git+https://git@github.com/fernand0/socialModules@dist

# Mapping of social modules to their respective message ID fields
MODULE_ID_MAP = {
    'moduleSlack': 'ts',
    'moduleGitter': 'id',
    'moduleMastodon': 'id',
    'moduleTwitter': 'id_str',
}

# Maximum message length for platforms like Slack
MAX_MESSAGE_LENGTH = 3800  # Slightly less than 4000 to allow for JSON overhead


def end(msg=""):
    return f"END{msg}"


class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """
        
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
        
        # Set id_post based on mapping, default to 'id'
        self.id_post = MODULE_ID_MAP.get(my_module, 'id')
		
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
        self['chan'] = chan
        self.sc.setChannel(chan)
        self.user_name = pwd.getpwuid(os.getuid())[0]
        self.user_host = os.uname()[1]

        msg_j = self.prepare_message(
            typ='Msg', 
            args=f"Hello! IP: {self.get_my_ip()}. Commands [{self._bot.bot_config.BOT_PREFIX}]. Name: {self.user_host}. Backend: {self._bot.bot_config.BACKEND}"
        )

        self.log.debug(f" Chan: {chan}")
        try:
            self.sc.publishPost(msg_j, '', chan)
        except Exception as e:
            self.log.error(f"Failed to publish activation message: {e}")
        
        self.start_poller(60, self.manage_posts)
        self.log.info('ErrForward has been activated')

    def get_configuration_template(self):
        return {
            'channel': "general",
            'module': "moduleSlack"
        }

    def callback_message(self, mess):
        # This was likely for debugging, refined to prevent unnecessary yielding
        if ((mess.body.find(self.user_name) == -1) 
                or (mess.body.find(self.user_host) == -1)):
            pass

    def get_my_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
 
    @botcmd
    def myip(self, mess, args):
        """ IP of the bot
        """
        yield self.get_my_ip()
        yield end()

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

    def prepare_message(self, usr="", host="", frm="", 
                        mess=None, typ="", cmd="", args=""):
        self.log.info("Start prepare_message")

        if not frm and mess: 
            frm = mess.frm 

        if args and typ != 'Msg':
            self.log.debug(f"prepare_message args: {args}")
            args = urllib.parse.quote(args)

        msg = {
            'userName': usr or getattr(self, 'user_name', ''), 
            'userHost': host or getattr(self, 'user_host', ''), 
            'frm': str(frm), 
            'typ': typ, 
            'cmd': cmd, 
            'args': args
        }
        msg_j = json.dumps(msg)

        self.log.info("End prepare_message")
        return msg_j

    def extract_args(self, msg):
        self.log.debug(f"Msg: {msg}")

        if 'text' in msg: 
            try: 
                msg_e = json.loads(msg['text']) 
            except Exception: 
                self.log.debug(f"    Error Converting json: {msg}") 
                msg_e = msg['text']
        else: 
            self.log.info("No text!")
            msg_e = None
            
        if msg_e and isinstance(msg_e, dict) and ('args' in msg_e) \
                and ('typ' in msg_e) and (msg_e['typ'] != 'Msg'):
            # Unquoting the args
            tmp_j = urllib.parse.unquote(msg_e['args'])
            msg_e['args'] = tmp_j

        return msg_e

    def broadcast_command(self, msg, cmd): 
        self.log.info("Starting Broadcast")
        try:
            list_bots = self.sc.getBots(self['chan'])
        except Exception as e:
            self.log.error(f"Failed to get bots for broadcast: {e}")
            return

        for bot in list_bots:
            try:
                start = bot[bot.find('[')+1]
                new_cmd = start + cmd
                msg_j = self.prepare_message(
                    mess=msg['mess'], typ='Cmd', cmd=new_cmd, 
                    args=msg['args']
                ) 
                self.sc.publishPost(msg_j, '', self['chan'])
            except Exception as e:
                self.log.error(f"Failed to broadcast to bot {bot}: {e}")

        self.log.info("End Broadcast")

    def manage_command(self, chan, msg_e, msg):
        self.log.info(f"Start manage command ({msg_e['cmd']})")
        cmd = msg_e['cmd']
        len_prefix = len(self._bot.bot_config.BOT_PREFIX)
        prefix = cmd[:len_prefix]
        cmd = cmd[len_prefix:]

        if prefix == self._bot.bot_config.BOT_PREFIX:
            self.log.info(f" {cmd} it's for me")
            try:
                old_chan = self.sc.getChannel()
                self.sc.setChannel(chan)
                self.sc.deletePostId(msg[self.id_post])
                self.sc.channel = old_chan
            except Exception as e:
                self.log.error(f"Failed to delete command post: {e}")

            list_commands = self._bot.all_commands
            if cmd in list_commands:
                method = list_commands[cmd]                   
                txt_r = ''
                if msg_e['args']:
                    new_args = urllib.parse.unquote(msg_e['args'])
                    new_msg = ""
                else:
                    new_msg = Message(frm=self._bot.build_identifier(
                        self.bot_config.BOT_ADMINS[0]))
                    new_args = ""

                try:
                    replies = method(new_msg, new_args) 
                    if (not inspect.isgeneratorfunction(method) 
                            and not isinstance(replies, (tuple, list))): 
                        replies = [replies]

                    for reply in replies: 
                        if isinstance(reply, str):
                            txt_r = f"{txt_r}\n{reply}"
                        else:
                            if not method._err_command_template: 
                                txt_r = f"{txt_r} {reply}"
                            else:
                                txt_r = txt_r + tenv().get_template(
                                    f"{method._err_command_template}.md"
                                ).render(reply)

                    # Split long replies into chunks
                    txt_chunks = self._split_message(txt_r)
                    chan_p = self['chan']
                    self.sc.setChannel(chan)

                    for chunk in txt_chunks:
                        reply_msg = self.prepare_message(
                            typ='Rep', 
                            usr=msg_e['userName'], 
                            host=msg_e['userHost'], 
                            frm=msg_e['frm'], 
                            args=chunk
                        )
                        self.sc.publishPost(reply_msg, '', chan_p)
                except Exception as e:
                    self.log.error(f"Error executing or replying to command {cmd}: {e}")
            else:
                self.log.info(f"Command not available {cmd}")
        self.log.info("End manage command")

    def manage_reply(self, chan, msg_e, msg):
        if '|' in msg_e['userHost']:
            msg_e['userHost'] = msg_e['userHost'].split('|')[1]
            if msg_e['userHost'].endswith('>'): 
                msg_e['userHost'] = msg_e['userHost'][:-1]

        if ((msg_e['userName'] == self.user_name) 
                and (msg_e['userHost'] == self.user_host)):
            self.log.info("It's for me")
            try:
                old_chan = self.sc.getChannel()
                self.sc.setChannel(chan)
                self.sc.deletePostId(msg[self.id_post])
                self.sc.channel = old_chan
            except Exception as e:
                self.log.error(f"Failed to delete reply post: {e}")
            
            replies = urllib.parse.unquote(msg_e['args'])
            if not (msg_e['frm'] == '-'):
                msg_to = self._bot.build_identifier(msg_e['frm'])
            else:
                msg_to = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
            replies = replies.replace('_', r'\_')
            
            self.send(msg_to, replies)

    def manage_posts(self):
        if not hasattr(self, 'sc') or not self.sc:
            return

        chan = self['chan']
        try:
            self.sc.setPosts()
            posts = self.sc.getPosts()
        except Exception as e:
            self.log.error(f"Failed to fetch posts: {e}")
            return

        for msg in posts: 
            msg_e = self.extract_args(msg) 
            if msg_e and isinstance(msg_e, dict) and ('typ' in msg_e): 
                if msg_e['typ'] == 'Cmd': 
                    self.manage_command(chan, msg_e, msg) 
                elif msg_e['typ'] == 'Rep':                    
                    self.manage_reply(chan, msg_e, msg)

    def forward_command(self, mess, args):
        self.log.info(f"Begin forward {mess} from {mess.frm}")
        if ' ' in args:
            args_s = args.split()
            cmd = args_s[0]
            new_args = ' '.join(args_s[1:])
        else:
            cmd = args
            new_args = ""
            
        if cmd.startswith('*'):
            new_cmd = cmd[1:]
            msg = {
                'mess': mess, 
                'typ': 'Cmd', 
                'cmd': new_cmd, 
                'args': new_args
            } 
            self.broadcast_command(msg, new_cmd) 
        else: 
            msg_e = self.prepare_message(
                mess=mess, 
                typ='Cmd',
                cmd=cmd,
                args=new_args
            ) 
            try:
                self.sc.publishPost(msg_e, '', self['chan']) 
            except Exception as e:
                self.log.error(f"Failed to forward command: {e}")
        self.log.info(f"End forward {mess}")

    @botcmd
    def forward(self, mess, args):
        """ Command forwarding to another bot
        """
        yield self.forward_command(mess, args)

    @botcmd
    def fw(self, mess, args):
        """ Command forwarding to another bot (abrv)
        """
        yield self.forward_command(mess, args)

    @botcmd(name='listB', template='monospace')
    def list_bots_cmd(self, mess, args):
        """ List bots connected to the Slack channel
        """
        try:
            bots = self.sc.getBots(self['chan'])
            yield {'text': bots}
            yield end()
        except Exception as e:
            yield f"Error listing bots: {e}"
