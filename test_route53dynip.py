import unittest
from unittest.mock import patch, MagicMock
import signal
import json
import logging
import argparse
import requests
from route53dynip import GracefulKiller, get_ip, update_route_53, get_hosted_zone, main

class TestGracefulKiller(unittest.TestCase):
    def test_exit_gracefully(self):
        killer = GracefulKiller()
        self.assertFalse(killer.kill_now)
        killer.exit_gracefully(signal.SIGINT, None)
        self.assertTrue(killer.kill_now)

class TestGetIP(unittest.TestCase):
    @patch('requests.get')
    def test_get_ip_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'ip': '192.168.1.1'}
        mock_get.return_value = mock_response

        with self.assertLogs(level='INFO') as log:
            ip = get_ip()
            self.assertEqual(ip, '192.168.1.1')
            self.assertIn('INFO', log.output[0])

    @patch('requests.get')
    def test_get_ip_rate_limit(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with self.assertLogs(level='WARNING') as log:
            ip = get_ip()
            self.assertIsNone(ip)
            self.assertIn("Exceeded the daily rate limit for ipinfo.io", log.output[0])

    @patch('requests.get', side_effect=requests.exceptions.RequestException('Network error'))
    def test_get_ip_error(self, mock_get):
        with self.assertLogs(level='ERROR') as log:
            ip = get_ip()
            self.assertIsNone(ip)
            self.assertIn("Error retrieving IP address: Network error", log.output[0])

class TestUpdateRoute53(unittest.TestCase):
    @patch('boto3.client')
    def test_update_route_53_no_change(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [{
                'Name': 'example.com.',
                'ResourceRecords': [{'Value': '192.168.1.1'}]
            }]
        }
        with self.assertLogs(level='INFO') as log:
            update_route_53(mock_client, 'zone-id', 'example.com.', '192.168.1.1')
            self.assertIn("example.com. already points to 192.168.1.1", log.output[0])

    @patch('boto3.client')
    def test_update_route_53_update(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [{
                'Name': 'example.com.',
                'ResourceRecords': [{'Value': '192.168.1.1'}]
            }]
        }
        with self.assertLogs(level='INFO') as log:
            update_route_53(mock_client, 'zone-id', 'example.com.', '192.168.1.2')
            self.assertIn("Updating example.com. from 192.168.1.1 to 192.168.1.2", log.output[0])

class TestGetHostedZone(unittest.TestCase):
    @patch('boto3.client')
    def test_get_hosted_zone_success(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.list_hosted_zones_by_name.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'HostedZones': [{'Name': 'example.com.', 'Id': '/hostedzone/zone-id'}]
        }
        zone_id = get_hosted_zone(mock_client, 'example.com.')
        self.assertEqual(zone_id, 'zone-id')

    @patch('boto3.client')
    def test_get_hosted_zone_not_found(self, mock_boto_client):
        mock_client = MagicMock()
        mock_client.list_hosted_zones_by_name.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'HostedZones': []
        }
        with self.assertLogs(level='ERROR') as log:
            zone_id = get_hosted_zone(mock_client, 'example.com.')
            self.assertIsNone(zone_id)
            self.assertIn("Could not find a hosted zone for example.com.", log.output[0])

class TestMainFunction(unittest.TestCase):
    @patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(fqdn='example.com', onetime=True))
    @patch('route53dynip.get_hosted_zone', return_value='zone-id')
    @patch('route53dynip.get_ip', return_value='192.168.1.1')
    @patch('route53dynip.update_route_53')
    @patch('boto3.client')
    def test_main_onetime(self, mock_boto_client, mock_update_route_53, mock_get_ip, mock_get_hosted_zone, mock_parse_args):
        main()
        mock_get_hosted_zone.assert_called_once()
        mock_get_ip.assert_called_once()
        mock_update_route_53.assert_called_once()

if __name__ == '__main__':
    unittest.main()