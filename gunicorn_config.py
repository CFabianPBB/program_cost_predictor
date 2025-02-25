import os
import multiprocessing

bind = "0.0.0.0:" + os.environ.get("PORT", "10000")
workers = multiprocessing.cpu_count() * 2 + 1