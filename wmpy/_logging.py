import logging

def get_logging_shortcuts(name):
    """ Returns a logger, along with bound versions of its debug, warning,
        and error methods.
    """
    logger = logging.getLogger(name)
    return logger, logger.debug, logger.warning, logger.error

