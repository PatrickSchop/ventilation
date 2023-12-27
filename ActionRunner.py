from Logger import Logger

class Runner:
    def execute(func, parameters=None):
        try:
            if isinstance(parameters, list):
                #print(f"ActionRunner executing {func} with parameter list {parameters}")
                l = len(parameters)
                if l >= 4:
                    func(parameters[0], parameters[1], parameters[2], parameters[3])
                elif l==3:
                    func(parameters[0], parameters[1], parameters[2])
                elif l==2:
                    func(parameters[0], parameters[1])
                elif l==1:
                    func(parameters[0])
                else:
                    func()
            elif parameters is not None:
                #print(f"ActionRunner executing {func} with single parameter {parameters}")
                func(parameters)
            else:
                #print(f"ActionRunner executing {func} without parameter")
                func()
        except Exception as e:
            Logger.error(e)