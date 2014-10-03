__author__ = 'Chick Markley'

"""Python API interface to opentuner

This module was built to a handle our particular use case, where
we are parsing python functions and optimizing JIT code generation
for time or energy.  The JIT aspect made it difficult to use the
standard opentuner methodology, where tuning run main controls the
compilation and execution,

The staticmethod main() method below, shows a simple example of use
The python gets an api object, and uses that object to get new configurations
and report the results of a trial.

If the search space is exhausted the API will just return the best configuration
found.

See also: examples/rosenbrock/rosenbrock_using_api
"""

from datetime import datetime
import os
import math
import socket
import copy
import time
import re
import hashlib
import logging
import uuid


log = logging.getLogger(__name__)

from opentuner import ConfigurationManipulator
from opentuner.tuningrunmain import init_logging
from opentuner import resultsdb
from opentuner.resultsdb.models import DesiredResult, Result
from opentuner.search.driver import SearchDriver
from opentuner.measurement.driver import MeasurementDriver
from opentuner.measurement.inputmanager import FixedInputManager
from opentuner.search import plugin


class PythonAPI():
    """
    simplified interface to opentuner search, currently this does not manage
    the compiler or input options

    """
    def __init__(self,
                 name,
                 args,
                 search_driver=SearchDriver,
                 measurement_driver=MeasurementDriver):
        init_logging()

        self.name = name
        self._manipulator = ConfigurationManipulator()
        manipulator = self.manipulator()
        input_manager = FixedInputManager()
        self.lap_time = time.time()
        self._objective = None
        self._project = None
        self._program = None
        self._version = None
        objective = self.objective()

        if not args.database:
            if name is None:
                args.database = 'opentuner.db'
            else:
                args.database = name
                if not args.database.endswith(".db"):
                    args.database += ".db"

        if not os.path.isdir(args.database):
            os.mkdir(args.database)
        args.database = 'sqlite:///' + os.path.join(args.database,
                                                    socket.gethostname() + '.db')

        if not args.label:
            args.label = 'unnamed'

        #self.fake_commit = ('sqlite' in args.database)
        self.fake_commit = True

        self.args = args

        self.engine, self.Session = resultsdb.connect(args.database)
        self.session = self.Session()
        self.tuning_run = None
        self.search_driver_cls = search_driver
        self.measurement_driver_cls = measurement_driver
        # self.measurement_interface = measurement_interface
        self.measurement_interface = self
        self.input_manager = input_manager
        self.manipulator = manipulator
        self.objective = objective
        self.objective_copy = copy.copy(objective)
        self.driver = None
        self.best_and_final = None

        program_version = (self.measurement_interface
                           .db_program_version(self.session))
        self.session.flush()
        self.measurement_interface.prefix_hook(self.session)
        self.tuning_run = (
            resultsdb.models.TuningRun(
                uuid=uuid.uuid4().hex,
                name=self.args.label,
                args=self.args,
                start_date=datetime.now(),
                program_version=program_version,
                objective=self.objective_copy,
            ))
        self.session.add(self.tuning_run)

        driver_kwargs = {
            'args': self.args,
            'input_manager': self.input_manager,
            'manipulator': self.manipulator,
            'measurement_interface': self.measurement_interface,
            'objective': self.objective,
            'session': self.session,
            'tuning_run_main': self,
            'tuning_run': self.tuning_run,
        }

        self.search_driver = self.search_driver_cls(**driver_kwargs)

        self.measurement_driver = self.measurement_driver_cls(**driver_kwargs)
        self.measurement_interface.set_driver(self.measurement_driver)
        self.input_manager.set_driver(self.measurement_driver)

        self.tuning_run.machine_class = self.measurement_driver.get_machine_class()
        self.tuning_run.input_class = self.input_manager.get_input_class()
        self.desired_result = None
        self.machine = self.measurement_driver.get_machine()
        self.get_next_called = False
        self.pending_desired_results = None

    def add_parameter(self, param):
        self._manipulator.add_parameter(param)

    def get_search_space_order(self):
        return math.log(self.manipulator.search_space_size(), 10)

    def is_configuration_exhausted(self):
        return self.best_and_final is not None

    def get_next_configuration(self):
        if self.best_and_final:
            return self.best_and_final.data

        if not self.pending_desired_results:
            self.search_driver.run_generation_techniques()
            query_result = (
                self.session.query(DesiredResult)
                .filter_by(tuning_run=self.tuning_run, state='REQUESTED')
                .order_by(DesiredResult.generation, DesiredResult.priority.desc())
            )
            import collections
            self.pending_desired_results = collections.deque(query_result.all())

        if len(self.pending_desired_results) == 0:
            self.best_and_final = self.search_driver.best_result.configuration
            self.desired_result = self.search_driver.best_result
        else:
            self.desired_result = self.pending_desired_results.popleft()

        self.lap_timer()
        # print(self.desired_result.configuration.data)
        return self.desired_result.configuration.data

    def report_result(self, result):
        if self.best_and_final:
            return

        result.configuration = self.desired_result.configuration
        result.machine = self.machine
        result.tuning_run = self.tuning_run
        result.collection_date = datetime.now()

        self.session.add(result)
        self.desired_result.result = result
        self.desired_result.state = 'COMPLETE'

        result.collection_cost = self.lap_timer()
        self.session.flush()
        self.commit()
        self.search_driver.plugin_proxy.after_results_wait()
        for result in (self.search_driver.results_query()
                           .filter_by(was_new_best=None)
                           .order_by(Result.collection_date)):
            if self.search_driver.best_result is None:
                self.search_driver.best_result = result
                result.was_new_best = True
            elif self.search_driver.objective.lt(result, self.search_driver.best_result):
                self.search_driver.best_result = result
                result.was_new_best = True
                self.search_driver.plugin_proxy.on_new_best_result(result)
            else:
                result.was_new_best = False

        self.search_driver.result_callbacks()

    def lap_timer(self):
        """return the time elapsed since the last call to lap_timer"""
        t = time.time()
        r = t - self.lap_time
        self.lap_time = t
        return r

    # def compile(self, config_data, id):
    #     """
    #     Compiles according to the configuration in config_data (obtained from desired_result.configuration)
    #     Should use id paramater to determine output location of executable
    #     Return value will be passed to run_precompiled as compile_result, useful for storing error/timeout information
    #     """
    #     pass
    #
    # def run_precompiled(self, desired_result, input, limit, compile_result, id):
    #     """
    #     Runs the given desired result on input and produce a Result()
    #     Abort early if limit (in seconds) is reached
    #     Assumes that the executable to be measured is already compiled
    #       in an executable corresponding to identifier id
    #     compile_result is the return result of compile(), will be None if compile was not called
    #     If id = None, must call run()
    #     """
    #     return self.run(desired_result, input, limit)

    def save_final_config(self, config):
        """
        called at the end of autotuning with the best resultsdb.models.Configuration
        """
        self.best_and_final = config

    def close(self):
        self.measurement_interface.save_final_config(
            self.search_driver.best_result.configuration)
        self.best_and_final = self.search_driver.best_result.configuration
        print("best and final configuration %s" % plugin.cfg_repr(self.best_and_final))
        self.tuning_run.final_config = self.search_driver.best_result.configuration
        self.tuning_run.state = 'COMPLETE'
        self.tuning_run.end_date = datetime.now()
        self.commit(force=True)
        self.session.close()
        # return self.tuning_run.final_config
        return self.best_and_final

    def db_program_version(self, session):
        """return a version identifier for the program being tuned"""
        return resultsdb.models.ProgramVersion.get(
            session=session,
            project=self.project_name(),
            name=self.program_name(),
            version=self.program_version(),
        )

    def set_driver(self, measurement_driver):
        self.driver = measurement_driver

    def project_name(self):
        if self._project is not None:
            return self._project
        autoname = re.sub('(Measurement?)Interface$', '',
                          self.__class__.__name__)
        if autoname:
            return autoname
        else:
            return 'unknown'

    def program_name(self):
        return self._program

    def program_version(self):
        return self._version

    @staticmethod
    def file_hash(filename):
        """helper used to generate program versions"""
        return hashlib.sha256(open(filename).read()).hexdigest()

    def manipulator(self):
        """
        called once to create the search.manipulator.ConfigurationManipulator
        """
        if self._manipulator is None:
            msg = (
                'MeasurementInterface.manipulator() must be implemented or a '
                '"manipulator=..." must be provided to the constructor'
            )
            log.error(msg)
            raise Exception(msg)
        return self._manipulator

    def objective(self):
        """
        called once to create the search.objective.SearchObjective
        """
        if self._objective is None:
            from opentuner.search.objective import MinimizeTime

            return MinimizeTime()
        return self._objective

    def prefix_hook(self, session):
        pass

    def results_wait(self, generation):
        pass

    def commit(self, force=False):
        if force or not self.fake_commit:
            self.session.commit()
        else:
            self.session.flush()

    @staticmethod
    def main():
        import argparse
        import opentuner
        from opentuner.search.manipulator import IntegerParameter
        from opentuner.resultsdb.models import Result

        parser = argparse.ArgumentParser(parents=opentuner.argparsers())
        args = parser.parse_args()
        api = PythonAPI('test', args)
        api.add_parameter(IntegerParameter('x', -200, 200))

        print("machine {}".format(api.measurement_driver.get_machine().cpu))

        def test_func(cfg):
            x = cfg['x']
            y = ( x - 10 ) * ( x - 10 )
            print("f({}) -> {}".format(x, y))
            return Result(time=y)

        for x in xrange(500):
            cfg = api.get_next_configuration()
            result = test_func(cfg)
            api.report_result(result)

        api.close()

# PythonAPI.main()
