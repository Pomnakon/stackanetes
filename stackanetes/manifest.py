# Copyright 2016 Intel Corporation
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

import os

from jinja2 import Environment, FileSystemLoader
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger()
CONF = cfg.CONF
CONF.import_group('stackanetes', 'stackanetes.config.stackanetes')


class Manifest(object):
    def __init__(self, configuration, service_dir):
        self.service_dir = service_dir
        self.type = configuration['type']
        self.service_name = configuration['name']
        self.label = configuration['label']
        self.external_ip_enabled = configuration.get('external_ip_enabled',
                                                     False)
        self.memory = CONF.stackanetes.memory
        self.docker_registry = CONF.stackanetes.docker_registry
        self.image_version = CONF.stackanetes.docker_image_tag
        self.host_interface = CONF.stackanetes.minion_interface_name
        self.external_ip = CONF.stackanetes.external_ip
        self.namespace = CONF.stackanetes.namespace
        if configuration.get('containers'):
            self._parameters_for_multi_containers_pod(configuration)
        else:
            self._parameters_for_singel_container_pod(configuration)
        self.template_name = self._find_template()

    def _parameters_for_singel_container_pod(self, configuration):
        self.command = configuration['command']
        self.configmaps = configuration['files']
        self.image = configuration.get('image')
        self.ports = configuration.get('ports', [])
        self.envs = configuration.get('envs', [])
        self.session_affinity = configuration.get("session_affinity",[])
        self.non_root = configuration.get("non_root",[])
        self.emptydirs = configuration.get('emptyDirs', [])
        self.mounts = configuration.get('mounts', [])
        self.envs.append({'COMMAND': self.command})
        self.template_name = self._find_template()
        self._set_service_type()
        if configuration.get('dependencies'):
            self._add_dependencies(self.envs, configuration['dependencies'])
        self._add_files_list(self.envs, self.configmaps)

    def _parameters_for_multi_containers_pod(self, configuration):
        config_maps = []
        empty_dirs = []
        mounts = []
        self.containers = []
        for container_configuration in configuration['containers']:
            container_dict = {}
            container_dict['command'] = container_configuration['command']
            container_dict['image'] = container_configuration['image']
            container_dict['name'] = container_configuration['name']
            container_dict['envs'] = container_configuration.get('envs', [])
            container_dict['emptydirs'] = container_configuration.get('emptyDirs', [])
            container_dict['configmaps'] = container_configuration.get('files', [])
            config_maps.extend(container_dict['configmaps'])
            container_dict['emptyDirs'] = container_configuration.get('emptyDirs', [])
            empty_dirs.extend(container_dict['emptyDirs'])
            container_dict['mounts'] = container_configuration.get('mounts', [])
            mounts.extend(container_dict['mounts'])
            container_dict['envs'].append(
                {'COMMAND': container_configuration['command']})
            self.containers.append(container_dict)
            if configuration.get('dependencies'):
                self._add_dependencies(container_dict['envs'],
                                       configuration['dependencies'])
            self._add_files_list(container_dict['envs'],
                                 container_dict['configmaps'])

        self.configmaps = config_maps
        self.configmaps = self._filter_elements(self.configmaps, 'configmap_name')
        self.emptydirs = empty_dirs
        self.emptydirs = self._filter_elements(self.emptydirs, 'name')
        self.mounts = mounts
        self.mounts = self._filter_elements(self.mounts, 'name')

    @staticmethod
    def _add_files_list(envs, configmaps):
        for config in configmaps:
            if 'dest_file_name' in config:
                config['key_name'] = config['dest_file_name']
            else:
                config['key_name'] = config['file_name']
        configmaps_string = ','.join(map(lambda x: '/'.join(
            [x['container_path'], x['key_name']]), configmaps))
        envs.append({'CONFIGS': configmaps_string})

    @staticmethod
    def _add_dependencies(envs, dependencies):
        jobs = ','.join(dependencies.get('job', []))
        envs.append({'JOBS': jobs})
        services = ','.join(dependencies.get('service', []))
        envs.append({'SERVICES': services})
        ds = ','.join(dependencies.get('ds', []))
        envs.append({'DS': ds})

    def render(self):
        template_dir = os.path.join(self.service_dir, '..', 'templates')

        template_environment = Environment(
            autoescape=False,
            loader=FileSystemLoader(template_dir),
            trim_blocks=False)
        data = template_environment.get_template(self.template_name).render(
            self.__dict__)
        return data

    def _find_template(self):
        if self.type == "network-node":
            return "generic-network-node.yml.j2"
        elif self.type == "compute-node":
            return "generic-compute-node.yml.j2"
        elif self.type == "job":
            return "generic-job.yml.j2"
        elif self.type == "deployment":
            return "generic-deployment.yml.j2"
        elif self.type == "daemonset":
            return "generic-daemonset.yml.j2"
        else:
            msg = "{} type is not supported".format(self.type)
            LOG.error(msg)
            raise KeyError(msg)

    # TODO(DTadrzak): check if those method is still required
    def _set_service_type(self):
        self.service = self.service_name.split("-")[0]

    @staticmethod
    def _filter_elements(dict_list, key_name):
         filtered_list = []
         new_list = []
         for dictionary in dict_list:
             if dictionary[key_name] not in filtered_list:
                 new_list.append(dictionary)
                 filtered_list.append(dictionary[key_name])
         return new_list
