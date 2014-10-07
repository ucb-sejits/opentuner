#!/usr/bin/env python
#
# This is a simple testcase purely for testing the python tuner api
#
# http://en.wikipedia.org/wiki/Rosenbrock_function
#
# Also supports some other test functions taken from:
# http://en.wikipedia.org/wiki/Test_functions_for_optimization
#
from __future__ import print_function

import argparse
import logging

import opentuner
from opentuner.py_api import PyAPI
from opentuner.search.manipulator import FloatParameter
from opentuner.resultsdb.models import Result

log = logging.getLogger(__name__)

parser = argparse.ArgumentParser(parents=opentuner.argparsers())
parser.add_argument('--trials', type=int, default=1000,
                    help='number of trials')
parser.add_argument('--dimensions', type=int, default=2,
                    help='dimensions for the Rosenbrock function')
parser.add_argument('--domain', type=float, default=1000,
                    help='bound for variables in each dimension')
parser.add_argument('--function', default='rosenbrock',
                    choices=('rosenbrock', 'sphere', 'beale', 'parabola'),
                    help='function to use')


def rosenbrock(cfg, args):
    val = 0.0
    if args.function == 'rosenbrock':
        # the actual rosenbrock function:
        for d in xrange(args.dimensions - 1):
            x0 = cfg[d]
            x1 = cfg[d + 1]
            val += 100.0 * (x1 - x0 ** 2) ** 2 + (x0 - 1) ** 2
    elif args.function == 'sphere':
        for d in xrange(args.dimensions):
            xi = cfg[d]
            val += xi ** 2
    elif args.function == 'beale':
        assert args.dimensions == 2
        assert args.domain == 4.5
        x = cfg[0]
        y = cfg[1]
        val = ((1.5 - x + x * y) ** 2 +
               (2.25 - x + x * y ** 2) ** 2 +
               (2.625 - x + x * y ** 3) ** 2)
    return Result(time=val)

def parabola(cfg, args):
    x, y = cfg[0], cfg[1]
    z = (x*x + y*y)
    print("{},{},{}".format(x, y, z))
    return Result(time=z)

if __name__ == '__main__':
    args = parser.parse_args()
    if args.function == 'beale':
        # fixed for this function
        args.domain = 4.5
        args.dimensions = 2

    api = PyAPI('rosenbrock', args)
    for d in xrange(args.dimensions):
        api.add_parameter(FloatParameter( d, -args.domain, args.domain))

    print("search space size 10^{:.2f} trials {}".format(api.get_search_space_order(), args.trials))


    for trial in xrange(args.trials):
        cfg = api.get_next_configuration()
        if args.function == 'parabola':
            api.report_result(parabola(cfg, args))
        else:
            api.report_result(rosenbrock(cfg, args))

    api.close()