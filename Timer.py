from datetime import datetime, timedelta
import time
import threading
import ActionRunner
from Clock import Clock
from Logger import Logger



class CancellationToken:
    __cancelled = False
    __lock = threading.Lock()

    def cancelled(self):
        with self.__lock:
            return self.__cancelled

    def cancel(self):
        with self.__lock:
            self.__cancelled = True



class Timer:
    DELAY = 0.1

    class _Action:
        func: any
        parameters: list = None

    class _Task(_Action):
        defferredUntil: datetime

    class _TimerAction(_Action):
        frequency: int
        lastRun: any

    __tasks: list
    __timerActions: list
    __lock: threading.Lock

    def __init__(self):
        self.__tasks = []
        self.__timerActions = []
        self.__lock = threading.Lock()

    def execute(self, func, defferredUntil=None, delay=None, parameters=None):
        a = Timer._Task()
        a.func = func

        if (defferredUntil is None) and (delay is not None):
            defferredUntil = Clock.now() + timedelta(seconds=delay)

        a.defferredUntil = defferredUntil

        a.parameters = parameters

        with self.__lock:
            self.__tasks.append(a)

    def add(self, func, frequency):
        a = Timer._TimerAction()
        a.func = func
        a.frequency = frequency
        a.lastRun = Clock.now()
        with self.__lock:
            self.__timerActions.append(a)

    def run(self, cancellationToken=None):
        if cancellationToken is None:
            cancellationToken = CancellationToken()
        while not cancellationToken.cancelled():
            try:
                a = self._takeTask()
                if (a == None):
                    a = self._takeTimerAction()

                if (a is not None):
                    ActionRunner.Runner.execute(a.func, a.parameters)
                else:
                    time.sleep(Timer.DELAY)
            except Exception as e:
                Logger.error(f"Timer loop error: {e}")


    def _takeTask(self):
        t = Clock.now()
        with self.__lock:
            for a in self.__tasks:
                if (a.defferredUntil is None) or (a.defferredUntil <= t):
                    self.__tasks.remove(a)
                    return a
            
        return None
    
    def _takeTimerAction(self):
        t = Clock.now()
        with self.__lock:
            for a in self.__timerActions:
                if (a.lastRun + timedelta(seconds = a.frequency)) <= t:
                    self.__timerActions.remove(a)
                    self.__timerActions.append(a)
                    a.lastRun = t
                    return a
        
        return None
    

            


        