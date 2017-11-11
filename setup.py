from setuptools import setup, find_packages

setup(
    name='pycfg',
    version='0.1.0',
    python_requires='>=3.6',

    packages=find_packages(where='src'),
    package_dir={'': 'src'},
)
