#!/usr/bin/env python3
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run a recognizer using the Google Assistant Library with button support.

The Google Assistant Library has direct access to the audio API, so this Python
code doesn't need to record audio. Hot word detection "OK, Google" is supported.

It is available for Raspberry Pi 2/3 only; Pi Zero is not supported.
"""

import logging
import platform
import sys
import threading
from time import sleep
import subprocess

import aiy.assistant.auth_helpers
from aiy.assistant.library import Assistant
import aiy.voicehat
from google.assistant.library.event import EventType
from aip.speech import AipSpeech
import json, requests
from config.config import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
)


class Speech:
    def get_volume(self):
        return int(aiy.audio.get_tts_volume() - 5)

    def to_speech(self, text, lang='zh', per=0):
        apiKey = config.get('BAIDU', 'api_key')
        secretKey = config.get('BAIDU', 'secret_key')

        aip = AipSpeech("10093734", apiKey, secretKey)

        print(aiy.audio.get_tts_volume())

        _vol = int(aiy.audio.get_tts_volume() / (int(100 / 15) + 1))
        result = aip.synthesis(text=text, lang=lang, ctp=1, options={'vol': _vol, 'per': per})
        _filepath = "/tmp/response.mp3"
        if not isinstance(result, dict):
            with open(_filepath, 'wb') as f:
                f.write(result)

        _play = subprocess.Popen(["mpv",
                                  "--volume",
                                  "{}".format(self.get_volume()),
                                  _filepath])
        _play.wait()

    def play_youtube(self, url):
        # mpv --vid no --ytdl
        playshell = subprocess.Popen(["mpv",
                                      "--volume",
                                      "{}".format(self.get_volume()/10),
                                      "--vid",
                                      "no",
                                      "--ytdl",
                                      url],
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE)
        playshell.wait()


class MyAssistant(object):
    """An assistant that runs in the background.

    The Google Assistant Library event loop blocks the running thread entirely.
    To support the button trigger, we need to run the event loop in a separate
    thread. Otherwise, the on_button_pressed() method will never get a chance to
    be invoked.
    """

    def __init__(self):
        self._task = threading.Thread(target=self._run_task)
        self._can_start_conversation = False
        self._assistant = None

        self._if_vlc = False

        self.baidu_speech = Speech()

    def start(self):
        """Starts the assistant.

        Starts the assistant event loop and begin processing events.
        """
        self._task.start()

    def say_ip(self):
        self._if_vlc = True
        ip_address = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True)
        # aiy.audio.say('My IP address is %s' % ip_address.decode('utf-8'), volume=aiy.audio.get_tts_volume()/10)
        self.baidu_speech.to_speech('My IP address is %s' % ip_address.decode('utf-8'))

    def play_youtube(self):
        self._if_vlc = True
        aiy.audio.say("OK, Here you are.", volume=int(aiy.audio.get_tts_volume() / 3))
        self.baidu_speech.play_youtube("https://www.youtube.com/watch?v=QYT8WYdPJYo")

    def play_news(self):
        self._if_vlc = True
        _feedly_token = config.get('FEEDLY', 'token')
        _h_value = "OAuth  {}".format(_feedly_token)
        url = 'http://cloud.feedly.com/v3/streams/contents?count=3&streamId=user/b869fc6c-a570-42c0-b973-782f0fb0db18/category/News'  # noqa
        _request = requests.get(url, headers={"Authorization": _h_value})
        news_data = _request.json()

        response = ""
        _items = news_data['items']
        for i in range(0, len(_items)):
            _news = _items[i]
            response += "第{}則，{}。\n".format(i + 1, _news['title'])

        aiy.audio.say("OK, Here you are.", volume=int(aiy.audio.get_tts_volume() / 3))
        self.baidu_speech.to_speech(response)

    def _run_task(self):
        credentials = aiy.assistant.auth_helpers.get_assistant_credentials()
        with Assistant(credentials) as assistant:
            self._assistant = assistant
            for event in assistant.start():
                self._process_event(event)

    def _process_event(self, event):
        status_ui = aiy.voicehat.get_status_ui()
        if event.type == EventType.ON_START_FINISHED:
            status_ui.status('ready')
            self._can_start_conversation = True
            # Start the voicehat button trigger.
            aiy.voicehat.get_button().on_press(self._on_button_pressed)
            if sys.stdout.isatty():
                print('Say "OK, Google" or press the button, then speak. '
                      'Press Ctrl+C to quit...')

        elif event.type == EventType.ON_CONVERSATION_TURN_STARTED:
            self._can_start_conversation = False
            status_ui.status('listening')

        elif event.type == EventType.ON_RECOGNIZING_SPEECH_FINISHED and event.args:
            print('You said:', event.args['text'])
            text = event.args['text'].lower()
            if text == 'ip address':
                self._can_start_conversation = False
                self._assistant.stop_conversation()
                self.say_ip()
            elif text == 'play youtube':
                self._can_start_conversation = False
                self._assistant.stop_conversation()
                self.play_youtube()
            elif text == 'show me some news':
                self._can_start_conversation = False
                self._assistant.stop_conversation()
                self.play_news()

        elif event.type == EventType.ON_END_OF_UTTERANCE:
            status_ui.status('thinking')

        elif (event.type == EventType.ON_CONVERSATION_TURN_FINISHED
              or event.type == EventType.ON_CONVERSATION_TURN_TIMEOUT
              or event.type == EventType.ON_NO_RESPONSE):
            status_ui.status('ready')
            self._can_start_conversation = True

        elif event.type == EventType.ON_ASSISTANT_ERROR and event.args and event.args['is_fatal']:
            sys.exit(1)

    def _on_button_pressed(self):
        # Check if we can start a conversation. 'self._can_start_conversation'
        # is False when either:
        # 1. The assistant library is not yet ready; OR
        # 2. The assistant library is already in a conversation.
        if self._can_start_conversation:
            self._assistant.start_conversation()

        if self._if_vlc:
            print("button cancel youtube")
            pkill = subprocess.Popen(["/usr/bin/pkill", "mpv"], stdin=subprocess.PIPE)
            self._if_vlc = False


def main():
    sleep(3)
    print("end sleep")

    if platform.machine() == 'armv6l':
        print('Cannot run hotword demo on Pi Zero!')
        exit(-1)
    MyAssistant().start()


if __name__ == '__main__':
    main()
