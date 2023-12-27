from datetime import datetime, timedelta
import time
import ActionRunner



class CancellationToken:
    __cancelled = False

    def cancelled(self):
        return self.__cancelled

    def cancel(self):
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

    def __init__(self):
        self.__tasks = []
        self.__timerActions = []

    def execute(self, func, defferredUntil=None, delay=None, parameters=None):
        a = Timer._Task()
        a.func = func

        if (defferredUntil is None) and (delay is not None):
            defferredUntil = datetime.now() + timedelta(seconds=delay)

        a.defferredUntil = defferredUntil

        a.parameters = parameters

        self.__tasks.append(a)

    def add(self, func, frequency):
        a = Timer._TimerAction()
        a.func = func
        a.frequency = frequency
        a.lastRun = datetime.now()
        self.__timerActions.append(a)

    def run(self, cancellationToken=CancellationToken()):
        while not cancellationToken.cancelled():
            a = self._takeTask()
            if (a == None):
                a = self._takeTimerAction()
            
            if (a is not None):
                ActionRunner.Runner.execute(a.func, a.parameters)
            else:
                time.sleep(Timer.DELAY)


    def _takeTask(self):
        t = datetime.now()
        for a in self.__tasks:
            if (a.defferredUntil is None) or (a.defferredUntil <= t):
                self.__tasks.remove(a)
                return a
            
        return None
    
    def _takeTimerAction(self):
        t = datetime.now()
        for a in self.__timerActions:
            if (a.lastRun + timedelta(seconds = a.frequency)) <= t:
                self.__timerActions.remove(a)
                self.__timerActions.append(a)
                a.lastRun = t
                return a
        
        return None
    

            


        