# Copyright 2014 Scalyr Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------
#
# author: Steven Czerwinski <czerwin@scalyr.com>

__author__ = 'czerwin@scalyr.com'

import os
import tempfile
import unittest

import scalyr_agent.util as scalyr_util

from scalyr_agent.util import JsonReadFileException, RateLimiter, FakeRunState, ScriptEscalator
from scalyr_agent.json_lib import JsonObject


class TestUtil(unittest.TestCase):

    def setUp(self):
        self.__tempdir = tempfile.mkdtemp()
        self.__path = os.path.join(self.__tempdir, 'testing.json')

    def test_read_file_as_json(self):
        self.__create_file(self.__path, '{ a: "hi"}')

        json_object = scalyr_util.read_file_as_json(self.__path)
        self.assertEquals(json_object, JsonObject(a='hi'))

    def test_read_file_as_json_no_file(self):
        self.assertRaises(JsonReadFileException, scalyr_util.read_file_as_json, 'foo')

    def test_read_file_as_json_with_bad_json(self):
        self.__create_file(self.__path, '{ a: hi}')

        self.assertRaises(JsonReadFileException, scalyr_util.read_file_as_json, self.__path)

    def __create_file(self, path, contents):
        fp = open(path, 'w')
        fp.write(contents)
        fp.close()

    def test_uuid(self):
        first = scalyr_util.create_unique_id()
        second = scalyr_util.create_unique_id()
        self.assertTrue(len(first) > 0)
        self.assertTrue(len(second) > 0)
        self.assertNotEqual(first, second)

    def test_remove_newlines_and_truncate(self):
        self.assertEquals(scalyr_util.remove_newlines_and_truncate('hi', 1000), 'hi')
        self.assertEquals(scalyr_util.remove_newlines_and_truncate('ok then', 2), 'ok')
        self.assertEquals(scalyr_util.remove_newlines_and_truncate('o\nk\n', 1000), 'o k ')
        self.assertEquals(scalyr_util.remove_newlines_and_truncate('ok\n\r there', 1000), 'ok   there')
        self.assertEquals(scalyr_util.remove_newlines_and_truncate('ok\n\r there', 6), 'ok   t')


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        self.__test_rate = RateLimiter(100, 10, current_time=0)
        self.__current_time = 0

    def advance_time(self, delta):
        self.__current_time += delta

    def charge_if_available(self, num_bytes):
        return self.__test_rate.charge_if_available(num_bytes, current_time=self.__current_time)

    def test_basic_use(self):
        self.assertTrue(self.charge_if_available(20))
        self.assertTrue(self.charge_if_available(80))
        self.assertFalse(self.charge_if_available(1))

    def test_refill(self):
        self.assertTrue(self.charge_if_available(60))
        self.assertFalse(self.charge_if_available(60))
        self.advance_time(1)
        self.assertFalse(self.charge_if_available(60))
        self.advance_time(1)
        self.assertTrue(self.charge_if_available(60))


class TestRunState(unittest.TestCase):

    def test_basic_use(self):
        # We use a FakeRunState for testing just so we do not accidentally sleep.
        run_state = FakeRunState()

        self.assertTrue(run_state.is_running())
        run_state.sleep_but_awaken_if_stopped(1.0)
        self.assertEquals(run_state.total_times_slept, 1)
        run_state.stop()
        self.assertFalse(run_state.is_running())

    def test_sleeping_already_stopped(self):
        run_state = FakeRunState()

        run_state.stop()
        run_state.sleep_but_awaken_if_stopped(1.0)
        self.assertEquals(run_state.total_times_slept, 0)

    def test_callbacks(self):
        self.called = False

        def on_stop():
            self.called = True

        run_state = FakeRunState()
        run_state.register_on_stop_callback(on_stop)
        run_state.stop()

        self.assertTrue(self.called)

        # Make sure it is immediately invoked if already stopped.
        self.called = False
        run_state.register_on_stop_callback(on_stop)
        self.assertTrue(self.called)


class TestScriptEscalator(unittest.TestCase):
    def test_is_user_change_required(self):
        (test_instance, controller) = self.create_test_instance('czerwin', 'fileA', 'steve')
        self.assertTrue(test_instance.is_user_change_required())

        (test_instance, controller) = self.create_test_instance('czerwin', 'fileA', 'czerwin')
        self.assertFalse(test_instance.is_user_change_required())

    def test_change_user_and_rerun_script(self):
        (test_instance, controller) = self.create_test_instance('czerwin', 'fileA', 'steve')
        self.assertEquals(test_instance.change_user_and_rerun_script('random'), 0)

        self.assertEquals(controller.call_count, 1)
        self.assertEquals(controller.last_call['user'], 'steve')
        self.assertIsNotNone(controller.last_call['script_file'])

    def create_test_instance(self, current_user, config_file, config_owner):
        controller = TestScriptEscalator.ControllerMock(current_user, config_file, config_owner)
        # noinspection PyTypeChecker
        return ScriptEscalator(controller, config_file, os.getcwd()), controller

    class ControllerMock(object):
        def __init__(self, running_user, expected_config_file, config_owner):
            self.__running_user = running_user
            self.__expected_config_file = expected_config_file
            self.__config_owner = config_owner
            self.last_call = None
            self.call_count = 0

        def get_current_user(self):
            return self.__running_user

        def get_file_owner(self, config_file_path):
            assert self.__expected_config_file == config_file_path
            if self.__expected_config_file == config_file_path:
                return self.__config_owner
            else:
                return None

        def run_as_user(self, user, script_file_path, script_binary, script_args):
            self.call_count += 1
            self.last_call = {
                'user': user,
                'script_file': script_file_path,
                'script_binary': script_binary,
                'script_args': script_args
            }
            return 0