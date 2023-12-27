import traceback


class Logger:
    def error(err):
        print(err)
        if isinstance(err, BaseException):
            traceback_str = ''.join(traceback.format_tb(err.__traceback__))
            print(traceback_str)
