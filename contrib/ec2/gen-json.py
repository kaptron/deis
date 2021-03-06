#!/usr/bin/env python
import json
import os
import yaml

CURR_DIR = os.path.dirname(os.path.realpath(__file__))

# Add EC2-specific units to the shared user-data
FORMAT_DOCKER_VOLUME = '''
  [Unit]
  Description=Formats the added EBS volume for Docker
  ConditionPathExists=!/etc/docker-volume-formatted
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/sbin/wipefs -f /dev/xvdf
  ExecStart=/usr/sbin/mkfs.ext4 -i 4096 -b 4096 /dev/xvdf
  ExecStart=/bin/touch /etc/docker-volume-formatted
'''
MOUNT_DOCKER_VOLUME = '''
  [Unit]
  Description=Mount Docker volume to /var/lib/docker
  Requires=format-docker-volume.service
  After=format-docker-volume.service
  Before=docker.service
  [Mount]
  What=/dev/xvdf
  Where=/var/lib/docker
  Type=ext4
'''
FORMAT_ETCD_VOLUME = '''
  [Unit]
  Description=Formats the etcd device
  ConditionPathExists=!/etc/etcd-volume-formatted
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/sbin/wipefs -f /dev/xvdg
  ExecStart=/usr/sbin/mkfs.ext4 -i 4096 -b 4096 /dev/xvdg
  ExecStart=/bin/touch /etc/etcd-volume-formatted
'''
MOUNT_ETCD_VOLUME = '''
  [Unit]
  Description=Mounts the etcd volume
  Requires=format-etcd-volume.service
  After=format-etcd-volume.service
  [Mount]
  What=/dev/xvdg
  Where=/media/etcd
  Type=ext4
'''
PREPARE_ETCD_DATA_DIRECTORY = '''
  [Unit]
  Description=Prepares the etcd data directory
  Requires=media-etcd.mount
  After=media-etcd.mount
  Before=etcd.service
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/bin/chown -R etcd:etcd /media/etcd
'''

new_units = [
  dict({'name': 'format-docker-volume.service', 'command': 'start', 'content': FORMAT_DOCKER_VOLUME}),
  dict({'name': 'var-lib-docker.mount', 'command': 'start', 'content': MOUNT_DOCKER_VOLUME}),
  dict({'name': 'format-etcd-volume.service', 'command': 'start', 'content': FORMAT_ETCD_VOLUME}),
  dict({'name': 'media-etcd.mount', 'command': 'start', 'content': MOUNT_ETCD_VOLUME}),
  dict({'name': 'prepare-etcd-data-directory.service', 'command': 'start', 'content': PREPARE_ETCD_DATA_DIRECTORY})
]

data = yaml.load(file(os.path.join(CURR_DIR, '..', 'coreos', 'user-data'), 'r'))

# coreos-cloudinit will start the units in order, so we want these to be processed before etcd/fleet
# are started
data['coreos']['units'] = new_units + data['coreos']['units']

# configure etcd to use its EBS volume
data['coreos']['etcd']['data-dir'] = '/media/etcd'

header = ["#cloud-config", "---"]
dump = yaml.dump(data, default_flow_style=False)

template = json.load(open(os.path.join(CURR_DIR, 'deis.template.json'),'r'))

template['Resources']['CoreOSServerLaunchConfig']['Properties']['UserData']['Fn::Base64']['Fn::Join'] = [ "\n", header + dump.split("\n") ]
template['Parameters']['ClusterSize']['Default'] = str(os.getenv('DEIS_NUM_INSTANCES', 3))

VPC_ID = os.getenv('VPC_ID', None)
VPC_SUBNETS = os.getenv('VPC_SUBNETS', None)
VPC_PRIVATE_SUBNETS = os.getenv('VPC_PRIVATE_SUBNETS', VPC_SUBNETS)
VPC_ZONES = os.getenv('VPC_ZONES', None)

if VPC_ID and VPC_SUBNETS and VPC_ZONES and len(VPC_SUBNETS.split(',')) == len(VPC_ZONES.split(',')):
  # skip VPC, subnet, route, and internet gateway creation
  del template['Resources']['VPC']
  del template['Resources']['Subnet1']
  del template['Resources']['Subnet2']
  del template['Resources']['Subnet1RouteTableAssociation']
  del template['Resources']['Subnet2RouteTableAssociation']
  del template['Resources']['InternetGateway']
  del template['Resources']['GatewayToInternet']
  del template['Resources']['PublicRouteTable']
  del template['Resources']['PublicRoute']
  del template['Resources']['CoreOSServerLaunchConfig']['DependsOn']
  del template['Resources']['DeisWebELB']['DependsOn']

  # update VpcId fields
  template['Resources']['DeisWebELBSecurityGroup']['Properties']['VpcId'] = VPC_ID
  template['Resources']['VPCSecurityGroup']['Properties']['VpcId'] = VPC_ID

  # update subnets and zones
  template['Resources']['CoreOSServerAutoScale']['Properties']['AvailabilityZones'] = VPC_ZONES.split(',')
  template['Resources']['CoreOSServerAutoScale']['Properties']['VPCZoneIdentifier'] = VPC_PRIVATE_SUBNETS.split(',')
  template['Resources']['DeisWebELB']['Properties']['Subnets'] = VPC_SUBNETS.split(',')

print json.dumps(template)
