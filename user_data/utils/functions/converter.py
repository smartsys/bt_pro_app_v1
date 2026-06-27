import numpy as np


def convert_range_json_numpy_arrays(config):
    """Convert indicators_json range config to numpy arrays"""
    if config['type'] == 'arange':
        return np.arange(
            config['start'],
            config['stop'],
            config['step']
        ).astype(config['dtype'])
    # Add other types as needed (linspace, etc.)
    return np.array([config.get('value', config['start'])])
