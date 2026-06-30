"""Simple script to start uvicorn."""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "forex_trading.main:app", "--host", "0.0.0.0", "--port", "8003"],
    stdout=open("backend_uvicorn.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
