#!/usr/bin/env python
'''A simple Dynamic DNS client for use with Route 53 hosted zones

(c) 2017-2025 - Jason Burks https://github.com/jburks725

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import sys
import json
import requests
import signal
import time
import argparse
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Constants
SLEEP_INTERVAL = 1800  # 30 minutes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GracefulKiller:
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True

def get_ip():
    '''Retrieve the current IP address from ipinfo.io'''
    try:
        response = requests.get('http://ipinfo.io/json', timeout=5)
        response.raise_for_status
        if response.status_code == 200:
            ip = response.json()['ip']
            logging.info(f"Current IP address: {ip}")
            return ip
        if response.status_code == 429:
            logging.warning("Exceeded the daily rate limit for ipinfo.io")
        else:
            logging.warning(f"Unexpected response code: {response.status_code}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving IP address: {e}")
        return None

def update_route_53(client, zone_id, fqdn, ip_address):
    '''Update the Route 53 resource record set for the given FQDN'''
    try:
        response = client.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=fqdn,
            StartRecordType='A',
            MaxItems='1'
        )
    except ClientError as e:
        logging.error(f"Error calling Route 53 API: {e.response['Error']['Message']}")
        return

    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        logging.error("Error searching for Route 53 Resource Record Set. Aborting.")
        return

    if response['ResourceRecordSets'][0]['Name'] == fqdn:
        old_ip_address = response['ResourceRecordSets'][0]['ResourceRecords'][0]['Value']
        if old_ip_address == ip_address:
            logging.info(f"{fqdn} already points to {ip_address}")
            return
        logging.info(f"Updating {fqdn} from {old_ip_address} to {ip_address}")
    else:
        logging.info(f"Adding new A record {fqdn} pointing to {ip_address}")

    try:
        response = client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Comment': 'Record updated by route53dynip',
                'Changes': [
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': fqdn,
                            'Type': 'A',
                            'TTL': 300,
                            'ResourceRecords': [{'Value': ip_address}]
                        }
                    }
                ]
            }
        )
        logging.info(f"Route 53 Change Status: {response['ChangeInfo']['Status']}")
    except ClientError as e:
        logging.error(f"Error calling Route 53 API: {e.response['Error']['Message']}")

def get_hosted_zone(client, name):
    '''Retrieve the Route 53 hosted zone for the given FQDN'''
    labels = name.split('.')
    for i in range(len(labels), 2, -1):
        zone_guess = '.'.join(labels[-i:])
        try:
            response = client.list_hosted_zones_by_name(DNSName=zone_guess, MaxItems='1')
        except ClientError as e:
            logging.error(f"Error calling Route 53 API: {e.response['Error']['Message']}")
            return None

        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
            logging.error("Error searching for Route 53 Hosted Zone. Aborting.")
            return None
        
        if not response['HostedZones']:
            logging.error(f"Could not find a hosted zone for {name}")
            return None
        
        if response['HostedZones'][0]['Name'] == zone_guess:
            return response['HostedZones'][0]['Id'].split('/')[-1]

    logging.error(f"Could not find a hosted zone for {name}")
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fqdn", help="The FQDN to point your IP to")
    parser.add_argument("--onetime", help="Update the DNS entry and exit", action="store_true")
    args = parser.parse_args()

    fqdn = args.fqdn if args.fqdn.endswith('.') else f"{args.fqdn}."

    client = boto3.client('route53')
    zone_id = get_hosted_zone(client, fqdn)
    if zone_id is None:
        sys.exit(1)

    sleeper = GracefulKiller()
    while True:
        if sleeper.kill_now:
            break

        ip = get_ip()
        if ip:
            update_route_53(client, zone_id, fqdn, ip)
        else:
            logging.warning("Could not get IP, skipping this interval")

        if args.onetime:
            break

        for _ in range(SLEEP_INTERVAL):
            time.sleep(1)
            if sleeper.kill_now:
                break

    if not args.onetime:
        logging.info("Thank you for using route53dynip. Have a nice day.")

if __name__ == "__main__":
    main()
