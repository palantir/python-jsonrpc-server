Python JSON RPC Server
======================

.. image:: https://circleci.com/gh/palantir/python-jsonrpc-server.svg?style=shield
    :target: https://circleci.com/gh/palantir/python-jsonrpc-server

.. image:: https://ci.appveyor.com/api/projects/status/mdacv6fnif7wonl0?svg=true
    :target: https://ci.appveyor.com/project/gatesn/python-jsonrpc-server

.. image:: https://img.shields.io/github/license/palantir/python-jsonrpc-server.svg
     :target: https://github.com/palantir/python-jsonrpc-server/blob/master/LICENSE

A Python 2.7 and 3.4+ server implementation of the `JSON RPC 2.0`_ protocol. This library has been pulled
out of the `Python Language Server`_ project.

Asynchronous request handling is supported using Python 3's ``concurrent.futures`` module and the Python 2 `concurrent.futures backport`_.

Installation
------------

``pip install -U python-jsonrpc-server``

Usage
-----


Development
-----------

To run the test suite:

``pip install .[test] && tox``

License
-------

This project is made available under the MIT License.

.. _JSON RPC 2.0: http://www.jsonrpc.org/specification
.. _concurrent.futures backport: https://github.com/agronholm/pythonfutures
