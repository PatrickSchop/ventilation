from datetime import datetime
import time
import ActionRunner

class _TimerAction:
    func: any
    frequency: int
    lastRun: any

class CancellationToken:
    __cancelled = False

    def cancelled(self):
        return self.__cancelled

    def cancel(self):
        self.__cancelled = True

class Timer:
    __actions: list

    def __init__(self):
        self.__actions = []

    def add(self, func, frequency):
        ta = _TimerAction()
        ta.func = func
        ta.frequency = frequency
        ta.lastRun = datetime.now()
        self.__actions.append(ta)

    def run(self, cancellationToken: CancellationToken):
        while not cancellationToken.cancelled():
            t = datetime.now()
            for a in self.__actions:
                if ((t - a.lastRun).seconds >= a.frequency):
                    a.lastRun = t
                    ActionRunner.Runner.execute(a.func)
            time.sleep(0.1)



            


        