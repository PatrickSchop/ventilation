from Logger import Logger

class Runner:
    def execute(func, value=None):
        try:
            if value == None:
                func()
            else:
                func(value)
        except Exception as e:
            Logger.error(e)