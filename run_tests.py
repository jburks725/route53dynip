#!/usr/bin/env python
'''Test runner for route53dynip unit tests'''

import unittest
import sys

if __name__ == '__main__':
    # Discover and run all tests
    test_suite = unittest.defaultTestLoader.discover('.')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    
    # Return appropriate exit code for CI/CD pipelines
    sys.exit(not result.wasSuccessful())
