# This program is free software. It comes without any warranty, to the extent
# permitted by applicable law. You can redistribute it and/or modify it under
# the terms of the Do What The Fuck You Want To Public License, Version 2, as
# published by Sam Hocevar. See http://sam.zoy.org/wtfpl/COPYING for more
# details.

import json
import urllib
import urllib2
import logging

class OmegleException(Exception):
    pass

class OmegleFrame(object):
    def __init__(self, event, data=None):
        self.event = event
        self.data = data

    def __repr__(self):
        return "<OmegleFrame %r: %r>" % (self.event, self.data)

class OmegleConnection(object):
    def __init__(self, host="bajor.omegle.com"):
        self.host = host
        self.convid = json.loads(self._request("start", {
            "rcs" : 1,
            "spid" : ""
        }))
        self.connected = False

    def _request(self, endpoint, parameters):
        try:
            logging.info("Sending to /%s: %s" % (endpoint, parameters))
            return urllib2.urlopen(urllib2.Request(
                "http://%s/%s" % (self.host, endpoint),
                urllib.urlencode(parameters)
            )).read()
        except urllib2.HTTPError as e:
            raise OmegleException("failed to send packet")

    def recaptcha(self, challenge, response):
        if self._request("recaptcha", {
            "id" : self.convid,
            "challenge" : challenge,
            "response" : response
        }) != "win":
            raise OmegleException("failed to send captcha packet")

    def typing(self):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        if self._request("typing", {
            "id" : self.convid
        }) != "win":
            raise OmegleException("failed to send typing packet")

    def send(self, msg):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        if self._request("send", {
            "id" : self.convid,
            "msg" : msg
        }) != "win":
            raise OmegleException("failed to send message packet")

    def getFrames(self):
        frames = []

        payloads = json.loads(self._request("events", { "id" : self.convid }))

        if payloads is None:
            return None

        for payload in payloads:
            frame = OmegleFrame(*payload)

            if frame.event == "strangerDisconnected":
                self.connected = False
            elif frame.event == "connected":
                self.connected = True

            frames.append(frame)

        return frames

    def disconnect(self):
        if not self.connected:
            raise OmegleException("not connected to omegle")

        if self._request("disconnect", {
            "id" : self.convid
        }) != "win":
            raise OmegleException("failed to send disconnect(!!!) packet")

        self.connected = False
