#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function

import io
import re
from glob import glob
from os.path import abspath
from os.path import basename
from os.path import dirname
from os.path import join
from os.path import splitext

from setuptools import find_packages
from setuptools import setup

requirements = ['compas>=2.15.1']
keywords_list = ['graph', 'drawing', 'assembly', 'support graph', 'grasshopper', 'compas']

here = abspath(dirname(__file__))


def read(*names, **kwargs):
    return io.open(
        join(here, *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


about = {}
exec(read('src', 'graph_drawing', '__version__.py'), about)

setup(
    name=about['__title__'],
    version=about['__version__'],
    license=about['__license__'],
    description=about['__description__'],
    author=about['__author__'],
    author_email=about['__author_email__'],
    url=about['__url__'],
    long_description='%s\n%s' % (
        re.compile('^.. start-badges.*^.. end-badges', re.M |
                   re.S).sub('', read('README.rst')),
        re.sub(':[a-z]+:`~?(.*?)`', r'``\1``', read('CHANGELOG.rst'))
    ),
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
    include_package_data=True,
    zip_safe=False,
    python_requires='>=3.9',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Scientific/Engineering',
    ],
    keywords=keywords_list,
    install_requires=requirements,
    extras_require={'model': ['compas_model>=0.9.2,<0.10'], 'docs': ['mkdocs>=1.6,<2', 'mkdocs-material>=9.5', 'mkdocstrings[python]>=0.26', 'mike>=2.1', 'ruff']},
    entry_points={},
)
