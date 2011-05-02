# This program is free software. It comes without any warranty, to the extent
# permitted by applicable law. You can redistribute it and/or modify it under
# the terms of the Do What The Fuck You Want To Public License, Version 2, as
# published by Sam Hocevar. See http://sam.zoy.org/wtfpl/COPYING for more
# details.

import json
import urllib
import urllib2

class OmegleException(Exception):
    pass

class OmegleFrame(object):
    def __init__(self, event, data=None):
        self.event = event
        self.data = data

    def __repr__(self):
        return "<OmegleFrame %r: %r>" % (self.event, self.data)

    @staticmethod
    def fromPayload(payload):
        return OmegleFrame(
            payload[0],
            payload[1].strip() if len(payload) > 1 else None
        )

class OmegleConnection(object):
    def __init__(self, host="bajor.omegle.com"):
        self.host = host
        req = urllib2.Request(
            "http://%s/start" % host,
            urllib.urlencode({
                "rcs" : 1,
                "spid" : ""
            })
        )

        self.convid = json.loads(urllib2.urlopen(req).read())
        self.connected = False

    def recaptcha(self, challenge, response):
        req = urllib2.Request(
            "http://%s/recaptcha" % self.host,
            urllib.urlencode({
                "id" : self.convid,
                "challenge" : challenge,
                "response" : response
            })
        )

        if urllib2.urlopen(req).read() != "win":
            raise OmegleException("failed to send captcha packet")

    def typing(self):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        req = urllib2.Request(
            "http://%s/typing" % self.host,
            urllib.urlencode({
                "id" : self.convid
            })
        )

        if urllib2.urlopen(req).read() != "win":
            raise OmegleException("failed to send typing packet")

    def send(self, msg):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        req = urllib2.Request(        
            "http://%s/send" % self.host,
            urllib.urlencode({
                "id" : self.convid,
                "msg" : msg
            })
        )

        if urllib2.urlopen(req).read() != "win":
            raise OmegleException("failed to send message packet")

    def getFrames(self):
        frames = []

        req = urllib2.Request(
            "http://%s/events" % self.host,
            urllib.urlencode({
                "id" : self.convid
            })
        )

        payloads = json.loads(urllib2.urlopen(req).read())

        if payloads is None:
            return None

        for payload in payloads:
            frame = OmegleFrame.fromPayload(payload)

            if frame.event == "strangerDisconnected":
                self.connected = False
            elif frame.event == "connected":
                self.connected = True

            frames.append(frame)

        return frames

    def disconnect(self):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        req = urllib2.Request(
            "http://%s/disconnect" % self.host,
            urllib.urlencode({
                "id" : self.convid
            })
        )

        if urllib2.urlopen(req).read() != "win":
            raise OmegleException("failed to send disconnect(!!!) packet")

        self.connected = False
