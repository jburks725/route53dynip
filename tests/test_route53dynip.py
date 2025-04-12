#!/usr/bin/env python
'''Unit tests for route53dynip.py'''

import unittest
from unittest.mock import patch, MagicMock, call
import json
import sys
import os
import signal

# Add parent directory to path so we can import the main script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import route53dynip

class TestGetIp(unittest.TestCase):
    '''Tests for the get_ip function'''

    @patch('urllib.request.urlopen')
    def test_get_ip_success(self, mock_urlopen):
        '''Test successful IP address retrieval'''
        # Mock response
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = json.dumps({'ip': '192.0.2.1'}).encode('utf-8')
        mock_response.info.return_value.get_param.return_value = 'utf-8'
        mock_urlopen.return_value = mock_response

        # Call function
        result = route53dynip.get_ip()

        # Verify
        self.assertEqual(result, '192.0.2.1')
        mock_urlopen.assert_called_once_with('http://ipinfo.io/json')

    @patch('urllib.request.urlopen')
    def test_get_ip_rate_limit(self, mock_urlopen):
        '''Test rate limited response'''
        # Mock response
        mock_response = MagicMock()
        mock_response.getcode.return_value = 429
        mock_urlopen.return_value = mock_response

        # Call function
        with patch('builtins.print') as mock_print:
            result = route53dynip.get_ip()

        # Verify
        self.assertIsNone(result)
        mock_print.assert_called_with("Warning: you have exceeded the daily rate limit for ipinfo.io")

    @patch('urllib.request.urlopen')
    def test_get_ip_other_error(self, mock_urlopen):
        '''Test other HTTP error response'''
        # Mock response
        mock_response = MagicMock()
        mock_response.getcode.return_value = 500
        mock_urlopen.return_value = mock_response

        # Call function
        result = route53dynip.get_ip()

        # Verify
        self.assertIsNone(result)


class TestUpdateRoute53(unittest.TestCase):
    '''Tests for the update_route_53 function'''

    def setUp(self):
        self.client = MagicMock()
        self.zone_id = 'Z1234567890ABC'
        self.fqdn = 'test.example.com.'
        self.ip_address = '192.0.2.1'

    def test_update_route53_existing_matching_ip(self):
        '''Test when A record exists with matching IP'''
        # Mock response for list_resource_record_sets
        self.client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [
                {
                    'Name': self.fqdn,
                    'Type': 'A',
                    'TTL': 300,
                    'ResourceRecords': [{'Value': self.ip_address}]
                }
            ]
        }

        # Call function
        with patch('builtins.print') as mock_print:
            route53dynip.update_route_53(self.client, self.zone_id, self.fqdn, self.ip_address)

        # Verify
        self.client.list_resource_record_sets.assert_called_once_with(
            HostedZoneId=self.zone_id,
            StartRecordName=self.fqdn,
            StartRecordType='A',
            MaxItems='1'
        )
        self.client.change_resource_record_sets.assert_not_called()
        mock_print.assert_called_once()
        self.assertIn("already points to", mock_print.call_args[0][0])

    def test_update_route53_existing_different_ip(self):
        '''Test when A record exists with different IP'''
        old_ip = '192.0.2.2'
        # Mock response for list_resource_record_sets
        self.client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [
                {
                    'Name': self.fqdn,
                    'Type': 'A',
                    'TTL': 300,
                    'ResourceRecords': [{'Value': old_ip}]
                }
            ]
        }

        # Mock response for change_resource_record_sets
        self.client.change_resource_record_sets.return_value = {
            'ChangeInfo': {'Status': 'PENDING'}
        }

        # Call function
        with patch('builtins.print') as mock_print:
            route53dynip.update_route_53(self.client, self.zone_id, self.fqdn, self.ip_address)

        # Verify
        self.client.change_resource_record_sets.assert_called_once()
        self.assertEqual(
            self.client.change_resource_record_sets.call_args[1]['ChangeBatch']['Changes'][0]['ResourceRecordSet']['ResourceRecords'][0]['Value'],
            self.ip_address
        )
        mock_print.assert_any_call("Route 53 Change Status: PENDING")

    def test_update_route53_new_record(self):
        '''Test when A record doesn't exist'''
        # Mock response for list_resource_record_sets
        self.client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [
                {
                    'Name': 'different.' + self.fqdn,  # Different name
                    'Type': 'A',
                    'TTL': 300,
                    'ResourceRecords': [{'Value': '192.0.2.3'}]
                }
            ]
        }

        # Mock response for change_resource_record_sets
        self.client.change_resource_record_sets.return_value = {
            'ChangeInfo': {'Status': 'PENDING'}
        }

        # Call function
        with patch('builtins.print') as mock_print:
            route53dynip.update_route_53(self.client, self.zone_id, self.fqdn, self.ip_address)

        # Verify
        self.client.change_resource_record_sets.assert_called_once()
        mock_print.assert_any_call("Route 53 Change Status: PENDING")

    def test_update_route53_api_error_list(self):
        '''Test API error when listing records'''
        # Mock ClientError for list_resource_record_sets
        error_response = {'Error': {'Message': 'Test error'}}
        self.client.list_resource_record_sets.side_effect = route53dynip.ClientError(error_response, 'operation')

        # Call function
        with patch('builtins.print') as mock_print:
            route53dynip.update_route_53(self.client, self.zone_id, self.fqdn, self.ip_address)

        # Verify
        self.client.change_resource_record_sets.assert_not_called()
        mock_print.assert_called_once_with("Error calling Route 53 API:", "Test error")

    def test_update_route53_api_error_change(self):
        '''Test API error when changing records'''
        # Mock response for list_resource_record_sets
        self.client.list_resource_record_sets.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'ResourceRecordSets': [
                {
                    'Name': self.fqdn,
                    'Type': 'A',
                    'TTL': 300,
                    'ResourceRecords': [{'Value': '192.0.2.2'}]  # Different IP
                }
            ]
        }

        # Mock ClientError for change_resource_record_sets
        error_response = {'Error': {'Message': 'Test change error'}}
        self.client.change_resource_record_sets.side_effect = route53dynip.ClientError(error_response, 'operation')

        # Call function
        with patch('builtins.print') as mock_print:
            route53dynip.update_route_53(self.client, self.zone_id, self.fqdn, self.ip_address)

        # Verify
        mock_print.assert_any_call("Error calling Route 53 API:", "Test change error")


