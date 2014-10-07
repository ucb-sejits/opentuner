#!/usr/bin/env python
#
# Simple api test case that tries to find min value of a parabola
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


def parabola(cfg):
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

    api = PyAPI('parabola', args)
    for d in xrange(args.dimensions):
        api.add_parameter(FloatParameter(d, -args.domain, args.domain))

    print("search space size 10^{:.2f} trials {}".format(api.get_search_space_order(), args.trials))

    for trial in xrange(args.trials):
        cfg = api.get_next_configuration()
        api.report_result(parabola(cfg))

    api.close()