"""Projects and their tab trees (THREAD-CONTRACT §1.5 and §1.6).

A project is a row of ``write_folders``, extended in place (there is no
separate projects table). Its tab trees are navigation state, one row per
(owner, project, mothership), with append-only number registers and a
retirement history behind them.
"""