class TestGetHostedZone(unittest.TestCase):
    '''Tests for the get_hosted_zone function'''

    def setUp(self):
        self.client = MagicMock()

    def test_get_hosted_zone_exact_match(self):
        '''Test finding hosted zone with exact domain match'''
        # Mock response
        self.client.list_hosted_zones_by_name.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'HostedZones': [
                {
                    'Id': '/hostedzone/Z1234567890ABC',
                    'Name': 'example.com.'
                }
            ]
        }

        # Call function
        result = route53dynip.get_hosted_zone(self.client, 'example.com.')

        # Verify
        self.assertEqual(result, 'Z1234567890ABC')
        self.client.list_hosted_zones_by_name.assert_called_once_with(
            DNSName='example.com.',
            MaxItems='1'
        )

    def test_get_hosted_zone_subdomain(self):
        '''Test finding hosted zone with subdomain'''
        # Mock response that returns parent domain after checking subdomain
        def mock_list_zones(DNSName, MaxItems):
            if DNSName == 'test.example.com.':
                return {
                    'ResponseMetadata': {'HTTPStatusCode': 200},
                    'HostedZones': [
                        {
                            'Id': '/hostedzone/Z1234567890ABC',
                            'Name': 'example.com.'  # Different from requested
                        }
                    ]
                }
            elif DNSName == 'example.com.':
                return {
                    'ResponseMetadata': {'HTTPStatusCode': 200},
                    'HostedZones': [
                        {
                            'Id': '/hostedzone/Z1234567890ABC',
                            'Name': 'example.com.'  # Match
                        }
                    ]
                }
            return {'ResponseMetadata': {'HTTPStatusCode': 200}, 'HostedZones': []}

        self.client.list_hosted_zones_by_name.side_effect = mock_list_zones

        # Call function
        result = route53dynip.get_hosted_zone(self.client, 'test.example.com.')

        # Verify
        self.assertEqual(result, 'Z1234567890ABC')

    def test_get_hosted_zone_not_found(self):
        '''Test when no hosted zone is found'''
        # Mock response
        self.client.list_hosted_zones_by_name.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200},
            'HostedZones': [
                {
                    'Id': '/hostedzone/Z1234567890ABC',
                    'Name': 'different.com.'  # Different from requested
                }
            ]
        }

        # Call function
        with patch('builtins.print') as mock_print:
            result = route53dynip.get_hosted_zone(self.client, 'example.com.')

        # Verify
        self.assertIsNone(result)
        mock_print.assert_called_with("Error: Could not find a hosted zone for", "example.com.")

    def test_get_hosted_zone_api_error(self):
        '''Test API error when getting hosted zone'''
        # Mock ClientError
        error_response = {'Error': {'Message': 'Test zone error'}}
        self.client.list_hosted_zones_by_name.side_effect = route53dynip.ClientError(error_response, 'operation')

        # Call function
        with patch('builtins.print') as mock_print:
            result = route53dynip.get_hosted_zone(self.client, 'example.com.')

        # Verify
        self.assertIsNone(result)
        mock_print.assert_called_with("Error calling Route 53 API:", "Test zone error")


class TestGracefulKiller(unittest.TestCase):
    '''Tests for the GracefulKiller class'''

    def test_init(self):
        '''Test GracefulKiller initialization'''
        with patch('signal.signal') as mock_signal:
            killer = route53dynip.GracefulKiller()
            self.assertFalse(killer.kill_now)
            self.assertEqual(mock_signal.call_count, 2)
            self.assertEqual(mock_signal.call_args_list[0][0][0], signal.SIGINT)
            self.assertEqual(mock_signal.call_args_list[1][0][0], signal.SIGTERM)

    def test_exit_gracefully(self):
        '''Test the exit_gracefully method'''
        killer = route53dynip.GracefulKiller()
        self.assertFalse(killer.kill_now)
        
        # Call exit_gracefully
        killer.exit_gracefully(signal.SIGINT, None)
        
        # Verify kill_now is set to True
        self.assertTrue(killer.kill_now)


if __name__ == '__main__':
    unittest.main()
