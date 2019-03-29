# Copyright 2013 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import unittest

try:
    import unittest.mock as mock
except ImportError:
    import mock
from oslo_config import cfg

from cloudbaseinit.plugins.common import constants
from cloudbaseinit.plugins.common import setuserpassword
from cloudbaseinit.tests.metadata import fake_json_response
from cloudbaseinit.tests import testutils

CONF = cfg.CONF


class SetUserPasswordPluginTests(unittest.TestCase):

    def setUp(self):
        self._setpassword_plugin = setuserpassword.SetUserPasswordPlugin()
        self.fake_data = fake_json_response.get_fake_metadata_json(
            '2013-04-04')

    @mock.patch('base64.b64encode')
    @mock.patch('cloudbaseinit.utils.crypt.CryptManager'
                '.load_ssh_rsa_public_key')
    def test_encrypt_password(self, mock_load_ssh_key, mock_b64encode):
        mock_rsa = mock.MagicMock()
        fake_ssh_pub_key = 'fake key'
        fake_password = 'fake password'
        mock_load_ssh_key.return_value = mock_rsa
        mock_rsa.__enter__().public_encrypt.return_value = 'public encrypted'
        mock_b64encode.return_value = 'encrypted password'

        response = self._setpassword_plugin._encrypt_password(
            fake_ssh_pub_key, fake_password)

        mock_load_ssh_key.assert_called_with(fake_ssh_pub_key)
        mock_rsa.__enter__().public_encrypt.assert_called_with(
            b'fake password')
        mock_b64encode.assert_called_with('public encrypted')
        self.assertEqual('encrypted password', response)

    def _test_get_ssh_public_key(self, data_exists):
        mock_service = mock.MagicMock()
        public_keys = self.fake_data['public_keys']
        mock_service.get_public_keys.return_value = public_keys.values()

        response = self._setpassword_plugin._get_ssh_public_key(mock_service)

        mock_service.get_public_keys.assert_called_with()
        self.assertEqual(list(public_keys.values())[0], response)

    def test_get_ssh_plublic_key(self):
        self._test_get_ssh_public_key(data_exists=True)

    def test_get_ssh_plublic_key_no_pub_keys(self):
        self._test_get_ssh_public_key(data_exists=False)

    def _test_get_password(self, inject_password, generate_password):
        shared_data = {}
        reuse_password = not generate_password and not inject_password
        expected_password = 'Passw0rd'
        if reuse_password:
            # The password should be the one created by
            # CreateUser plugin.
            shared_data[constants.SHARED_DATA_PASSWORD] = (
                mock.sentinel.create_user_password)

        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        mock_service.get_admin_password.return_value = expected_password
        mock_osutils.generate_random_password.return_value = expected_password

        with testutils.ConfPatcher('inject_user_password', inject_password):
            response = self._setpassword_plugin._get_password(mock_service,
                                                              mock_osutils,
                                                              shared_data)
        if inject_password:
            mock_service.get_admin_password.assert_called_with()
        elif reuse_password:
            self.assertFalse(mock_service.get_admin_password.called)
            self.assertFalse(mock_osutils.generate_random_password.called)
            expected_password = mock.sentinel.create_user_password
        else:
            mock_osutils.get_maximum_password_length.assert_called_once_with()
            mock_osutils.generate_random_password.assert_called_once_with(
                mock_osutils.get_maximum_password_length())
        self.assertEqual(expected_password, response)

    def test_get_password_inject_true(self):
        self._test_get_password(generate_password=False,
                                inject_password=True)

    def test_get_password_inject_false(self):
        self._test_get_password(generate_password=False,
                                inject_password=False)

    def test_get_password_get_from_create_user_plugin(self):
        self._test_get_password(inject_password=False,
                                generate_password=False)

    def test_get_password_generate(self):
        self._test_get_password(inject_password=False,
                                generate_password=True)

    @mock.patch('cloudbaseinit.plugins.common.setuserpassword.'
                'SetUserPasswordPlugin._get_ssh_public_key')
    @mock.patch('cloudbaseinit.plugins.common.setuserpassword.'
                'SetUserPasswordPlugin._encrypt_password')
    def _test_set_metadata_password(self, mock_encrypt_password,
                                    mock_get_key, ssh_pub_key):
        fake_passw0rd = 'fake Passw0rd'
        mock_service = mock.MagicMock()
        mock_get_key.return_value = ssh_pub_key
        mock_encrypt_password.return_value = 'encrypted password'
        mock_service.post_password.return_value = 'value'
        mock_service.can_post_password = True
        mock_service.is_password_set = False
        with testutils.LogSnatcher('cloudbaseinit.plugins.common.'
                                   'setuserpassword') as snatcher:
            response = self._setpassword_plugin._set_metadata_password(
                fake_passw0rd, mock_service)

        expected_logging = []
        if ssh_pub_key is None:
            expected_logging = [
                'No SSH public key available for password encryption'
            ]
            self.assertTrue(response)
        else:
            mock_get_key.assert_called_once_with(mock_service)
            mock_encrypt_password.assert_called_once_with(ssh_pub_key,
                                                          fake_passw0rd)
            mock_service.post_password.assert_called_with(
                'encrypted password')
            self.assertEqual('value', response)
        self.assertEqual(expected_logging, snatcher.output)

    def test_set_metadata_password_with_ssh_key(self):
        fake_key = 'fake key'
        self._test_set_metadata_password(ssh_pub_key=fake_key)

    def test_set_metadata_password_no_ssh_key(self):
        self._test_set_metadata_password(ssh_pub_key=None)

    def test_set_metadata_password_already_set(self):
        mock_service = mock.MagicMock()
        mock_service.is_password_set = True
        with testutils.LogSnatcher('cloudbaseinit.plugins.common.'
                                   'setuserpassword') as snatcher:
            response = self._setpassword_plugin._set_metadata_password(
                mock.sentinel.fake_password, mock_service)

        self.assertTrue(response)
        expected_logging = ['User\'s password already set in the '
                            'instance metadata and it cannot be '
                            'updated in the instance metadata']
        self.assertEqual(expected_logging, snatcher.output)

    @mock.patch('cloudbaseinit.plugins.common.setuserpassword.'
                'SetUserPasswordPlugin._get_password')
    def test_set_password(self, mock_get_password):
        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        mock_get_password.return_value = 'fake password'
        response = self._setpassword_plugin._set_password(
            mock_service,
            mock_osutils,
            'fake user',
            mock.sentinel.shared_data)
        mock_get_password.assert_called_once_with(
            mock_service,
            mock_osutils,
            mock.sentinel.shared_data)
        mock_osutils.set_user_password.assert_called_once_with(
            'fake user',
            'fake password')
        self.assertEqual(response, 'fake password')

    @mock.patch('cloudbaseinit.plugins.common.setuserpassword.'
                'SetUserPasswordPlugin._set_password')
    @mock.patch('cloudbaseinit.plugins.common.setuserpassword.'
                'SetUserPasswordPlugin._set_metadata_password')
    @mock.patch('cloudbaseinit.osutils.factory.get_os_utils')
    def _test_execute(self, mock_get_os_utils, mock_set_metadata_password,
                      mock_set_password, is_password_set=False,
                      can_post_password=True):
        mock_service = mock.MagicMock()
        mock_osutils = mock.MagicMock()
        fake_shared_data = mock.MagicMock()
        fake_shared_data.get.return_value = 'fake username'
        mock_service.is_password_set = is_password_set
        mock_service.can_post_password = can_post_password
        mock_get_os_utils.return_value = mock_osutils
        mock_osutils.user_exists.return_value = True
        mock_set_password.return_value = 'fake password'

        with testutils.LogSnatcher('cloudbaseinit.plugins.common.'
                                   'setuserpassword') as snatcher:
            response = self._setpassword_plugin.execute(mock_service,
                                                        fake_shared_data)
        mock_get_os_utils.assert_called_once_with()
        fake_shared_data.get.assert_called_with(
            constants.SHARED_DATA_USERNAME, CONF.username)
        mock_osutils.user_exists.assert_called_once_with('fake username')
        mock_set_password.assert_called_once_with(mock_service, mock_osutils,
                                                  'fake username',
                                                  fake_shared_data)

        expected_logging = [
            "Password succesfully updated for user fake username",
        ]
        if can_post_password:
            mock_set_metadata_password.assert_called_once_with('fake password',
                                                               mock_service)
        else:
            expected_logging.append("Cannot set the password in the metadata "
                                    "as it is not supported by this service")
            self.assertFalse(mock_set_metadata_password.called)

        self.assertEqual((1, False), response)
        self.assertEqual(expected_logging, snatcher.output)

    def test_execute(self):
        self._test_execute(is_password_set=False, can_post_password=False)
        self._test_execute(is_password_set=True, can_post_password=True)
        self._test_execute(is_password_set=False, can_post_password=True)
