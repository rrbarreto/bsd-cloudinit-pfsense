# Copyright 2013 Mirantis Inc.
# Copyright 2014 Cloudbase Solutions Srl
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

from oslo_config import cfg
import yaml

from cloudbaseinit.openstack.common import log as logging
from cloudbaseinit.plugins.common.userdataplugins import base
from cloudbaseinit.plugins.common.userdataplugins.cloudconfigplugins import (
    factory
)


LOG = logging.getLogger(__name__)
OPTS = [
    cfg.ListOpt(
        'cloud_config_plugins',
        default=[],
        help=(
            'List which contains the name of the cloud config plugins '
            'ordered by priority.'
        ),
    )
]
CONF = cfg.CONF
CONF.register_opts(OPTS)
DEFAULT_ORDER_VALUE = 999


class CloudConfigError(Exception):
    pass


class CloudConfigPluginExecutor(object):
    """A simple executor class for processing cloud-config plugins.

    :kwarg plugins:
        Pairs of plugin names and the values corresponding to that plugin.
    """

    def __init__(self, **plugins):
        def _lookup_priority(plugin):
            try:
                return CONF.cloud_config_plugins.index(plugin)
            except ValueError:
                # If the plugin was not specified in the order
                # list, then default to a sane and unreachable value.
                return DEFAULT_ORDER_VALUE

        self._expected_plugins = sorted(
            plugins.items(),
            key=lambda item: _lookup_priority(item[0]))

    @classmethod
    def from_yaml(cls, stream):
        """Initialize an executor from an yaml stream."""

        loader = getattr(yaml, 'CLoader', yaml.Loader)
        try:
            content = yaml.load(stream, Loader=loader)
        except (TypeError, ValueError, AttributeError):
            msg = "Invalid yaml stream provided."
            LOG.error(msg)
            raise CloudConfigError(msg)

        return cls(**content)

    def execute(self):
        """Call each plugin, in the order requested by the user."""

        plugins = factory.load_plugins()
        for plugin_name, value in self._expected_plugins:
            method = plugins.get(plugin_name)
            if not method:
                LOG.error("Plugin %r is currently not supported", plugin_name)
                continue

            try:
                method(value)
            except Exception:
                LOG.exception("Processing plugin %s failed", plugin_name)


class CloudConfigPlugin(base.BaseUserDataPlugin):

    def __init__(self):
        super(CloudConfigPlugin, self).__init__("text/cloud-config")

    def process_non_multipart(self, part):
        """Process the given data, if it can be loaded through yaml."""
        try:
            executor = CloudConfigPluginExecutor.from_yaml(part)
        except CloudConfigError:
            LOG.error("Could not process the type %r", type(part))
        else:
            executor.execute()

    def process(self, part):
        payload = part.get_payload()
        self.process_non_multipart(payload)
