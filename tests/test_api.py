from __future__ import print_function
import unittest
import argparse

import opentuner
from opentuner.api import TuningRunManager
from opentuner.measurement.interface import DefaultMeasurementInterface
from opentuner.resultsdb.models import Result
from opentuner.search.manipulator import ConfigurationManipulator, IntegerParameter

__author__ = 'Chick Markley chick@eecs.berkeley.edu U.C. Berkeley'


class TestApi(unittest.TestCase):
    def test_api_start_and_stop(self):
        parser = argparse.ArgumentParser(parents=opentuner.argparsers())
        args = parser.parse_args(args=[])

        # we set up an api instance but only run it once
        manipulator = ConfigurationManipulator()
        manipulator.add_parameter(IntegerParameter('x', -10, 10))
        interface = DefaultMeasurementInterface(args=args,
                                                manipulator=manipulator,
                                                project_name='examples',
                                                program_name='api_test',
                                                program_version='0.1')
        api = TuningRunManager(interface, args)

        desired_result = api.get_next_desired_result()
        cfg = desired_result.configuration.data['x']
        result = Result(time=float(cfg))
        api.report_result(desired_result, result)

        # something changes and now we want to shut down the api
        # and start a new one, this used to raise an exception

        api.finish()

        manipulator = ConfigurationManipulator()
        manipulator.add_parameter(IntegerParameter('x', -100, 100))
        interface = DefaultMeasurementInterface(args=args,
                                                manipulator=manipulator,
                                                project_name='examples',
                                                program_name='api_test',
                                                program_version='0.1')
        api = TuningRunManager(interface, args)

        desired_result = api.get_next_desired_result()
        cfg = desired_result.configuration.data['x']
        result = Result(time=float(cfg))
        api.report_result(desired_result, result)

        self.assertIsNotNone(api.get_best_configuration())

        api.finish()

    def test_small_range(self):
        parser = argparse.ArgumentParser(parents=opentuner.argparsers())
        args = parser.parse_args(args=[])
        manipulator = ConfigurationManipulator()
        manipulator.add_parameter(IntegerParameter('x', -10, 10))
        interface = DefaultMeasurementInterface(args=args,
                                                manipulator=manipulator,
                                                project_name='examples',
                                                program_name='api_test',
                                                program_version='0.1')
        api = TuningRunManager(interface, args)

        configs_tried = set()

        for x in xrange(40):
            desired_result = api.get_next_desired_result()
            if desired_result is None:
                # The search space for this example is very small, so sometimes
                # the techniques have trouble finding a config that hasn't already
                # been tested.  Change this to a continue to make it try again.
                break
            cfg = desired_result.configuration.data['x']
            result = Result(time=float(cfg))
            api.report_result(desired_result, result)
            configs_tried.add(cfg)

        best_cfg = api.get_best_configuration()
        api.finish()

        self.assertEqual(best_cfg['x'], -10.0)

        # TODO: should this have tried everything in range?
        # print(configs_tried)
        # for x in range(-10, 11):
        #     print(x)
        #     self.assertTrue(
        #         x in configs_tried,
        #         "{} should have been in tried set {}".format(x, configs_tried))