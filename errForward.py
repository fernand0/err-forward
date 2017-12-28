from errbot import BotPlugin, botcmd, webhook
from slackclient import SlackClient
import configparser
import os, pwd
import datetime
import inspect
import re
import json

def end(msg=""):
    return("END"+msg)

class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """

    def getMyIP(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('google.com', 0))
        return(s.getsockname()[0])
         
    def activate(self):
        """
        Triggers on plugin activation

        You should delete it if you're not using it to override any default behaviour
        """
        #super(Skeleton, self).activate()
        
        super().activate()
        self.log.info('Vamos allá')

        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        
        self['sc'] = SlackClient(slack_token)
        self['chan'] = str(self._check_config('channel'))
        self['userName'] = pwd.getpwuid(os.getuid())[0]
        self['userHost'] = os.uname()[1]

        self.publishSlack(cmd = 'Msg', args = 'Hello! from %s' % self.getMyIP())
        self.start_poller(60, self.readSlack)
        self.log.info('Debería estar activo')

    #def deactivate(self):
    #    """
    #    Triggers on plugin deactivation

    #    You should delete it if you're not using it to override any default behaviour
    #    """
    #    super(Skeleton, self).deactivate()

    def get_configuration_template(self):
        """
        """
        return {'channel': "general"
               }

    def _check_config(self, option):

        # if no config, return nothing
        if self.config is None:
            return None
        else:
            # now, let's validate the key
            if option in self.config:
                return self.config[option]
            else:
                return None

    def callback_message(self, mess):
        userName = self['userName']
        userHost = self['userHost']
        if (mess.body.find(userName) == -1) or (mess.body.find(hostName) == -1):
            yield("Trying!")

    def publishSlack(self, usr="", host="", frm="", mess = "", cmd ="", args =""):
        chan = self['chan']
        userName = self['userName']
        userHost = self['userHost']
        msg = {}
        self.log.debug("IN FOrward %s"%mess)

        if not frm: 
            frm = "-"

        msg['userName'] = userName
        msg['userHost'] = userHost
        msg['frm'] = str(frm)
        msg['cmd'] = cmd
        msg['args'] = args

        #text = "User:%s.Host:%s.From:%s. %s: '%s'" % (userName, userHost, frm, cmd, args)
        #self['sc'].api_call( "chat.postMessage", channel = chan, text = text)
        msgJ = json.dumps(msg)
        self['sc'].api_call( "chat.postMessage", channel = chan, text = msgJ)

    def normalizedChan(self, chan): 
        chanList = self['sc'].api_call("channels.list")['channels'] 
        for channel in chanList: 
            if channel['name_normalized'] == chan:
                return(channel['id'])
        return('')

    def readSlack(self):
        # Don't put yield in this function!
        self.log.info('Start reading Slack')
        chan = self.normalizedChan(self._check_config('channel'))
        history = self['sc'].api_call("channels.history", channel=chan)
        for msg in history['messages']: 
            self.log.info(msg)
            try:
                self.log.info("Converting args")
                msgJ = json.loads(msg['text'])
                argsJ = msgJ['args']
                userNameJ = msgJ['userName'] 
                userHostJ = msgJ['userHost']
                frmJ = msgJ['frm']
                cmdJ = msgJ['cmd']
                argsJ = msgJ['args']
                self.log.info("End Converting")
            except:
                self.log.info("Exception")
                msgJ = ""
            pos = msg['text'].find('Cmd')
            self.log.info("Pos: %d"% pos)
            token = re.split(':|\.| ', msg['text']) 
            tokenCad =''
            for i in range(len(token)):
                tokenCad = tokenCad + token[i]+ '. '
            #if (pos >= 0) and not (msg['text'][0] == '{'): 
            #    listCommands = self._bot.all_commands
            #    cmdM = msg['text'][pos+5+1:-1]
            #    if not cmdM.startswith(self._bot.bot_config.BOT_PREFIX): 
            #        return ""
            #    posE = cmdM.find(' ')
            #    if posE > 0:
            #        cmd = cmdM[1:posE]
            #    else:
            #        cmd = cmdM[1:]
            #    args = cmdM[len(cmd)+1+1:]
            #    self.log.debug("Cmd: %s"% cmd)
            #    if cmd in listCommands:
            #        self.log.debug("I'd execute -%s- with argument -%s-" 
            #                % (cmd, args))
            #        method = listCommands[cmd]
            #        txtR = ''
            #        if inspect.isgeneratorfunction(method): 
            #            replies = method(msg, args) 
            #            for reply in replies: 
            #                if isinstance(reply, str):
            #                    txtR = txtR + '\n' + reply 
            #        else: 
            #            reply = method(msg, args) 
            #            if reply:
            #                txtR = txtR + reply
            #        self.publishSlack(cmd = 'Rep', usr= token[1],
            #                host = token[3], frm = token[5],args = txtR)

            #        self.deleteSlack(chan, msg['ts'])
            if msgJ and cmdJ == 'Cmd':                    
                listCommands = self._bot.all_commands
                cmdM = argsJ
                if not cmdM.startswith(self._bot.bot_config.BOT_PREFIX): 
                    return ""
                cmdM = argsJ
                posE = cmdM.find(' ')
                if posE > 0:
                    cmd = cmdM[1:posE]
                else:
                    cmd = cmdM[1:]
                args = cmdM[len(cmd)+1+1:]

                self.log.debug("Cmd: %s"% cmd)
                if cmd in listCommands:
                    self.log.debug("II'd execute -%s- with argument -%s- msgJ %s frmJ %s" 
                            % (cmd, args, msgJ, frmJ))
                    method = listCommands[cmd]                   
                    txtR = ''
                    if inspect.isgeneratorfunction(method): 
                        replies = method("", args) 
                        for reply in replies: 
                            if isinstance(reply, str):
                                txtR = txtR + '\n' + reply 
                    else: 
                        reply = method("", args) 
                        if reply:
                            txtR = txtR + reply
                    self.publishSlack(cmd = 'Rep', usr= userNameJ,
                            host=userHostJ, frm = frmJ, args = txtR)

                    self.deleteSlack(chan, msg['ts'])
            else:
                #pos = msg['text'].find('Rep')
                #if pos >= 0 and not (msg['text'][0] == '{'): 
                #    userName = self['userName']
                #    userHost = self['userHost']
                #    posMe = msg['text'].find(userName+'@'+userHost)
                #    if (posMe >= 0):
                #        # It's for me
                #        posIFrom = msg['text'].find('From', posMe)
                #        if posIFrom >= 0:
                #            posFFrom = msg['text'].find('. ', posIFrom)
                #        msgFrom = msg['text'][posIFrom+5:posFFrom]
                #        replies = msg['text'][pos+len('Rep:')+2:]
                #        for reply in replies.split('\n'):
                #            if posIFrom >= 0:
                #                botAdmin = self._bot.build_identifier(msgFrom)
                #            else:
                #                botAdmin = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
                #            self.send(botAdmin, '{0}'.format(reply))
                #        self.deleteSlack(chan, msg['ts'])
                if msgJ and cmdJ == 'Rep':                    
                    if (userNameJ == self['userName']) and (userHostJ == self['userHost']):
                        # It's for me
                        replies = argsJ 
                        for reply in replies.split('\n'):
                            self.log.debug("FRm",frmJ)
                            if not (frmJ == '-'):
                                botAdmin = self._bot.build_identifier(frmJ)
                            else:
                                botAdmin = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
                            self.send(botAdmin, '{0}'.format(reply))
                        self.deleteSlack(chan, msg['ts'])


        self.log.info('End reading Slack')

    def deleteSlack(self, theChannel, ts):
        self['sc'].api_call("chat.delete", channel=theChannel, ts=ts) 

    @botcmd
    def forward(self, mess, args):
        #token = re.split(':|\.', args) 
        self.log.debug("FOrward %s"%mess)
        self.publishSlack(mess=mess, cmd = 'Cmd' , args = args)

    @botcmd
    def myIP(self, mess, args):
        yield(self.getMyIP())
        yield(end())
