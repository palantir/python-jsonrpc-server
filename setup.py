#!/usr/bin/env python
from setuptools import find_packages, setup
import versioneer

README = open('README.rst', 'r').read()


setup(
    name='python-jsonrpc-server',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),

    description='JSON RPC 2.0 server library',

    long_description=README,

    # The project's main homepage.
    url='https://github.com/palantir/python-jsonrpc-server',

    author='Palantir Technologies, Inc.',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(exclude=['contrib', 'docs', 'test']),

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'future>=0.14.0; python_version<"3"',
        'futures; python_version<"3.2"',
        'ujson<=1.35; platform_system!="Windows"',
    ],

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[test]
    extras_require={
        'test': ['versioneer', 'pylint', 'pycodestyle', 'pyflakes', 'pytest', 'mock', 'pytest-cov', 'coverage'],
    },
)
