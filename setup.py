from setuptools import setup


setup(name="tbtools",
      version="0.2",
      author="IPython authors",
      license="BSD",

      classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Operating System :: POSIX :: BSD',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Topic :: Software Development :: Interpreters',
      ],

      packages=["tbtools"],
      entry_points={'console_scripts':['ipdb = tbtools.Debugger:main']},
      zip_safe=True
)
