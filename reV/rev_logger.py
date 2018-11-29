"""
Logging for reV
"""
import logging

__all__ = ['setup_logger', 'LoggingAttributes', 'init_logger']

FORMAT = '%(levelname)s - %(asctime)s [%(filename)s:%(lineno)d] : %(message)s'
LOG_LEVEL = {'INFO': logging.INFO,
             'DEBUG': logging.DEBUG,
             'WARNING': logging.WARNING,
             'ERROR': logging.ERROR,
             'CRITICAL': logging.CRITICAL}


def setup_logger(logger_name, log_level="INFO", log_file=None,
                 log_format=FORMAT):
    """
    Setup logging instance with given name and attributes
    """
    logger = logging.getLogger(logger_name)

    logger.setLevel(LOG_LEVEL[log_level])
    if log_file:
        handler = logging.FileHandler(log_file, mode='a')
    else:
        handler = logging.StreamHandler()

    if log_format:
        logformat = logging.Formatter(log_format)
        handler.setFormatter(logformat)

    handlers = [str(h) for h in logger.handlers]
    if str(handler) not in handlers:
        logger.addHandler(handler)

    return logger, handler


class LoggingAttributes:
    """
    Class to store and pass logging attributes to modules
    """
    def __init__(self):
        self._loggers = {}

    def __setitem__(self, logger_name, attributes):
        self._loggers[logger_name] = attributes

    def __getitem__(self, logger_name):
        return self._loggers[logger_name]

    def init_logger(self, logger_name):
        """
        Extract logger attributes and initialize logger
        """
        try:
            attrs = self[logger_name]
            setup_logger(logger_name, **attrs)
        except KeyError:
            pass


REV_LOGGERS = LoggingAttributes()


def init_logger(logger_name, **kwargs):
    """
    Starts logging instance and adds logging attributes to REV_LOGGERS

    Parameters
    ----------
    logger_name : str
        Name of logger to initialize
    **kwargs
        Logging attributes used to setup_logger

    Returns
    -------
    logger : logging.logger
        logging instance that was initialized
    handler : logging.Handler
        Handler for logger (FileHandler or StreamHandler)
    """
    logger, handler = setup_logger(logger_name, **kwargs)

    REV_LOGGERS[logger_name] = kwargs

    return logger, handler
