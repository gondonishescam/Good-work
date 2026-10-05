# Threaded workers: each webhook is short and I/O-bound. 4 x 32 = 128 concurrent webhooks.
# The Flask dev server or a single sync worker is what collapses at 10-100 calls.
bind = "0.0.0.0:8000"
workers = 4
worker_class = "gthread"
threads = 32
timeout = 30
keepalive = 5
accesslog = "-"
